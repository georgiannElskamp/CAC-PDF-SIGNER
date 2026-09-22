import unittest
from unittest.mock import Mock, patch

import linux_ui


class DesktopAvailabilityTests(unittest.TestCase):
    def test_missing_gtk_has_actionable_error(self):
        with patch("linux_ui.desktop_library", side_effect=OSError("missing library")):
            with self.assertRaisesRegex(RuntimeError, "GTK 3"):
                linux_ui.Dialogs()

    def test_unavailable_display_fails_without_opening_a_dialog(self):
        library = Mock()
        library.gtk_init_check.return_value = False
        with patch("linux_ui.desktop_library", return_value=library):
            with self.assertRaisesRegex(RuntimeError, "desktop display"):
                linux_ui.Dialogs()
        library.gtk_dialog_new.assert_not_called()
