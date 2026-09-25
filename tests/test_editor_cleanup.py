import ctypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from editor_ci import _windows_editor_process_ids, stop_windows_editor, supports_form_handoff


class EditorVersionTests(unittest.TestCase):
    def test_form_handoff_version_gate_accepts_prereleases(self):
        self.assertFalse(supports_form_handoff("0.7.0-rc.6"))
        self.assertFalse(supports_form_handoff("0.8.1"))
        self.assertTrue(supports_form_handoff("0.9.0-rc.1"))
        self.assertTrue(supports_form_handoff("0.9.0"))


class EditorProcessSelectionTests(unittest.TestCase):
    def test_cleanup_rechecks_identity_after_opening_a_process_handle(self):
        with tempfile.TemporaryDirectory(prefix="cac-editor-selection-") as directory:
            inventory = [{"ProcessId": 31, "ParentProcessId": 30, "ExecutablePath": None, "Created": "1100"}]
            native = SimpleNamespace(OpenProcess=Mock(return_value=42), CloseHandle=Mock(),
                                     TerminateProcess=Mock(), WaitForSingleObject=Mock(), WAIT_OBJECT_0=0)
            with patch.dict(sys.modules, {"_winapi": native}), \
                 patch("editor_ci.subprocess.run", return_value=SimpleNamespace(stdout=json.dumps(inventory))), \
                 patch("editor_ci._windows_process_times", side_effect=[(100, 120), (200, 0)]):
                stop_windows_editor(directory, SimpleNamespace(pid=30, _handle=20))
            native.CloseHandle.assert_called_once_with(42)
            native.TerminateProcess.assert_not_called()
            native.WaitForSingleObject.assert_not_called()

    def test_cleanup_selects_only_launcher_descendants(self):
        with tempfile.TemporaryDirectory(prefix="cac-editor-selection-") as directory:
            root = Path(directory)
            launcher = root / "DesktopEditors.exe"
            launcher.touch()
            unrelated = root / "update-service.exe"
            unrelated.touch()
            processes = [
                {"ProcessId": 10, "ParentProcessId": 1, "ExecutablePath": str(launcher), "Created": 100},
                {"ProcessId": 11, "ParentProcessId": 10, "ExecutablePath": None, "Created": 110},
                {"ProcessId": 12, "ParentProcessId": 11, "ExecutablePath": r"C:\\Windows\\helper.exe", "Created": 120},
                {"ProcessId": 20, "ParentProcessId": 1, "ExecutablePath": str(unrelated), "Created": 110},
                {"ProcessId": 21, "ParentProcessId": 11, "ExecutablePath": None, "Created": 105},
            ]
            self.assertEqual(_windows_editor_process_ids(root, 10, processes, (100, 0)), {10, 11, 12})

    def test_cleanup_bounds_detached_children_to_launcher_lifetime(self):
        processes = [
            {"ProcessId": 31, "ParentProcessId": 30, "ExecutablePath": None, "Created": 110},
            {"ProcessId": 32, "ParentProcessId": 31, "ExecutablePath": None, "Created": 140},
            {"ProcessId": 33, "ParentProcessId": 30, "ExecutablePath": None, "Created": 90},
            {"ProcessId": 34, "ParentProcessId": 30, "ExecutablePath": None, "Created": 130},
            {"ProcessId": 35, "ParentProcessId": 30, "ExecutablePath": None},
        ]
        with tempfile.TemporaryDirectory(prefix="cac-editor-selection-") as directory:
            self.assertEqual(_windows_editor_process_ids(directory, 30, processes, (100, 120)), {31, 32})
            self.assertEqual(_windows_editor_process_ids(directory, 30, processes, (100, 0)), set())

    def test_cleanup_ignores_pid_reused_by_the_same_executable(self):
        with tempfile.TemporaryDirectory(prefix="cac-editor-selection-") as directory:
            executable = Path(directory) / "DesktopEditors.exe"
            executable.touch()
            processes = [{"ProcessId": 10, "ParentProcessId": 1, "ExecutablePath": str(executable), "Created": 200},
                         {"ProcessId": 11, "ParentProcessId": 10, "ExecutablePath": None, "Created": 210}]
            self.assertEqual(_windows_editor_process_ids(directory, 10, processes, (100, 150)), set())

    def test_cleanup_ignores_reused_launcher_pid(self):
        with tempfile.TemporaryDirectory(prefix="cac-editor-selection-") as directory:
            outside = Path(directory).parent / "not-the-editor.exe"
            outside.touch(exist_ok=True)
            try:
                processes = [
                    {"ProcessId": 40, "ParentProcessId": 1, "ExecutablePath": str(outside), "Created": 100},
                    {"ProcessId": 41, "ParentProcessId": 40, "ExecutablePath": None, "Created": 110},
                ]
                self.assertEqual(_windows_editor_process_ids(directory, 40, processes, (100, 0)), set())
            finally:
                outside.unlink(missing_ok=True)


@unittest.skipUnless(sys.platform == "win32", "Windows process cleanup")
class EditorCleanupTests(unittest.TestCase):
    def test_exited_launcher_child_is_stopped_without_touching_an_independent_process(self):
        with tempfile.TemporaryDirectory(prefix="cac-editor-detached-") as directory:
            root = Path(directory)
            log = root / "editor.log"
            ping = str(Path(os.environ["SystemRoot"]) / "System32/ping.exe")
            other = subprocess.Popen([ping, "-t", "127.0.0.1"], stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
            helper = None
            try:
                script = ("import subprocess,sys; "
                          "p=subprocess.Popen([sys.argv[1],'-t','127.0.0.1'],creationflags=subprocess.CREATE_NO_WINDOW); "
                          "open(sys.argv[2],'w').write(str(p.pid))")
                with log.open("wb") as stream:
                    launcher = subprocess.Popen([sys._base_executable, "-c", script, ping, str(root / "child.pid")],
                                                stdout=stream, stderr=stream, creationflags=subprocess.CREATE_NO_WINDOW)
                launcher.wait(timeout=10)
                import _winapi
                helper = _winapi.OpenProcess(0x100001, False, int((root / "child.pid").read_text()))
                self.assertNotEqual(_winapi.WaitForSingleObject(helper, 0), _winapi.WAIT_OBJECT_0)
                stop_windows_editor(root, launcher)
                self.assertEqual(_winapi.WaitForSingleObject(helper, 10000), _winapi.WAIT_OBJECT_0)
                self.assertIsNone(other.poll())
                log.unlink()
            finally:
                if helper is not None:
                    if _winapi.WaitForSingleObject(helper, 0) != _winapi.WAIT_OBJECT_0:
                        _winapi.TerminateProcess(helper, 1)
                    _winapi.CloseHandle(helper)
                other.kill()
                other.wait(timeout=10)

    def test_detached_helper_releases_its_log(self):
        with tempfile.TemporaryDirectory(prefix="cac-editor-cleanup-") as directory:
            root = Path(directory)
            binary = root / "helper.exe"
            system = Path(os.environ["SystemRoot"]) / "System32"
            shutil.copyfile(system / "cmd.exe", binary)
            alias = ctypes.create_unicode_buffer(32768)
            length = ctypes.windll.kernel32.GetShortPathNameW(str(binary), alias, len(alias))
            self.assertTrue(0 < length < len(alias))
            log = root / "editor.log"
            with log.open("wb") as stream:
                child = subprocess.Popen([alias.value, "/d", "/c", str(system / "ping.exe"), "-t", "127.0.0.1"], stdout=stream,
                                         stderr=stream, creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                self.assertIsNone(child.poll())
                with self.assertRaises(PermissionError):
                    log.unlink()
                stop_windows_editor(root, child)
                child.wait(timeout=10)
                log.unlink()
            finally:
                if child.poll() is None:
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(child.pid)], capture_output=True)
                child.wait(timeout=10)
