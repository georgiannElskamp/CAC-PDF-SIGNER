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
import github_api
import pipeline_policy as policy
from test_scheduler import scheduler
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

    def test_closing_report_does_not_reuse_last_months_success(self):
        with patch.object(maintenance, "clock", return_value=self.local("2026-09-30T21:07:00")):
            self.assertTrue(scheduler.report_stale("2026-08-30T22:00:00Z"))
            self.assertTrue(scheduler.report_stale("2026-09-29T22:00:00Z"))
            self.assertFalse(scheduler.report_stale("2026-09-30T12:00:00Z"))

    def test_report_uses_claimed_scan_not_a_later_noop_kickoff(self):
        at = self.local("2026-09-30T21:07:00")
        state = {"records": {}, "lastSuccessfulPoll": "2026-09-30T12:00:00Z", "deferredEditors": ["v9.4.0"]}
        monthly = {"cycles": {"2026-09": {"runs": {"discovery": "42"}}}}
        posted = []
        def api(path, method="GET", body=None, **kwargs):
            if "/contents/monthly.json" in path:
                return {"content": base64.b64encode(json.dumps(monthly).encode()).decode()}
            if path.endswith("/actions/runs/42"):
                return {"conclusion": "failure"}
            if "/pulls?" in path or "/issues?" in path:
                return []
            if method == "POST" and path.endswith("/issues"):
                posted.append(body)
                return {}
            self.fail(path)
        with patch.dict(os.environ, {"PIPELINE_ENABLED": "false"}), \
             patch.object(maintenance, "clock", return_value=at), \
             patch.object(scheduler, "load_state", return_value=(state, "state-sha")), \
             patch.object(scheduler, "api", side_effect=api):
            with self.assertRaises(SystemExit):
                scheduler.health()
        self.assertEqual(posted[0]["title"], "Monthly maintenance 2026-09")
        self.assertIn("dependency updates are not verified", posted[0]["body"])
        self.assertIn("Editor combinations deferred by the three-dispatch limit: v9.4.0.", posted[0]["body"])

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
        state = Mock(data={"pulls": {}, "fullReconciliation": {"runId": "old"}})
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": dependencies.PRIVATE, "GITHUB_EVENT_NAME": "workflow_dispatch"}), \
             patch.object(sys, "argv", ["pipeline.py", "--pr-only"]), \
             patch.object(pipeline, "State", return_value=state), \
             patch.object(pipeline, "api", return_value={"login": policy.OWNER}), \
             patch.object(pipeline, "pages", return_value=[]) as pages, patch.object(pipeline, "promote") as promote:
            pipeline.main()
        promote.assert_not_called()
        self.assertEqual(state.data["fullReconciliation"], {"runId": "old"})
        self.assertTrue(all("base=research" in c.args[0] for c in pages.call_args_list))

    def test_expired_writes_stop_at_the_shared_api_boundary(self):
        at = self.local("2026-09-30T21:01:00")
        with patch.dict(os.environ, {"GITHUB_EVENT_NAME": "schedule"}), \
             patch.object(maintenance, "clock", return_value=at), \
             patch.object(github_api.urllib.request, "urlopen") as network:
            for method in ("POST", "PUT", "PATCH", "DELETE"):
                with self.assertRaises(maintenance.DeadlinePassed):
                    github_api.api("/repos/example/repo/issues", method, {})
                with self.assertRaises(maintenance.DeadlinePassed):
                    scheduler.api("/repos/example/repo/issues", method, {})
        network.assert_not_called()

    def test_only_the_closing_report_can_write_after_deadline(self):
        response = Mock()
        response.__enter__ = Mock(return_value=Mock(read=Mock(return_value=b"{}")))
        response.__exit__ = Mock(return_value=False)
        with patch.dict(os.environ, {"GITHUB_EVENT_NAME": "schedule", "GH_TOKEN": "synthetic-test-token"}), \
             patch.object(scheduler, "PRIVATE", dependencies.PRIVATE), \
             patch.object(maintenance, "clock", return_value=self.local("2026-09-30T21:07:00")), \
             patch.object(scheduler.urllib.request, "urlopen", return_value=response) as network:
            scheduler.api("/repos/" + dependencies.PRIVATE + "/issues", "POST", {}, closing=True)
            with self.assertRaises(ValueError):
                scheduler.api("/repos/" + dependencies.PRIVATE + "/git/refs", "POST", {}, closing=True)
            with self.assertRaises(ValueError):
                scheduler.api("/repos/" + dependencies.PUBLIC + "/issues", "POST", {}, closing=True)
        self.assertEqual(network.call_count, 1)

    def test_deadline_crossed_while_reading_ci_cannot_post_a_status_or_repair(self):
        clock = Mock(return_value=self.local("2026-09-30T20:59:00"))
        def ci(value):
            clock.return_value = self.local("2026-09-30T21:01:00")
            return "pending", []
        state = Mock(data={"pulls": {}})
        with patch.dict(os.environ, {"GITHUB_EVENT_NAME": "schedule"}), \
             patch.object(maintenance, "clock", clock), patch.object(pipeline, "policy_changes", return_value=[]), \
             patch.object(pipeline, "ci_state", side_effect=ci), \
             patch.object(github_api.urllib.request, "urlopen") as network:
            with self.assertRaises(maintenance.DeadlinePassed):
                pipeline.reconcile_pull(state, pull())
        network.assert_not_called()
        state.save.assert_not_called()

    def test_full_pass_is_recorded_only_after_reconciliation_and_promotion_finish(self):
        for failure in (None, RuntimeError("incomplete"), maintenance.DeadlinePassed("deadline")):
            state = Mock(data={"pulls": {}})
            with patch.dict(os.environ, {"GITHUB_REPOSITORY": dependencies.PRIVATE, "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_RUN_ID": "42"}), \
                 patch.object(sys, "argv", ["pipeline.py"]), patch.object(pipeline, "State", return_value=state), \
                 patch.object(pipeline, "api", return_value={"login": policy.OWNER}), \
                 patch.object(pipeline, "pages", return_value=[]), patch.object(pipeline, "promote", side_effect=failure):
                if failure:
                    with self.assertRaises(type(failure)):
                        pipeline.main()
                else:
                    pipeline.main()
            self.assertEqual(state.data["fullReconciliation"]["runId"], "42")
            self.assertEqual("completedAt" in state.data["fullReconciliation"], failure is None)

    def test_report_rejects_pr_only_incomplete_or_unsuccessful_full_passes(self):
        stamp = "2026-09-30T12:00:00Z"
        with patch.object(maintenance, "clock", return_value=self.local("2026-09-30T21:07:00")), \
             patch.object(scheduler, "api", return_value={"conclusion": "success"}) as api:
            self.assertFalse(scheduler.full_reconciliation_current({"lastSuccessfulPoll": stamp}))
            self.assertFalse(scheduler.full_reconciliation_current({"fullReconciliation": {"runId": "42"}}))
            api.assert_not_called()
            value = {"fullReconciliation": {"runId": "42", "completedAt": stamp}}
            self.assertTrue(scheduler.full_reconciliation_current(value))
            api.return_value = {"conclusion": "failure"}
            self.assertFalse(scheduler.full_reconciliation_current(value))

    def test_report_read_scopes_and_branch_dry_run_permissions(self):
        root = Path(__file__).resolve().parents[1] / "automation/controller"
        health = (root / "health.yml").read_text().split("permissions:\n", 1)[1].split("jobs:\n", 1)[0]
        for permission in ("contents", "actions", "pull-requests", "statuses", "checks"):
            self.assertIn("  " + permission + ": read\n", health)
        discovery = (root / "discovery.yml").read_text()
        gate = discovery.split("  gate:\n", 1)[1].split("  claim:\n", 1)[0]
        claim = discovery.split("  claim:\n", 1)[1].split("  scan:\n", 1)[0]
        self.assertNotIn(": write", gate)
        self.assertIn("github.ref == 'refs/heads/main'", claim)
        self.assertIn("inputs.dry_run != true", claim)

    def test_exhausted_correction_budget_does_not_parse_an_unrequested_reply(self):
        record = {}
        def exhausted(*args):
            record["repair"] = {"state": "budget-exhausted", "created_at": STAMP}
        with patch.object(pipeline, "request_once", side_effect=exhausted), \
             patch.object(pipeline, "apply_repair") as apply, patch.object(pipeline, "status") as status:
            pipeline.repair(Mock(), {}, record, pull(), "findings")
        apply.assert_not_called()
        self.assertEqual(status.call_args.args[1], "pending")


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

    def test_controller_updates_only_identical_public_templates(self):
        before = "steps:\n  - uses: actions/checkout@" + SHA + " # v1\n"
        after = before.replace(SHA, MAIN).replace("# v1", "# v2")
        path = ".github/workflows/discovery.yml"
        template = "automation/controller/discovery.yml"
        calls = []
        def api(endpoint, method="GET", body=None, credential=None):
            private = endpoint.startswith("/repos/" + dependencies.PRIVATE + "/")
            if private:
                self.assertEqual(method, "GET")
                self.assertEqual(credential, "GH_TOKEN")
            else:
                self.assertEqual(credential, "APP_TOKEN")
            calls.append((endpoint, method, body))
            if "/git/ref/heads/" in endpoint:
                return {"object": {"sha": SHA if private else MAIN}}
            if method == "GET" and "/git/commits/" in endpoint:
                return {"tree": {"sha": "tree"}}
            if method == "GET" and "/git/trees/" in endpoint:
                return {"tree": [{"type": "blob", "path": path if private else template,
                                  "mode": "100644", "sha": "blob"}]}
            if "/git/blobs/" in endpoint:
                return {"content": base64.b64encode(before.encode()).decode()}
            if endpoint.endswith("/pulls"):
                return {"html_url": "https://github.com/" + dependencies.PUBLIC + "/pull/1"}
            return {"sha": "created"}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "metadata.json").write_text(json.dumps({"target": "controller", "base": SHA}))
            (root / "result.jsonl").write_text(self.output(path, after))
            with patch.object(dependencies, "api", side_effect=api), \
                 patch.object(dependencies, "pages", return_value=[]), \
                 patch.object(dependencies, "optional", return_value=None):
                dependencies.publish("controller", root)
        tree = next(body for endpoint, method, body in calls if endpoint.endswith("/git/trees") and method == "POST")
        self.assertEqual(tree["tree"][0]["path"], template)
        self.assertEqual(tree["tree"][0]["content"], after)
        pr = next(body for endpoint, method, body in calls if endpoint.endswith("/pulls") and method == "POST")
        self.assertEqual(pr["base"], "research")

    def test_controller_template_drift_and_symlinks_block_proposals(self):
        source = lambda p: ("original", "100644")
        files = {".github/workflows/discovery.yml": "new"}
        for value, mode in (("changed", "100644"), ("original", "120000")):
            with self.assertRaisesRegex(ValueError, "differs from its reviewed template"):
                dependencies.controller_templates(files, source, lambda p: (value, mode))


class ExistingReviewTests(unittest.TestCase):
    def evidence(self):
        submitted, completed = "2026-01-01T00:05:00Z", "2026-01-01T00:05:01Z"
        review = {"id": 4, "user": {"login": policy.CODEX}, "commit_id": SHA,
                  "submitted_at": submitted, "state": "COMMENTED", "body": ""}
        summary = {"user": {"login": policy.CODEX}, "created_at": STAMP, "updated_at": completed,
                   "body": '<!-- codex-pull-request-review-summary -->\nCode Review | Completed | `' + SHA[:7] +
                           '` | PR opened <relative-time datetime="' + STAMP + '">'}
        clean = {**summary, "created_at": completed,
                 "body": "Codex Review: Didn't find any major issues.\n**Reviewed commit:** `" + SHA[:10] + "`"}
        return [summary, clean], [review]

    def test_automatic_review_is_adopted_without_another_cloud_request(self):
        comments, reviews = self.evidence()
        state = Mock(); record = {}
        with patch.object(pipeline, "pages", side_effect=[comments, reviews, []]), patch.object(pipeline, "request_once") as request:
            self.assertEqual(pipeline.review(state, record, pull()), "clean")
        request.assert_not_called()
        self.assertTrue(record["review"]["automatic"])

    def test_each_native_trigger_can_precede_its_completed_exact_commit_review(self):
        for trigger in ("PR opened", "Ready for review", "New commits"):
            comments, reviews = self.evidence()
            comments[0]["body"] = comments[0]["body"].replace("PR opened", trigger)
            result, since = policy.automatic_review(SHA, comments, reviews, [])
            self.assertEqual(result, "clean")
            self.assertEqual(since, reviews[0]["submitted_at"])

    def test_automatic_completion_still_needs_current_completed_authentic_evidence(self):
        for mutation in (lambda c: c[0].update(updated_at=STAMP),
                         lambda c: c[0].update(body=c[0]["body"].replace("Completed", "Running")),
                         lambda c: c[0].update(body=c[0]["body"].replace(SHA[:7], MAIN[:7])),
                         lambda c: c[0].update(user={"login": "someone-else"}),
                         lambda c: c[1].update(created_at=STAMP),
                         lambda c: c[1].update(user={"login": "someone-else"})):
            comments, reviews = self.evidence()
            mutation(comments)
            self.assertEqual(policy.automatic_review(SHA, comments, reviews, [])[0], "pending")

    def test_manual_requests_keep_their_stricter_completion_time_boundary(self):
        comments, reviews = self.evidence()
        comments[0]["body"] = comments[0]["body"].replace("PR opened", "Manual request")
        request = {"created_at": reviews[0]["submitted_at"]}
        self.assertEqual(policy.review_result(SHA, request, comments, reviews, [], []), "pending")
        self.assertEqual(policy.review_result(SHA, request, comments, [], [], [], automatic=True), "pending")

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
