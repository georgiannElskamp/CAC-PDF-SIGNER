"""Native bridge message framing tests."""

import json
import struct
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import signing


class BridgeTests(unittest.TestCase):
    def test_certificate_request_and_response_framing(self):
        response = json.dumps({"certificates": []}).encode()
        with patch.object(
            signing.subprocess,
            "run",
            return_value=SimpleNamespace(
                returncode=0, stdout=struct.pack("<I", len(response)) + response
            ),
        ) as execute, patch("windows_csp.certificates", return_value=[]):
            self.assertEqual(signing.certificates(Path("bridge.exe")), [])
        payload = execute.call_args.kwargs["input"]
        self.assertEqual(struct.unpack("<I", payload[:4])[0], len(payload) - 4)
        self.assertEqual(json.loads(payload[4:]), {"cmd": "listCertificates"})

    def test_incomplete_native_reply_is_rejected(self):
        with patch.object(
            signing.subprocess,
            "run",
            return_value=SimpleNamespace(
                returncode=0, stdout=struct.pack("<I", 100) + b"{}"
            ),
        ):
            with self.assertRaisesRegex(
                RuntimeError, "Invalid signing bridge response"
            ):
                signing.certificates(Path("bridge.exe"))
