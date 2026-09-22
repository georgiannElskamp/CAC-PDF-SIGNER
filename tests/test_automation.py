"""Release metadata must not turn incomplete or substituted assets into a pass."""

import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import automation


class IssueLifecycleTests(unittest.TestCase):
    def issue(self, state="open", **overrides):
        return {"number": 5, "title": "Compatibility", "body": "Report\n\n<!-- cac-automation:editor:123 -->",
                "state": state, "user": {"login": "github-actions[bot]"}, **overrides}

    def test_status_changes_even_when_report_text_is_unchanged(self):
        for previous, desired, reason in (("open", "closed", "completed"), ("closed", "open", "reopened")):
            with self.subTest(state=desired), patch.object(automation, "api", side_effect=[[self.issue(previous)], {}]) as api:
                automation.upsert_issue("editor:123", "Compatibility", "Report", state=desired)
                self.assertEqual(api.call_count, 2)
                self.assertEqual(api.call_args.args[0], f"/repos/{automation.REPOSITORY}/issues/5")
                self.assertEqual(api.call_args.kwargs["method"], "PATCH")
                self.assertEqual(api.call_args.kwargs["body"]["state"], desired)
                self.assertEqual(api.call_args.kwargs["body"]["state_reason"], reason)

    def test_identical_report_and_state_do_not_write(self):
        for state in ("open", "closed"):
            with self.subTest(state=state), patch.object(automation, "api", return_value=[self.issue(state)]) as api:
                automation.upsert_issue("editor:123", "Compatibility", "Report", state=state)
                self.assertEqual(api.call_count, 1)

    def test_first_success_is_created_then_closed(self):
        with patch.object(automation, "api", side_effect=[[], self.issue(), self.issue("closed")]) as api:
            result = automation.upsert_issue("editor:123", "Compatibility", "Report", state="closed")
            self.assertEqual(result["state"], "closed")
            self.assertEqual(api.call_args_list[1].kwargs["method"], "POST")
            self.assertNotIn("state", api.call_args_list[1].kwargs["body"])
            self.assertEqual(api.call_args_list[2].kwargs["method"], "PATCH")

    def test_first_failure_needs_only_one_write(self):
        with patch.object(automation, "api", side_effect=[[], self.issue()]) as api:
            automation.upsert_issue("editor:123", "Compatibility", "Report", state="open")
            self.assertEqual(api.call_count, 2)
            self.assertEqual(api.call_args.kwargs["method"], "POST")

    def test_interrupted_first_closure_reuses_created_issue_on_next_report(self):
        with patch.object(automation, "api", side_effect=[[], self.issue(), OSError("interrupted"),
                                                         [self.issue()], self.issue("closed")]) as api:
            with self.assertRaises(OSError):
                automation.upsert_issue("editor:123", "Compatibility", "Report", state="closed")
            automation.upsert_issue("editor:123", "Compatibility", "Report", state="closed")
            writes = [call.kwargs["method"] for call in api.call_args_list if "method" in call.kwargs]
            self.assertEqual(writes, ["POST", "PATCH", "PATCH"])

    def test_searches_all_pages_and_ignores_user_issues_and_pull_requests(self):
        first = [self.issue(user={"login": "someone"})] * 99 + [self.issue(pull_request={"url": "example"})]
        with patch.object(automation, "api", side_effect=[first, [self.issue("closed")], {}]) as api:
            automation.upsert_issue("editor:123", "Compatibility", "Report", state="open")
            self.assertIn("state=all&per_page=100&page=2", api.call_args_list[1].args[0])
            self.assertEqual(api.call_args.kwargs["method"], "PATCH")

    def test_update_failure_propagates_without_creating_another_issue(self):
        with patch.object(automation, "api", side_effect=[[self.issue()], OSError("unavailable")]) as api:
            with self.assertRaises(OSError):
                automation.upsert_issue("editor:123", "Compatibility", "Report", state="closed")
            self.assertEqual(api.call_count, 2)

    def test_invalid_state_cannot_write(self):
        with patch.object(automation, "api") as api:
            with self.assertRaises(ValueError):
                automation.upsert_issue("editor:123", "Compatibility", "Report", state="unknown")
            api.assert_not_called()


class CompatibilityReportTests(unittest.TestCase):
    def check_report(self, *, missing=None, failed=None, extra=None, prerequisites=None, passes=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            metadata = {"editor": automation.editor_manifest(ReleaseDiscoveryTests().release()),
                        "plugin": {"tag": "v1.0.0", "sha256": "a" * 64}, "harness": "b" * 40}
            (root / "metadata.json").write_text(json.dumps(metadata))
            for platform in ("windows-2025", "ubuntu-24.04", "simulation"):
                if platform != missing:
                    (root / f"result-{platform}.json").write_text(json.dumps({"platform": platform, "passed": platform != failed}))
            if extra is not None:
                (root / "result-extra.json").write_text(extra)
            env = {"GITHUB_RUN_ID": "123", "GITHUB_STEP_SUMMARY": str(root / "summary"),
                   "PREREQUISITES": prerequisites if prerequisites is not None else
                   json.dumps(dict.fromkeys(("source", "package", "desktop", "simulation"), "success"))}
            with patch.dict(os.environ, env), patch.object(automation, "upsert_issue") as issue:
                if passes:
                    automation.report(root)
                else:
                    with self.assertRaises(SystemExit):
                        automation.report(root)
                issue.assert_called_once()
                self.assertEqual(issue.call_args.kwargs["state"], "closed" if passes else "open")
                summary = (root / "summary").read_text()
                self.assertIn("Passed automated coverage" if passes else "Investigation required", summary)

    def test_complete_success_closes_issue(self):
        self.check_report(passes=True)

    def test_each_failed_or_missing_platform_reopens_issue(self):
        for platform in ("windows-2025", "ubuntu-24.04", "simulation"):
            with self.subTest(failed=platform):
                self.check_report(failed=platform)
            with self.subTest(missing=platform):
                self.check_report(missing=platform)

    def test_missing_failed_or_unreadable_job_status_cannot_close_issue(self):
        for job in ("source", "package", "desktop", "simulation"):
            for status in ("failure", "cancelled", "skipped", None):
                values = dict.fromkeys(("source", "package", "desktop", "simulation"), "success")
                if status is None:
                    del values[job]
                else:
                    values[job] = status
                with self.subTest(job=job, status=status):
                    self.check_report(prerequisites=json.dumps(values))
        for value in ("{}", "null", "[]", "invalid json"):
            with self.subTest(prerequisites=value):
                self.check_report(prerequisites=value)

    def test_bad_or_duplicate_result_reopens_issue_despite_other_passes(self):
        for value in ("not json", "[]", "null", '{"platform": []}',
                      '{"platform": "unknown", "passed": true}',
                      '{"platform": "windows-2025", "passed": true}'):
            with self.subTest(result=value):
                self.check_report(extra=value)


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
