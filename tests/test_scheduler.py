import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import automation
import test_automation

spec = importlib.util.spec_from_file_location("scheduler", Path(__file__).resolve().parents[1] / "automation/controller/watch.py")
scheduler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scheduler)


class SchedulerTests(unittest.TestCase):
    def editor_release(self, version):
        release = test_automation.ReleaseDiscoveryTests().release()
        release["tag_name"] = "v" + version
        for asset in release["assets"]:
            asset["browser_download_url"] = asset["browser_download_url"].replace("v9.4.0", "v" + version)
        return release

    def discover(self, releases, state, cycle="2026-09", force=False):
        commit, approved = "c" * 40, {"sha256": "b" * 64}
        dispatched = []
        def request(path, method="GET", body=None, **kwargs):
            if path.endswith("commits/main"):
                return {"sha": commit}
            if "/releases?" in path:
                return releases
            if path.endswith("compatibility-test.yml/dispatches"):
                dispatched.append(body["inputs"]["editor_tag"])
                return None
            self.fail("Unexpected API call: " + path)
        def file(path, sha):
            return approved if path.endswith("approved-plugin.json") else {"version": "9.4.0"}
        state["lastComponentDispatch"] = scheduler.now()
        with patch.object(scheduler, "api", side_effect=request), patch.object(scheduler, "public_file", side_effect=file), \
             patch.object(scheduler, "resolve_plugin", side_effect=lambda api, value: value), \
             patch.object(scheduler, "load_state", return_value=(state, "sha")), patch.object(scheduler, "save_state"), \
             patch.object(scheduler, "window", return_value={"id": cycle}):
            scheduler.watch(force=force)
        return dispatched

    def record(self, release, cycle="2026-08", conclusion="success"):
        key = scheduler.fingerprint(scheduler.manifest(release), {"sha256": "b" * 64}, "c" * 40)
        return key, {"status": "completed", "conclusion": conclusion, "cycle": cycle, "tag": release["tag_name"]}

    def test_newest_untested_editor_precedes_three_old_successful_controls(self):
        old = [self.editor_release(v) for v in ("9.4.0", "9.5.0", "9.6.0")]
        latest = self.editor_release("10.0.0.1")
        state = {"records": dict(self.record(r) for r in old)}
        dispatched = self.discover([*old, latest, latest], state)
        self.assertEqual(dispatched[0], "v10.0.0.1")
        self.assertEqual(len(dispatched), 3)
        self.assertEqual(len(set(dispatched)), 3)
        self.assertEqual(state["deferredEditors"], ["v9.4.0"])

    def test_monthly_controls_rotate_and_never_overtake_untested_editors(self):
        releases = [self.editor_release(v) for v in ("9.4.0", "9.5.0", "9.6.0", "9.7.0")]
        state = {"records": dict(self.record(r) for r in releases)}
        self.assertEqual(self.discover(releases, state), ["v9.7.0", "v9.6.0", "v9.5.0"])
        for record in state["records"].values():
            record.update(status="completed", conclusion="success")
        next_cycle = self.discover(releases, state, cycle="2026-10")
        self.assertEqual(next_cycle[0], "v9.4.0")

    def test_more_than_three_new_releases_leave_an_explicit_deferred_list(self):
        releases = [self.editor_release(v) for v in ("9.4.0", "9.5.0", "9.6.0", "10.0.0.1")]
        state = {"records": {}}
        self.assertEqual(self.discover(releases, state), ["v10.0.0.1", "v9.6.0", "v9.5.0"])
        self.assertEqual(state["deferredEditors"], ["v9.4.0"])

    def test_four_part_release_precedes_its_shorter_version_prefixes(self):
        releases = [self.editor_release(v) for v in ("10.0", "10.0.0", "10.0.0.1")]
        self.assertEqual(self.discover(releases, {"records": {}}), ["v10.0.0.1", "v10.0.0", "v10.0"])

    def test_controller_and_public_workflow_agree_on_fingerprint(self):
        release = test_automation.ReleaseDiscoveryTests().release()
        approved = {"sha256": "b" * 64}
        editor = scheduler.manifest(release)
        self.assertEqual(editor, automation.editor_manifest(release))
        self.assertEqual(scheduler.fingerprint(editor, approved, "c" * 40),
                         automation.combination(editor, approved, "c" * 40))

    def test_completed_combination_is_not_dispatched_again(self):
        release = test_automation.ReleaseDiscoveryTests().release()
        approved = {"sha256": "b" * 64}
        commit = "c" * 40
        key = scheduler.fingerprint(scheduler.manifest(release), approved, commit)
        state = {"records": {key: {"status": "completed", "conclusion": "failure"}}, "lastComponentDispatch": scheduler.now()}
        def request(path, *args, **kwargs):
            if path.endswith("commits/main"):
                return {"sha": commit}
            if "/releases?" in path:
                return [release]
            self.fail("Unexpected write or dispatch: " + path)
        def file(path, sha):
            return approved if path.endswith("approved-plugin.json") else {"version": "9.4.0"}
        with patch.object(scheduler, "api", side_effect=request), \
             patch.object(scheduler, "public_file", side_effect=file), \
             patch.object(scheduler, "resolve_plugin", side_effect=lambda api, value: value), \
             patch.object(scheduler, "load_state", return_value=(state, "sha")), \
             patch.object(scheduler, "save_state"):
            scheduler.watch()
        self.assertEqual(state["records"][key]["conclusion"], "failure")

    def test_dispatch_intent_survives_ambiguous_network_response(self):
        release = test_automation.ReleaseDiscoveryTests().release()
        state = {"records": {}}
        saved = []
        def request(path, *args, **kwargs):
            if path.endswith("commits/main"):
                return {"sha": "c" * 40}
            if "/releases?" in path:
                return [release]
            if path.endswith("dispatches"):
                raise TimeoutError("Simulated interrupted acknowledgement")
            self.fail("Unexpected request: " + path)
        def file(path, sha):
            return {"sha256": "b" * 64} if path.endswith("approved-plugin.json") else {"version": "9.4.0"}
        with patch.object(scheduler, "api", side_effect=request), \
             patch.object(scheduler, "public_file", side_effect=file), \
             patch.object(scheduler, "resolve_plugin", side_effect=lambda api, value: value), \
             patch.object(scheduler, "load_state", return_value=(state, "sha")), \
             patch.object(scheduler, "save_state", side_effect=lambda value: saved.append(json.loads(json.dumps(value)))):
            with self.assertRaises(TimeoutError):
                scheduler.watch()
        self.assertEqual(len(saved), 1)
        self.assertEqual(next(iter(saved[0]["records"].values()))["status"], "dispatching")
