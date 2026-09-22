"""Only a complete component check with no alerts may close its tracking issue."""

from datetime import datetime, timezone
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import watch_components


class ComponentWatchTests(unittest.TestCase):
    def check_watch(self, *, newer=False, sdk_changed=False, advisory=False, unavailable=None):
        def api(path):
            if "/releases?" in path:
                if unavailable == "version":
                    raise OSError("Version feed unavailable")
                return [{"tag_name": "v1.0.1" if newer else "v1.0.0"}]
            if unavailable == "advisories":
                raise OSError("Advisory feed unavailable")
            return [{"published_at": datetime.now(timezone.utc).isoformat(),
                     "ghsa_id": "GHSA-test", "html_url": "https://example.org/advisory"}] if advisory else []

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "plugin").mkdir()
            (root / "plugin/plugins.js").write_bytes(b"bundled")
            item = {"name": "libusb", "version": "1.0.0", "repository": "libusb/libusb"}
            with (patch.object(watch_components, "ROOT", root),
                  patch.object(watch_components, "components", return_value=[item]),
                  patch.object(watch_components, "inventory", return_value={"components": []}),
                  patch.object(watch_components, "api", side_effect=api),
                  patch.object(watch_components, "upsert_issue") as issue,
                  patch("urllib.request.urlopen", return_value=io.BytesIO(b"new" if sdk_changed else b"bundled"),
                        side_effect=OSError("SDK unavailable") if unavailable == "sdk" else None)):
                if unavailable:
                    with self.assertRaises(SystemExit):
                        watch_components.watch(root / "report")
                else:
                    watch_components.watch(root / "report")
                attention = bool(newer or sdk_changed or advisory or unavailable)
                issue.assert_called_once()
                self.assertEqual(issue.call_args.kwargs["state"], "open" if attention else "closed")
                report = (root / "report/component-report.md").read_text()
                self.assertIn("Review required" if attention else "No changes detected", report)
                if unavailable:
                    self.assertIn("Incomplete checks", report)
                self.assertTrue((root / "report/components.cdx.json").is_file())

    def test_complete_current_check_closes_issue(self):
        self.check_watch()

    def test_each_actionable_change_opens_issue(self):
        for condition in ("newer", "sdk_changed", "advisory"):
            with self.subTest(condition=condition):
                self.check_watch(**{condition: True})

    def test_unavailable_feed_keeps_issue_open_and_fails_job(self):
        for feed in ("version", "sdk", "advisories"):
            with self.subTest(feed=feed):
                self.check_watch(unavailable=feed)
