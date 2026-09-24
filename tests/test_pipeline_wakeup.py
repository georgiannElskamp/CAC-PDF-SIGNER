import os
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "automation/controller"))
import pipeline
import pipeline_policy as policy
import wakeup

SHA = "a" * 40


def pull():
    return {"number": 26, "state": "open", "draft": False, "user": {"login": policy.APP},
            "base": {"ref": "research", "sha": "b" * 40},
            "head": {"ref": "automation/sync-release-example", "sha": SHA,
                     "repo": {"full_name": policy.PUBLIC}}}


def activity():
    return {"repository": {"full_name": policy.PUBLIC}, "action": "completed",
            "workflow_run": {"path": ".github/workflows/pipeline-activity.yml",
                             "event": "pull_request_review", "display_title": "Research PR 26",
                             "head_repository": {"full_name": policy.PUBLIC}}}


class WakeupTests(unittest.TestCase):
    @patch.dict(os.environ, {"CONTROLLER_DISPATCH_TOKEN": "synthetic-test-value"})
    def test_approval_wakes_a_full_sweep_on_private_main(self):
        with patch.object(wakeup, "api", side_effect=[pull(), None]) as api:
            self.assertTrue(wakeup.wake("workflow_run", activity()))
        self.assertEqual(api.call_args_list[0].kwargs["credential"], "GH_TOKEN")
        self.assertEqual(api.call_args.args,
                         (f"/repos/{policy.OWNER}/cac-pdf-signer-automation/actions/workflows/pipeline.yml/dispatches",
                          "POST", {"ref": "main", "inputs": {"dry_run": "false", "pull": "",
                                                               "release_type": "auto", "event_wakeup": "true"}}))
        self.assertEqual(api.call_args.kwargs["credential"], "CONTROLLER_DISPATCH_TOKEN")

    def test_foreign_repositories_and_workflows_cannot_wake_controller(self):
        for field, value in (("path", ".github/workflows/other.yml"), ("event", "push"),
                             ("display_title", "Research PR 26; echo unsafe"),
                             ("head_repository", {"full_name": "external/fork"})):
            event = activity(); event["workflow_run"][field] = value
            with patch.object(wakeup, "api") as api:
                self.assertFalse(wakeup.wake("workflow_run", event))
                api.assert_not_called()
        event = activity(); event["repository"]["full_name"] = "external/fork"
        with patch.object(wakeup, "api") as api:
            self.assertFalse(wakeup.wake("workflow_run", event))
            api.assert_not_called()

    def test_live_pr_eligibility_is_checked_before_dispatch(self):
        for mutate in (lambda p: p["base"].update(ref="main"),
                       lambda p: p["head"]["repo"].update(full_name="external/fork"),
                       lambda p: p.update(state="closed"), lambda p: p.update(draft=True),
                       lambda p: p["user"].update(login="unknown"),
                       lambda p: p["head"].update(ref="release-verification")):
            value = pull(); mutate(value)
            with patch.object(wakeup, "api", return_value=value) as api:
                self.assertFalse(wakeup.wake("workflow_run", activity()))
                self.assertEqual(api.call_count, 1)

    def test_codex_summary_edits_and_owner_comments_wake_review(self):
        event = {"repository": {"full_name": policy.PUBLIC}, "action": "edited",
                 "issue": {"number": 26, "pull_request": {"url": "synthetic"}},
                 "comment": {"user": {"login": policy.CODEX}}}
        self.assertEqual(wakeup.pull_numbers("issue_comment", event), [26])
        event["comment"]["user"]["login"] = policy.OWNER
        self.assertEqual(wakeup.pull_numbers("issue_comment", event), [26])
        event["comment"]["user"]["login"] = "unknown"
        self.assertEqual(wakeup.pull_numbers("issue_comment", event), [])
        event["comment"]["user"]["login"] = policy.CODEX
        del event["issue"]["pull_request"]
        self.assertEqual(wakeup.pull_numbers("issue_comment", event), [])

    def test_ci_completion_uses_current_pr_and_missing_associations_fall_back(self):
        event = activity()
        event["workflow_run"].update(path=".github/workflows/pr-build.yml", event="pull_request",
                                     head_sha=SHA, pull_requests=[{"number": 26}])
        self.assertEqual(wakeup.pull_numbers("workflow_run", event), [26])
        event["workflow_run"]["pull_requests"] = []
        with patch.object(wakeup, "api", return_value=[{"number": 26}]) as api:
            self.assertEqual(wakeup.pull_numbers("workflow_run", event), [26])
            api.assert_called_once_with(f"/repos/{policy.PUBLIC}/commits/{SHA}/pulls", credential="GH_TOKEN")
        event["workflow_run"]["head_sha"] = "../main"
        with patch.object(wakeup, "api") as api:
            self.assertEqual(wakeup.pull_numbers("workflow_run", event), [])
            api.assert_not_called()

    def test_missing_dispatch_secret_fails_clearly_without_writing(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(wakeup, "api", return_value=pull()) as api:
            with self.assertRaisesRegex(RuntimeError, "CONTROLLER_DISPATCH_TOKEN"):
                wakeup.wake("workflow_run", activity())
            self.assertEqual(api.call_count, 1)

    @patch.dict(os.environ, {"CONTROLLER_DISPATCH_TOKEN": "synthetic-test-value"})
    def test_uncertain_dispatch_is_not_retried(self):
        with patch.object(wakeup, "api", side_effect=[pull(), TimeoutError("synthetic")]) as api:
            with self.assertRaises(TimeoutError):
                wakeup.wake("workflow_run", activity())
            self.assertEqual(api.call_count, 2)

    def test_manual_dispatch_accepts_only_a_pr_number(self):
        event = {"repository": {"full_name": policy.PUBLIC}, "inputs": {"pull": "26"}}
        self.assertEqual(wakeup.pull_numbers("workflow_dispatch", event), [26])
        for number in ("", "0", "-1", "1;echo unsafe", True):
            event["inputs"]["pull"] = number
            with self.assertRaises(ValueError):
                wakeup.pull_numbers("workflow_dispatch", event)

    def test_credential_workflow_never_runs_from_pr_events_or_source(self):
        workflow = (ROOT / ".github/workflows/pipeline-wakeup.yml").read_text(encoding="utf-8")
        self.assertNotIn("pull_request_target:", workflow)
        self.assertNotIn("pull_request_review:", workflow)
        self.assertIn("ref: refs/heads/main", workflow)
        self.assertIn("environment: controller-dispatch", workflow)
        signal = (ROOT / ".github/workflows/pipeline-activity.yml").read_text(encoding="utf-8")
        self.assertIn("permissions: {}", signal)
        self.assertNotIn("secrets.", signal)
        self.assertNotIn("checkout", signal)


class ResearchGateTests(unittest.TestCase):
    def process(self, value, latest=None, review="clean"):
        state = Mock(data={"pulls": {}})
        with patch.object(pipeline, "policy_changes", return_value=[]), \
             patch.object(pipeline, "ci_state", return_value=("passed", [])), \
             patch.object(pipeline, "review", return_value=review), \
             patch.object(pipeline, "api", return_value=latest or value) as api, \
             patch.object(pipeline, "status") as status:
            pipeline.process_pull(state, value)
        return api, status

    def test_hold_label_allows_manual_merge_after_complete_evidence(self):
        value = pull(); value["labels"] = [{"name": "automation:no-merge"}]
        api, status = self.process(value)
        self.assertEqual(status.call_args.args[1], "success")
        self.assertIn("manual merge", status.call_args.args[2])
        self.assertFalse(any("/merge" in call.args[0] for call in api.call_args_list))

    def test_hold_added_during_review_prevents_automatic_merge(self):
        latest = pull(); latest["labels"] = [{"name": "automation:no-merge"}]
        api, status = self.process(pull(), latest)
        self.assertEqual(status.call_args.args[1], "success")
        self.assertFalse(any("/merge" in call.args[0] for call in api.call_args_list))

    def test_changed_base_or_head_never_gets_success(self):
        for side in ("base", "head"):
            latest = pull(); latest[side]["sha"] = "c" * 40
            api, status = self.process(pull(), latest)
            self.assertFalse(any(call.args[1] == "success" for call in status.call_args_list))
            self.assertFalse(any("/merge" in call.args[0] for call in api.call_args_list))

    def test_status_links_to_controller_run(self):
        with patch.dict(os.environ, {"GITHUB_RUN_ID": "1234"}), patch.object(pipeline, "api") as api:
            pipeline.status(SHA, "pending", "Review pending")
        self.assertEqual(api.call_args.args[2]["target_url"],
                         f"https://github.com/{policy.OWNER}/cac-pdf-signer-automation/actions/runs/1234")

    def test_sync_creation_posts_pending_review_immediately(self):
        state = Mock(data={"pulls": {}})
        def api(path, method="GET", body=None):
            if "/compare/" in path:
                return {"ahead_by": 1}
            if method == "POST" and path.endswith("/pulls"):
                return {"number": 26}
            if method == "POST" and path.endswith("/git/refs"):
                return {}
            self.fail(path)
        with patch.object(pipeline, "head", side_effect=["b" * 40, SHA]), \
             patch.object(pipeline, "optional", return_value=None), \
             patch.object(pipeline, "pages", return_value=[]), \
             patch.object(pipeline, "api", side_effect=api), patch.object(pipeline, "status") as status:
            pipeline.promote(state)
        status.assert_called_once_with(SHA, "pending", "Waiting for the sync PR tests and Codex review")
