import subprocess
import unittest
from unittest.mock import patch

import publish_release


class PublishReleaseTests(unittest.TestCase):
    def test_uncommitted_changes_prevent_remote_operations(self):
        with patch.object(publish_release, "command", return_value=" M README.md") as run:
            with self.assertRaisesRegex(ValueError, "Commit"):
                publish_release.publish("v0.6.0-dev")
        run.assert_called_once_with("git", "status", "--porcelain")

    def test_existing_tag_is_not_overwritten(self):
        with patch.object(publish_release, "command", side_effect=[
            "", "https://github.com/example/project.git", "{}", "existing-tag",
        ]) as run:
            with self.assertRaisesRegex(ValueError, "already exists"):
                publish_release.publish("v0.6.0-dev")
        self.assertFalse(any("push" in call.args for call in run.call_args_list))

    def test_failed_push_does_not_upload_or_publish(self):
        with patch.object(publish_release, "command", side_effect=[
            "", "https://github.com/example/project.git", "{}", "",
            subprocess.CalledProcessError(1, "git push"),
        ]) as run:
            with self.assertRaises(subprocess.CalledProcessError):
                publish_release.publish("v0.6.0-dev")
        self.assertFalse(any("release" in call.args for call in run.call_args_list))

    def test_upload_stays_draft_until_checks_run(self):
        with patch.object(publish_release, "command", side_effect=[
            "", "git@github.com:example/project.git", "{}", "", "", "", "",
        ]) as run:
            publish_release.publish("v0.6.0-dev")
        commands = [call.args for call in run.call_args_list]
        upload = next(args for args in commands if args[:3] == ("gh", "release", "create"))
        self.assertIn("--draft", upload)
        self.assertIn("--prerelease", upload)
        self.assertEqual(upload[upload.index("--repo") + 1], "example/project")
        self.assertEqual(commands[-1][:4], ("gh", "workflow", "run", "release.yml"))
