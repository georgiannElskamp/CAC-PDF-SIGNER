import ctypes
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from editor_ci import _windows_editor_process_ids, stop_windows_editor, supports_form_handoff


class EditorVersionTests(unittest.TestCase):
    def test_form_handoff_version_gate_accepts_prereleases(self):
        self.assertFalse(supports_form_handoff("0.7.0-rc.6"))
        self.assertFalse(supports_form_handoff("0.8.1"))
        self.assertTrue(supports_form_handoff("0.9.0-rc.1"))
        self.assertTrue(supports_form_handoff("0.9.0"))


class EditorProcessSelectionTests(unittest.TestCase):
    def test_cleanup_selects_only_launcher_descendants(self):
        with tempfile.TemporaryDirectory(prefix="cac-editor-selection-") as directory:
            root = Path(directory)
            launcher = root / "DesktopEditors.exe"
            launcher.touch()
            unrelated = root / "update-service.exe"
            unrelated.touch()
            processes = [
                {"ProcessId": 10, "ParentProcessId": 1, "ExecutablePath": str(launcher)},
                {"ProcessId": 11, "ParentProcessId": 10, "ExecutablePath": None},
                {"ProcessId": 12, "ParentProcessId": 11, "ExecutablePath": r"C:\\Windows\\helper.exe"},
                {"ProcessId": 20, "ParentProcessId": 1, "ExecutablePath": str(unrelated)},
            ]
            self.assertEqual(_windows_editor_process_ids(root, 10, processes), {10, 11, 12})

    def test_cleanup_uses_exited_launcher_as_ancestry_marker(self):
        processes = [
            {"ProcessId": 31, "ParentProcessId": 30, "ExecutablePath": None},
            {"ProcessId": 32, "ParentProcessId": 31, "ExecutablePath": None},
        ]
        with tempfile.TemporaryDirectory(prefix="cac-editor-selection-") as directory:
            self.assertEqual(_windows_editor_process_ids(directory, 30, processes), {31, 32})

    def test_cleanup_ignores_reused_launcher_pid(self):
        with tempfile.TemporaryDirectory(prefix="cac-editor-selection-") as directory:
            outside = Path(directory).parent / "not-the-editor.exe"
            outside.touch(exist_ok=True)
            try:
                processes = [
                    {"ProcessId": 40, "ParentProcessId": 1, "ExecutablePath": str(outside)},
                    {"ProcessId": 41, "ParentProcessId": 40, "ExecutablePath": None},
                ]
                self.assertEqual(_windows_editor_process_ids(directory, 40, processes), set())
            finally:
                outside.unlink(missing_ok=True)


@unittest.skipUnless(sys.platform == "win32", "Windows process cleanup")
class EditorCleanupTests(unittest.TestCase):
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
                stop_windows_editor(root, child.pid)
                child.wait(timeout=10)
                log.unlink()
            finally:
                if child.poll() is None:
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(child.pid)], capture_output=True)
                child.wait(timeout=10)
