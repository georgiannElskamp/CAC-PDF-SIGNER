import json
import unittest
from pathlib import Path
from unittest.mock import patch

import publish_release


ROOT = Path(__file__).resolve().parents[1]


class PublishReleaseTests(unittest.TestCase):
    def test_local_publication_cannot_bypass_verification_pr(self):
        with patch.object(publish_release, 'command') as command:
            with self.assertRaisesRegex(ValueError, 'release-verification PR'):
                publish_release.publish('v1.0.0')
            command.assert_not_called()

    def test_current_release_documentation_is_final_and_installable(self):
        version = json.loads((ROOT / 'plugin/config.json').read_text(encoding='utf-8'))['version']
        installation = (ROOT / 'docs/INSTALLATION.md').read_text(encoding='utf-8')
        notes = (ROOT / 'docs/RELEASE_NOTES.md').read_text(encoding='utf-8')

        self.assertIn('/releases/latest', installation)
        self.assertIn(f'Release {version}', notes)
        self.assertNotIn('release candidate', notes.lower())
        self.assertNotIn('pending', notes.lower())
