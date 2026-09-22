"""Regression checks for durable recovery and saving exact signed bytes."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import helper


class SaveRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.output = self.root / "Signed"
        self.output.mkdir()
        self.original = self.root / "test.pdf"
        self.original.write_bytes(b"%PDF-test original")
        self.recovery = self.output / "test-signed.pdf"
        self.content = self.original.read_bytes() + b" signed incremental bytes"
        self.recovery.write_bytes(self.content)
        self.identifier = "0123456789ab"
        self.scope = patch.multiple(
            helper, OUTPUT=self.output, OUTPUTS={}, OUTPUT_META={}
        )
        self.scope.start()
        helper.OUTPUTS[self.identifier] = self.recovery
        helper.record_output(
            self.identifier,
            {
                "recoveryName": self.recovery.name,
                "sha256": hashlib.sha256(self.content).hexdigest(),
                "source": str(self.original),
                "name": self.original.name,
                "field": "PreparedBy",
                "sourceHash": hashlib.sha256(self.original.read_bytes()).hexdigest(),
                "savedPath": "",
            },
        )

    def tearDown(self):
        self.scope.stop()
        self.temp.cleanup()

    def test_recovery_survives_restart(self):
        helper.OUTPUT_META.clear()
        helper.OUTPUTS.clear()
        helper.load_outputs()
        self.assertTrue(
            helper.output_result(self.identifier, recovered=True)["recovered"]
        )
        self.assertEqual(helper.OUTPUT_META[self.identifier]["savedPath"], "")

    def test_cancel_then_retry_saves_exact_bytes(self):
        with patch.object(
            helper.subprocess,
            "run",
            return_value=SimpleNamespace(returncode=0, stdout='{"path":""}'),
        ):
            self.assertTrue(helper.save_with_dialog(self.identifier)["cancelled"])
        self.assertEqual(helper.OUTPUT_META[self.identifier]["savedPath"], "")
        target = self.root / "chosen.pdf"
        with patch.object(
            helper.subprocess,
            "run",
            return_value=SimpleNamespace(
                returncode=0, stdout=json.dumps({"path": str(target)})
            ),
        ):
            helper.save_with_dialog(self.identifier)
        self.assertEqual(target.read_bytes(), self.content)
        self.assertEqual(self.recovery.read_bytes(), self.content)
        self.assertEqual(helper.OUTPUT_META[self.identifier]["savedPath"], str(target))

    def test_failed_chooser_keeps_recovery_and_releases_lock(self):
        with patch.object(
            helper.subprocess,
            "run",
            return_value=SimpleNamespace(
                returncode=1, stdout='{"error":"chooser failed"}'
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "chooser failed"):
                helper.save_with_dialog(self.identifier)
        self.assertFalse(helper.SAVE_LOCK.locked())
        self.assertEqual(helper.OUTPUT_META[self.identifier]["savedPath"], "")
        self.assertEqual(self.recovery.read_bytes(), self.content)

    def test_original_and_tampered_recovery_rejected(self):
        with self.assertRaisesRegex(ValueError, "preserve the original"):
            helper.save_output(self.identifier, self.original)
        self.recovery.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "changed"):
            helper.save_output(self.identifier, self.root / "bad.pdf")
        self.assertFalse((self.root / "bad.pdf").exists())

    def test_save_failure_keeps_pending_status(self):
        with self.assertRaises(OSError):
            helper.save_output(self.identifier, self.root / "missing-folder/chosen.pdf")
        self.assertEqual(helper.OUTPUT_META[self.identifier]["savedPath"], "")
        self.assertEqual(self.recovery.read_bytes(), self.content)


if __name__ == "__main__":
    unittest.main()
