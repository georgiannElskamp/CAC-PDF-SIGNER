import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import build_standalone


class ReleaseLicenseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        shutil.copytree(build_standalone.ROOT / "licenses", self.root / "licenses")

    def test_all_native_notices_are_collected(self):
        with patch.object(build_standalone, "ROOT", self.root):
            result = build_standalone.native_licenses()
        for name in build_standalone.REQUIRED_NOTICES:
            self.assertEqual(result["licenses/" + name],
                             (self.root / "licenses" / name).read_bytes())
        self.assertIn("licenses/manifest.json", result)

    def test_missing_bridge_dependency_notice_stops_packaging(self):
        (self.root / "licenses/go-x-sys-BSD-3-Clause.txt").unlink()
        with patch.object(build_standalone, "ROOT", self.root):
            with self.assertRaisesRegex(ValueError, "Required license missing"):
                build_standalone.native_licenses()

    def test_changed_upstream_notice_stops_packaging(self):
        (self.root / "licenses/go-BSD-3-Clause.txt").write_text("shortened notice")
        with patch.object(build_standalone, "ROOT", self.root):
            with self.assertRaisesRegex(ValueError, "License checksum mismatch"):
                build_standalone.native_licenses()

    def test_build_ignores_unrelated_native_and_python_search_paths(self):
        with patch.dict(os.environ, {
            "PATH": "unrelated-native-libraries",
            "PYTHONPATH": "unrelated-python-libraries",
            "PYTHONHOME": "unrelated-python-runtime",
        }):
            env = build_standalone.build_environment()
        self.assertNotIn("unrelated-native-libraries", env["PATH"])
        self.assertNotIn("PYTHONPATH", env)
        self.assertNotIn("PYTHONHOME", env)
        self.assertIn(str(Path(os.environ["SystemRoot"]) / "System32"), env["PATH"])
