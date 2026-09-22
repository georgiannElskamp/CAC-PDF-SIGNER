import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import build_standalone
from audit_public import audit_release, source_files


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

    def test_existing_release_is_not_embedded_in_source(self):
        release = self.root / "release"
        release.mkdir()
        (release / "CAC-PDF-Signer.plugin").write_bytes(b"old package")
        self.assertTrue(source_files(self.root))
        self.assertFalse(any(release in p.parents for p in source_files(self.root)))

    def test_release_checksum_failure_is_reported(self):
        release = self.root / "release"
        release.mkdir()
        (release / "CAC-PDF-Signer.plugin").write_bytes(b"changed package")
        (release / "SHA256SUMS.txt").write_text("wrong checksum")
        (release / "INSTALL.txt").write_text("installation notes")
        findings = audit_release(self.root)
        self.assertEqual(len(findings), 1)
        self.assertIn("checksum", findings[0][1])
