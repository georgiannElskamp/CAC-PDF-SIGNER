import json
import tempfile
import unittest
import zipfile
from pathlib import Path

import build_plugin
import runtime_config
import setup_windows


class PublicSetupTests(unittest.TestCase):
    def test_unique_credentials_and_private_build(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            fake_editor = root / "DesktopEditors.exe"
            fake_editor.write_bytes(b"not executed")
            a, b = root / "first", root / "second"
            first = setup_windows.prepare_settings(a, 47910, str(fake_editor))
            second = setup_windows.prepare_settings(b, 47911, str(fake_editor))
            self.assertNotEqual(first["token"], second["token"])
            self.assertEqual(len(first["token"]), 64)
            self.assertEqual(
                first["token"],
                setup_windows.prepare_settings(a, 47910, str(fake_editor))["token"],
            )
            package = build_plugin.build(a)
            with zipfile.ZipFile(package) as archive:
                connection = archive.read("connection.js").decode()
                self.assertIn(first["token"], connection)
                self.assertNotIn(second["token"], connection)
                self.assertIn("127.0.0.1:47910", connection)
                self.assertIn(b"127.0.0.1:47910", archive.read("background.html"))
                self.assertEqual(
                    set(archive.namelist()), set(build_plugin.FILES + ["connection.js"])
                )
                self.assertEqual(
                    json.loads(archive.read("config.json"))["version"],
                    runtime_config.VERSION,
                )
                self.assertEqual(
                    json.loads(archive.read("config.json"))["variations"][0]["type"],
                    "background",
                )

    def test_private_state_cannot_be_generated_in_checkout(self):
        checkout = Path(runtime_config.__file__).resolve().parent
        with self.assertRaisesRegex(ValueError, "outside the source"):
            setup_windows.prepare_settings(checkout / "private")
        with self.assertRaisesRegex(ValueError, "outside the source"):
            build_plugin.build(checkout)

    def test_bridge_checksum_rejects_untrusted_archive(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            archive = root / "bad.zip"
            archive.write_bytes(b"wrong bytes")
            with self.assertRaisesRegex(ValueError, "checksum"):
                setup_windows.install_bridge(root, archive)
            self.assertFalse((root / "pdfsign-bridge.exe").exists())

    def test_invalid_or_missing_settings_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with self.assertRaises(RuntimeError):
                runtime_config.load_settings(root)
            (root / "settings.json").write_text(
                json.dumps({"port": 47831, "token": ""})
            )
            with self.assertRaises(ValueError):
                runtime_config.load_settings(root)
