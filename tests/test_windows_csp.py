"""Exercise legacy RSA signing with an ephemeral software provider, never a card."""

import ctypes as C
from ctypes import wintypes as W
import hashlib
import struct
import sys
import unittest

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from windows_csp import crypto_api, sign_hash


@unittest.skipUnless(sys.platform == "win32", "Windows CryptoAPI")
class LegacyProviderTests(unittest.TestCase):
    def test_sha256_signature_matches_ephemeral_rsa_key(self):
        private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        numbers = private.private_numbers()
        public = numbers.public_numbers
        blob = struct.pack("<BBHIIII", 7, 2, 0, 0x2400, 0x32415352, 2048, public.e)
        for value, size in ((public.n, 256), (numbers.p, 128), (numbers.q, 128),
                            (numbers.dmp1, 128), (numbers.dmq1, 128), (numbers.iqmp, 128), (numbers.d, 256)):
            blob += value.to_bytes(size, "little")
        api = crypto_api()
        handle = C.c_void_p
        api.CryptAcquireContextW.argtypes = [C.POINTER(handle), W.LPCWSTR, W.LPCWSTR, W.DWORD, W.DWORD]
        api.CryptImportKey.argtypes = [handle, C.c_void_p, W.DWORD, handle, W.DWORD, C.POINTER(handle)]
        api.CryptDestroyKey.argtypes = [handle]
        provider, key = handle(), handle()
        self.assertTrue(api.CryptAcquireContextW(C.byref(provider), None,
            "Microsoft Enhanced RSA and AES Cryptographic Provider", 24, 0xF0000000))
        try:
            buffer = C.create_string_buffer(blob)
            self.assertTrue(api.CryptImportKey(provider, buffer, len(blob), None, 0, C.byref(key)))
            content = b"Synthetic provider test; no real card or certificate."
            signature = sign_hash(api, provider, 2, hashlib.sha256(content).digest())
            private.public_key().verify(signature, content, padding.PKCS1v15(), hashes.SHA256())
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                sign_hash(api, provider, 2, b"short")
        finally:
            if key:
                api.CryptDestroyKey(key)
            api.CryptReleaseContext(provider, 0)
