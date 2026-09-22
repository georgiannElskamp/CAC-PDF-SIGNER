import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from editor_ci import stop_windows_editor


@unittest.skipUnless(sys.platform == "win32", "Windows process cleanup")
class EditorCleanupTests(unittest.TestCase):
    def test_detached_helper_releases_its_log(self):
        with tempfile.TemporaryDirectory(prefix="cac-editor-cleanup-") as directory:
            root = Path(directory)
            binary = root / "helper.exe"
            shutil.copyfile(Path(os.environ["SystemRoot"]) / "System32/ping.exe", binary)
            log = root / "editor.log"
            with log.open("wb") as stream:
                child = subprocess.Popen([str(binary), "-t", "127.0.0.1"], stdout=stream,
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
                    child.kill()
                child.wait(timeout=10)
