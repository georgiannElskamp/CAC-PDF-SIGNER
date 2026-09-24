import ctypes
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from editor_ci import stop_windows_editor, supports_form_handoff


class EditorVersionTests(unittest.TestCase):
    def test_form_handoff_version_gate_accepts_prereleases(self):
        self.assertFalse(supports_form_handoff("0.7.0-rc.6"))
        self.assertFalse(supports_form_handoff("0.8.1"))
        self.assertTrue(supports_form_handoff("0.9.0-rc.1"))
        self.assertTrue(supports_form_handoff("0.9.0"))


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
                stop_windows_editor(root)
                child.wait(timeout=10)
                log.unlink()
            finally:
                if child.poll() is None:
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(child.pid)], capture_output=True)
                child.wait(timeout=10)
