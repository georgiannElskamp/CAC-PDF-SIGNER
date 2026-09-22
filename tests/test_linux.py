import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

import linux_card
from runtime_config import state_directory


@unittest.skipUnless(sys.platform == "linux", "Linux runtime")
class LinuxRuntimeTests(unittest.TestCase):
    def test_xdg_state_without_windows_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"XDG_DATA_HOME": directory}, clear=True):
                self.assertEqual(state_directory(), Path(directory) / "ONLYOFFICE-CAC-Signature")

    def test_system_reader_socket_is_reused_and_environment_restored(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(linux_card, "available_socket", return_value=True), patch.object(linux_card.subprocess, "Popen") as spawn:
            with linux_card.reader_runtime():
                self.assertEqual(os.environ["PCSCLITE_CSOCK_NAME"], "/run/pcscd/pcscd.comm")
            self.assertNotIn("PCSCLITE_CSOCK_NAME", os.environ)
            spawn.assert_not_called()

    def test_private_reader_stops_on_signing_failure(self):
        child = Mock()
        child.poll.return_value = None
        observed = []
        def available(path):
            return str(path).startswith(tempfile.gettempdir() + "/cac-pcsc-")
        with patch.dict(os.environ, {}, clear=True), patch.object(linux_card, "available_socket", side_effect=available), patch.object(linux_card.subprocess, "Popen", return_value=child) as spawn:
            with self.assertRaisesRegex(ValueError, "sign failed"):
                with linux_card.reader_runtime():
                    channel = Path(os.environ["PCSCLITE_CSOCK_NAME"])
                    observed.append(channel.parent)
                    self.assertEqual(channel.parent.stat().st_mode & 0o777, 0o700)
                    self.assertEqual(spawn.call_args.kwargs["env"]["CAC_PCSC_DIR"], str(channel.parent))
                    raise ValueError("sign failed")
            child.terminate.assert_called_once()
            child.wait.assert_called_once_with(timeout=3)
            self.assertFalse(observed[0].exists())
            self.assertNotIn("PCSCLITE_CSOCK_NAME", os.environ)

    def test_signing_lock_rejects_another_tab(self):
        from standalone_worker import signing_lock
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"CAC_SIGNATURE_HOME": directory}):
            with signing_lock():
                with self.assertRaisesRegex(ValueError, "already open"):
                    with signing_lock():
                        self.fail("Concurrent signing was allowed")
