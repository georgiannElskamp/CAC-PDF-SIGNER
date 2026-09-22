"""Release metadata must not turn incomplete or substituted assets into a pass."""

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import automation


class ReleaseDiscoveryTests(unittest.TestCase):
    def release(self):
        return {"tag_name": "v9.4.0", "id": 123, "published_at": "2026-09-01T12:00:00Z",
                "draft": False, "prerelease": False,
                "assets": [{"id": index, "name": name, "digest": "sha256:" + "a" * 64,
                            "updated_at": "2026-09-01T12:00:00Z",
                            "browser_download_url": f"https://github.com/{automation.UPSTREAM}/releases/download/v9.4.0/{name}"}
                           for index, name in enumerate(automation.ASSETS.values())]}

    def test_complete_release_and_changed_asset_have_different_keys(self):
        first = automation.editor_manifest(self.release())
        second = copy.deepcopy(first)
        second["linux"]["sha256"] = "b" * 64
        approved = {"sha256": "c" * 64}
        self.assertNotEqual(automation.combination(first, approved, "d" * 40),
                            automation.combination(second, approved, "d" * 40))

    def test_missing_checksum_asset_or_foreign_url_is_not_testable(self):
        for change in (lambda r: r["assets"].pop(),
                       lambda r: r["assets"][0].update(digest=None),
                       lambda r: r["assets"][0].update(browser_download_url="https://example.org/editor.exe"),
                       lambda r: r.update(prerelease=True),
                       lambda r: r.update(tag_name="v9.4.0/../../escape")):
            with self.subTest(change=change):
                release = self.release()
                change(release)
                with self.assertRaises(ValueError):
                    automation.editor_manifest(release)

    def test_incomplete_results_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            steps = {"runtime": {"outcome": "success"}, "editor": {"outcome": "skipped"}}
            automation.result(root, "windows-2025", json.dumps(steps))
            self.assertFalse(json.loads((root / "result-windows-2025.json").read_text())["passed"])

    def test_installer_manifest_rejects_path_substitution(self):
        manifest = automation.editor_manifest(self.release())
        manifest["linux"]["file"] = "../../payload"
        with self.assertRaises(ValueError):
            automation.validate_manifest(manifest)

    def test_checksum_failure_does_not_replace_destination(self):
        import io
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "download"
            output.write_bytes(b"approved")
            with patch("urllib.request.urlopen", return_value=io.BytesIO(b"substituted")):
                with self.assertRaises(ValueError):
                    automation.download("https://example.org/test", output, "a" * 64)
            self.assertEqual(output.read_bytes(), b"approved")
            self.assertFalse(output.with_suffix(".partial").exists())
