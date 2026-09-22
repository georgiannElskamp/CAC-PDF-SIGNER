from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from build_linux import verify_elfs


class LinuxBuildCompatibilityTests(unittest.TestCase):
    def test_newer_glibc_and_wrong_cpu_stop_the_build(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary = root / "worker"
            header = bytearray(20)
            header[:6] = b"\x7fELF\x02\x01"
            header[18:20] = (62).to_bytes(2, "little")
            binary.write_bytes(header)
            with patch("build_linux.subprocess.check_output", return_value="Name: GLIBC_2.28"):
                self.assertEqual(verify_elfs(root, "x86_64", "2.28"), 1)
            with patch("build_linux.subprocess.check_output", return_value="Name: GLIBC_2.34"):
                with self.assertRaisesRegex(ValueError, "newer glibc"):
                    verify_elfs(root, "x86_64", "2.28")
            with self.assertRaisesRegex(ValueError, "CPU architecture"):
                verify_elfs(root, "aarch64", "2.28")
