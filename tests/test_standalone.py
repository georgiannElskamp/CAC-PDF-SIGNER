"""The standalone process must retain completed signatures across Save As retries."""

import base64
import hashlib
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

from standalone_worker import SigningSession


class StandaloneRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.session = SigningSession(self.root, self.root / "unused.exe")
        self.session.output.mkdir()
        self.original = self.root / "original.pdf"
        self.original.write_bytes(b"%PDF-test original")
        self.content = self.original.read_bytes() + b" signed bytes"
        self.recovery = self.session.output / "recovery.pdf"
        self.recovery.write_bytes(self.content)
        self.identifier = "0123456789ab"
        self.metadata = dict(
            name="original.pdf",
            source=str(self.original),
            sourceHash=hashlib.sha256(self.original.read_bytes()).hexdigest(),
            field="PreparedBy",
            recoveryName=self.recovery.name,
            sha256=hashlib.sha256(self.content).hexdigest(),
            savedPath="",
        )
        self.session.record(self.identifier, self.metadata)
        self.request = dict(
            op="sign",
            pdf=base64.b64encode(self.original.read_bytes()).decode(),
            field="PreparedBy",
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_cancel_then_new_process_retries_without_card(self):
        with (
            patch("standalone_worker.signing_lock", return_value=nullcontext()),
            patch("standalone_worker.emit"),
            patch(
                "signing.certificates",
                side_effect=AssertionError("Card must not be accessed"),
            ),
            patch("save_dialog.choose_pdf", return_value=""),
        ):
            result = self.session.run(self.request)
            self.assertTrue(result["cancelled"])
        restarted = SigningSession(self.root, self.root / "unused.exe")
        target = self.root / "chosen.pdf"
        with (
            patch("standalone_worker.signing_lock", return_value=nullcontext()),
            patch("standalone_worker.emit"),
            patch(
                "signing.certificates",
                side_effect=AssertionError("Card must not be accessed"),
            ),
            patch("save_dialog.choose_pdf", return_value=str(target)),
        ):
            result = restarted.run(self.request)
        self.assertTrue(result["saved"])
        self.assertTrue(result["integrityVerified"])
        self.assertEqual(result["path"], str(target.resolve()))
        self.assertEqual(target.read_bytes(), self.content)
        self.assertIsNone(restarted.pending(self.metadata["sourceHash"], "PreparedBy"))

    def test_tampered_recovery_does_not_resign(self):
        self.recovery.write_bytes(b"changed")
        with patch(
            "signing.certificates", side_effect=AssertionError("Must not re-sign")
        ):
            with self.assertRaisesRegex(ValueError, "changed"):
                self.session.sign(self.request)

    def test_original_and_failed_destination_preserve_recovery(self):
        with self.assertRaisesRegex(ValueError, "preserve the original"):
            self.session.save(self.identifier, self.metadata, self.original)
        with self.assertRaises(OSError):
            self.session.save(
                self.identifier, self.metadata, self.root / "missing/chosen.pdf"
            )
        self.assertEqual(self.recovery.read_bytes(), self.content)
        self.assertIsNotNone(
            self.session.pending(self.metadata["sourceHash"], "PreparedBy")
        )

    def test_failed_dialog_preserves_recovery(self):
        with (
            patch("standalone_worker.signing_lock", return_value=nullcontext()),
            patch("standalone_worker.emit"),
            patch("save_dialog.choose_pdf", side_effect=RuntimeError("Dialog failed")),
        ):
            with self.assertRaisesRegex(RuntimeError, "Dialog failed"):
                self.session.run(self.request)
        self.assertIsNotNone(
            self.session.pending(self.metadata["sourceHash"], "PreparedBy")
        )
