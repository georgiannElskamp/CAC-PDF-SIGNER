import json
import base64
import os
from pathlib import Path
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "automation/controller"))
import dependencies
import maintenance
import pipeline
import pipeline_policy as policy
from test_pipeline import SHA, MAIN, STAMP, pull


class MonthlyCalendarTests(unittest.TestCase):
    def local(self, value):
        return datetime.fromisoformat(value).replace(tzinfo=maintenance.ZONE)

    def test_every_month_and_february_leap_year(self):
        for year in (2026, 2028, 2100):
            for month in range(1, 13):
                day = min(30, maintenance.calendar.monthrange(year, month)[1])
                at = self.local(f"{year}-{month:02d}-{day:02d}T02:00:00")
                self.assertTrue(maintenance.window(at)["active"])
                self.assertFalse(maintenance.window(at.replace(day=day - 1))["active"])

    def test_window_deadline_timezone_and_dst(self):
        for month, offset in ((1, 6), (7, 5)):
            start = datetime(2026, month, 30, 1 + offset, 17, tzinfo=timezone.utc)
            self.assertTrue(maintenance.window(start)["active"])
            self.assertFalse(maintenance.window(start.replace(minute=16))["active"])
            deadline = self.local(f"2026-{month:02d}-30T21:00:00")
            self.assertFalse(maintenance.window(deadline)["active"])
            self.assertTrue(maintenance.scheduled_allowed("schedule", deadline, closing=True))
        self.assertFalse(maintenance.window(self.local("2027-01-01T01:00:00"))["active"])

    def test_manual_runs_are_available_between_batches(self):
        at = self.local("2026-09-25T14:00:00")
        self.assertFalse(maintenance.scheduled_allowed("schedule", at))
        self.assertTrue(maintenance.scheduled_allowed("workflow_dispatch", at))

    def test_claim_is_durable_bounded_and_expires(self):
        state = Mock(data={})
        with patch.object(maintenance, "clock", return_value=self.local("2026-09-30T03:00:00")):
            self.assertTrue(maintenance.claim(state, "discovery"))
            self.assertFalse(maintenance.claim(state, "discovery"))
            self.assertTrue(maintenance.claim(state, "repair", limit=2))
            self.assertTrue(maintenance.claim(state, "repair", limit=2))
            self.assertFalse(maintenance.claim(state, "repair", limit=2))
        self.assertEqual(state.save.call_count, 3)
        with patch.object(maintenance, "clock", return_value=self.local("2026-09-30T21:01:00")):
            self.assertFalse(maintenance.claim(state, "unused"))

    def test_scheduled_pipeline_does_nothing_outside_window(self):
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": dependencies.PRIVATE, "GITHUB_EVENT_NAME": "schedule"}), \
             patch.object(sys, "argv", ["pipeline.py"]), \
             patch.object(maintenance, "clock", return_value=self.local("2026-09-25T03:00:00")), \
             patch.object(pipeline, "api") as api, patch.object(pipeline, "State") as state:
            pipeline.main()
        api.assert_not_called()
        state.assert_not_called()

    def test_delayed_dependency_jobs_cannot_scan_or_publish_after_deadline(self):
        with patch.dict(os.environ, {"GITHUB_EVENT_NAME": "schedule"}), \
             patch.object(maintenance, "clock", return_value=self.local("2026-09-30T21:01:00")), \
             patch.object(dependencies, "api") as api:
            with self.assertRaises(RuntimeError):
                dependencies.scan("python", Path("unused"), "unused")
            with self.assertRaises(RuntimeError):
                dependencies.publish("python", Path("unused"))
        api.assert_not_called()

    def test_event_pass_cannot_start_release_promotion_or_dependency_retargeting(self):
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": dependencies.PRIVATE, "GITHUB_EVENT_NAME": "workflow_dispatch"}), \
             patch.object(sys, "argv", ["pipeline.py", "--pr-only"]), \
             patch.object(pipeline, "State", return_value=Mock(data={"pulls": {}})), \
             patch.object(pipeline, "api", return_value={"login": policy.OWNER}), \
             patch.object(pipeline, "pages", return_value=[]) as pages, patch.object(pipeline, "promote") as promote:
            pipeline.main()
        promote.assert_not_called()
        self.assertTrue(all("base=research" in c.args[0] for c in pages.call_args_list))


class DependencyProposalTests(unittest.TestCase):
    def output(self, path="requirements-lock.txt", content="example==2.0.0\n", **extra):
        row = {"name": path, "directory": "/", "content": content, **extra}
        return json.dumps({"type": "create_pull_request", "data": {"base-commit-sha": SHA,
                           "updated-dependency-files": [row]}}) + "\n" + self.complete()

    def complete(self):
        return json.dumps({"type": "mark_as_processed", "data": {"base-commit-sha": SHA}})

    def test_real_pins_are_changed_without_modifying_dependency_names_or_commands(self):
        original = lambda path: ("example==1.0.0\n", "100644")
        value = dependencies.proposals(self.output(), "python", SHA, original)
        self.assertEqual(value, [{"requirements-lock.txt": "example==2.0.0\n"}])
        for content in ("malware==2.0.0\n", "example @ https://invalid.example/a\n", "example==2.0.0\n--extra-index-url evil\n"):
            with self.assertRaises(ValueError):
                dependencies.proposals(self.output(content=content), "python", SHA, original)

    def test_actions_allow_only_commit_pin_changes(self):
        before = "steps:\n  - uses: actions/checkout@" + SHA + " # v1\n"
        after = before.replace(SHA, MAIN).replace("# v1", "# v2")
        source = lambda path: (before, "100644")
        self.assertTrue(dependencies.proposals(self.output(".github/workflows/checks.yml", after), "actions", SHA, source))
        for changed in (after + "  - run: evil\n", after.replace("actions/checkout", "other/checkout"), after.replace(MAIN, "v2"),
                        after.replace("# v2", "# confidential data")):
            with self.assertRaises(ValueError):
                dependencies.proposals(self.output(".github/workflows/checks.yml", changed), "actions", SHA, source)

    def test_untrusted_paths_modes_deletes_and_stale_bases_are_rejected(self):
        source = lambda path: ("example==1.0.0\n", "100644")
        for path in ("../requirements-lock.txt", "/requirements-lock.txt", "requirements.txt", "a\\b", "plugin/code.js"):
            with self.assertRaises(ValueError):
                dependencies.proposals(self.output(path), "python", SHA, source)
        with self.assertRaises(ValueError):
            dependencies.proposals(self.output(deleted=True), "python", SHA, source)
        with self.assertRaises(ValueError):
            dependencies.proposals(self.output(), "python", MAIN, source)
        with self.assertRaises(ValueError):
            dependencies.proposals(self.output(), "python", SHA, lambda p: ("example==1.0.0\n", "120000"))

    def test_no_changes_partial_errors_and_multiple_groups(self):
        self.assertEqual(dependencies.proposals(self.complete(), "python", SHA, Mock()), [])
        source = lambda p: ("example==1.0.0\n", "100644")
        for output in ("", "invalid", self.output().splitlines()[0], self.output() + "\n" + self.output(), '{"type":"record_update_job_error"}'):
            with self.assertRaises(ValueError):
                dependencies.proposals(output, "python", SHA, source)

    def test_scan_job_is_grouped_uses_read_only_identity_and_pins_its_source(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(dependencies, "api", return_value={"object": {"sha": SHA}}) as api:
            dependencies.prepare("python", Path(folder))
            job = json.loads((Path(folder) / "job.json").read_text())
        self.assertEqual(job["job"]["source"]["commit"], SHA)
        self.assertEqual(job["job"]["source"]["branch"], "research")
        self.assertFalse(job["job"]["reject-external-code"])
        self.assertEqual(job["credentials"], [])
        self.assertEqual(job["job"]["dependency-groups"][0]["rules"], {"patterns": ["*"]})
        self.assertEqual(api.call_args.kwargs["credential"], "GH_TOKEN")
        self.assertNotIn("APP_TOKEN", json.dumps(job))

    def test_python_subprocess_never_receives_host_tokens(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(dependencies, "prepare"), \
             patch.dict(os.environ, {"GH_TOKEN": "synthetic", "APP_TOKEN": "synthetic", "PATH": "path"}), \
             patch.object(dependencies.subprocess, "run") as run:
            dependencies.scan("python", Path(folder), "dependabot")
        environment = run.call_args.kwargs["env"]
        self.assertNotIn("GH_TOKEN", environment)
        self.assertNotIn("APP_TOKEN", environment)
        self.assertEqual(environment["PATH"], "path")

    def test_publisher_dry_run_and_stale_base_do_not_write(self):
        def api(path, method="GET", body=None, **kwargs):
            self.assertEqual(method, "GET")
            if "/git/ref/heads/" in path:
                return {"object": {"sha": SHA}}
            if "/git/commits/" in path:
                return {"tree": {"sha": "tree"}}
            if "/git/trees/" in path:
                return {"tree": [{"type": "blob", "path": "requirements-lock.txt", "mode": "100644", "sha": "blob"}]}
            if "/git/blobs/" in path:
                return {"content": base64.b64encode(b"example==1.0.0\n").decode()}
            self.fail(path)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "metadata.json").write_text(json.dumps({"target": "python", "base": SHA}))
            (root / "result.jsonl").write_text(self.output())
            with patch.object(dependencies, "api", side_effect=api):
                dependencies.publish("python", root, dry_run=True)
            with patch.object(dependencies, "api", return_value={"object": {"sha": MAIN}}) as changed:
                with self.assertRaisesRegex(ValueError, "Base advanced"):
                    dependencies.publish("python", root)
                self.assertEqual(changed.call_count, 1)


class ExistingReviewTests(unittest.TestCase):
    def evidence(self):
        review = {"id": 4, "user": {"login": policy.CODEX}, "commit_id": SHA,
                  "submitted_at": STAMP, "state": "COMMENTED", "body": ""}
        summary = {"user": {"login": policy.CODEX}, "created_at": STAMP, "updated_at": STAMP,
                   "body": '<!-- codex-pull-request-review-summary -->\nCode Review | Completed | `' + SHA[:7] +
                           '` | PR opened <relative-time datetime="' + STAMP + '">'}
        clean = {**summary, "body": "Codex Review: Didn't find any major issues.\n**Reviewed commit:** `" + SHA[:10] + "`"}
        return [summary, clean], [review]

    def test_automatic_review_is_adopted_without_another_cloud_request(self):
        comments, reviews = self.evidence()
        state = Mock(); record = {}
        with patch.object(pipeline, "pages", side_effect=[comments, reviews, []]), patch.object(pipeline, "request_once") as request:
            self.assertEqual(pipeline.review(state, record, pull()), "clean")
        request.assert_not_called()
        self.assertTrue(record["review"]["automatic"])

    def test_old_foreign_or_unbound_reviews_do_not_satisfy_automatic_review(self):
        comments, reviews = self.evidence()
        self.assertIsNone(policy.automatic_review(MAIN, comments, reviews, []))
        self.assertIsNone(policy.automatic_review(SHA, comments, [], []))
        reviews[0]["user"]["login"] = "someone-else"
        self.assertIsNone(policy.automatic_review(SHA, comments, reviews, []))

    def test_current_findings_override_clean_summary(self):
        comments, reviews = self.evidence()
        inline = [{"user": {"login": policy.CODEX}, "original_commit_id": SHA, "pull_request_review_id": 4}]
        self.assertEqual(policy.automatic_review(SHA, comments, reviews, inline)[0], "findings")


if __name__ == "__main__":
    unittest.main()
