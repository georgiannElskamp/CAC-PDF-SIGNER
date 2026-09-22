import unittest
from unittest.mock import patch
import hashlib
import json
from pathlib import Path
import tempfile
import prepare_release


class HostedReleaseTests(unittest.TestCase):
    def run_record(self):
        return {"path": ".github/workflows/build-candidate.yml", "event": "workflow_dispatch",
                "head_branch": "main", "status": "completed", "conclusion": "success", "head_sha": "a" * 40}

    def test_only_complete_successful_main_build_is_releasable(self):
        self.assertEqual(prepare_release.validate_run(self.run_record()), "a" * 40)
        for field, value in (("path", ".github/workflows/checks.yml"), ("event", "pull_request"),
                             ("head_branch", "feature"), ("status", "in_progress"),
                             ("conclusion", "failure"), ("head_sha", "main")):
            with self.subTest(field=field):
                record = self.run_record()
                record[field] = value
                with self.assertRaises(ValueError):
                    prepare_release.validate_run(record)

    def test_invalid_run_id_is_rejected_before_api_access(self):
        with patch.object(prepare_release, "api") as api:
            with self.assertRaises(ValueError):
                prepare_release.inspect("../../other")
            api.assert_not_called()

    def test_published_version_is_rejected_without_any_write(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, candidate = root / "source", root / "candidate"
            (source / "plugin").mkdir(parents=True)
            candidate.mkdir()
            (source / "plugin/config.json").write_text(json.dumps({"version": "1.2.3"}))
            package = b"synthetic candidate bytes"
            (candidate / "CAC-PDF-Signer.plugin").write_bytes(package)
            (candidate / "metadata.json").write_text(json.dumps({"candidate": True, "plugin": {
                "tag": "v1.2.3", "commit": "a" * 40, "sha256": hashlib.sha256(package).hexdigest()}}))
            with patch.object(prepare_release, "api", return_value={"draft": False}) as api, \
                 patch.object(prepare_release.subprocess, "run") as command:
                with self.assertRaisesRegex(ValueError, "already published"):
                    prepare_release.stage(source, candidate, "a" * 40)
                api.assert_called_once_with(f"/repos/{prepare_release.REPOSITORY}/releases/tags/v1.2.3")
                command.assert_not_called()
