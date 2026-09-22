import unittest
from unittest.mock import patch
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
