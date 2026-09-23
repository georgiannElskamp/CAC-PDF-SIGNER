"""The standalone process must retain completed signatures across Save As retries."""

import base64
import hashlib
import tempfile
import unittest
import sys
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

from standalone_worker import SigningSession, valid_windows_destination


class StandaloneRecoveryTests(unittest.TestCase):
    def setUp(self):
        desktop = patch("save_dialog.check_desktop")
        self.desktop = desktop.start()
        self.addCleanup(desktop.stop)
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "Example User"
        self.root.mkdir()
        self.session = SigningSession(self.root, self.root / "unused.exe")
        self.session.output.mkdir()
        self.original = self.root / "original document.pdf"
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
        target = self.root / "chosen document.pdf"
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

    def test_unwritable_recovery_is_rejected_before_card_access(self):
        session = SigningSession(self.root / "blocked", self.root / "unused.exe")
        session.directory.mkdir()
        session.output.write_bytes(b"conflicting file")
        with patch("platform_card.card_signer") as card:
            with self.assertRaisesRegex(RuntimeError, "before signing"):
                session.sign(self.request)
            card.assert_not_called()

    def test_onlyoffice_form_reads_saved_path_without_encoded_pdf(self):
        request = {
            "op": "sign", "kind": "onlyoffice-form", "field": "Signature1",
            "sourcePath": str(self.original), "name": self.original.name,
        }
        signer = object()
        with patch("platform_card.card_signer", return_value=nullcontext(signer)) as card, \
             patch("signing.sign_bytes", return_value=self.content) as sign:
            _, metadata, recovered = self.session.sign(request)
        self.assertFalse(recovered)
        card.assert_called_once()
        sign.assert_called_once_with(self.original.read_bytes(), signer, {
            "field": "Signature1", "kind": "onlyoffice-form",
        })
        self.assertEqual(metadata["source"], str(self.original))
        with patch("platform_card.card_signer") as card:
            with self.assertRaisesRegex(ValueError, "saved local PDF"):
                self.session.sign({**request, "sourcePath": "form.pdf"})
            card.assert_not_called()

    def test_desktop_failure_is_rejected_before_card_access(self):
        self.desktop.side_effect = RuntimeError("Desktop is unavailable")
        with patch("standalone_worker.signing_lock", return_value=nullcontext()), patch("platform_card.card_signer") as card:
            with self.assertRaisesRegex(RuntimeError, "Desktop is unavailable"):
                self.session.run(self.request)
            card.assert_not_called()

    def test_windows_path_forms_preserve_alternate_stream_rejection(self):
        for value in (r"C:\Example User\signed.pdf", r"\\server\share\signed.pdf",
                      r"\\?\C:\Example User\signed.pdf", r"\\?\UNC\server\share\signed.pdf",
                      r"\\files.example.test\share\signed.pdf", r"\\?\UNC\files.example.test\share\signed.pdf"):
            self.assertTrue(valid_windows_destination(value), value)
        for value in (r"C:relative.pdf", r"\relative.pdf", r"C:\signed.pdf:stream.pdf",
                      r"\\?\C:\signed.pdf:stream.pdf", r"\\.\device\signed.pdf",
                      r"\\?\GLOBALROOT\Device\signed.pdf"):
            self.assertFalse(valid_windows_destination(value), value)

    @unittest.skipUnless(sys.platform == "win32", "Windows extended paths")
    def test_extended_windows_save_and_original_alias(self):
        original = "\\\\?\\" + str(self.original.resolve())
        with self.assertRaisesRegex(ValueError, "preserve the original"):
            self.session.save(self.identifier, self.metadata, original)
        target = self.root / "extended path.pdf"
        self.session.save(self.identifier, self.metadata, "\\\\?\\" + str(target.resolve()))
        self.assertEqual(target.read_bytes(), self.content)
