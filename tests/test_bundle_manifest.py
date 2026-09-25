import tempfile
import unittest
from pathlib import Path

from bundle_manifest import source_hashes, write_manifest, verify_manifest


class NativeManifestTests(unittest.TestCase):
    def test_git_line_endings_do_not_stale_runtime_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("worker.py", "requirements-lock.txt", "requirements-linux.txt", "requirements-build.txt", "requirements-native-build.txt"):
                (root / name).write_bytes(b"first\r\nsecond\r\n")
            expected = source_hashes(root)
            for path in root.iterdir():
                path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n"))
            self.assertEqual(source_hashes(root), expected)

    def test_reused_worker_rejects_changed_source_dependency_toolchain_font_or_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = root / "bundle"
            bundle.mkdir()
            (root / "fonts").mkdir()
            inputs = [root / "worker.py", root / "requirements-lock.txt",
                      root / "requirements-linux.txt", root / "requirements-build.txt", root / "requirements-native-build.txt", root / "fonts/example.ttf"]
            for path in inputs:
                path.write_bytes(b"original")
            payload = bundle / "worker"
            payload.write_bytes(b"runtime")
            nested = bundle / "fonts" / "manifest.json"
            nested.parent.mkdir()
            nested.write_text('{}')
            write_manifest(bundle, root, "test", "test")
            verify_manifest(bundle, root)
            for path in inputs + [payload, nested]:
                with self.subTest(path=path.name):
                    original = path.read_bytes()
                    path.write_bytes(b"changed")
                    with self.assertRaises(ValueError):
                        verify_manifest(bundle, root)
                    path.write_bytes(original)
            extra = bundle / "unexpected"
            extra.write_bytes(b"extra")
            with self.assertRaisesRegex(ValueError, "files differ"):
                verify_manifest(bundle, root)
