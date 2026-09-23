import unittest
from unittest.mock import patch
import publish_release


class PublishReleaseTests(unittest.TestCase):
    def test_local_publication_cannot_bypass_verification_pr(self):
        with patch.object(publish_release, 'command') as command:
            with self.assertRaisesRegex(ValueError, 'release-verification PR'):
                publish_release.publish('v1.0.0')
            command.assert_not_called()
