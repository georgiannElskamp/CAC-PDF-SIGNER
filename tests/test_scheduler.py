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
