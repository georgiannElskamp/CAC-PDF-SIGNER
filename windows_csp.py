"""RSA signing through legacy Windows smart-card providers."""

import base64
from contextlib import contextmanager
import ctypes as C
from ctypes import wintypes as W
import datetime
import hashlib
import ssl

from asn1crypto import x509


class Blob(C.Structure):
    _fields_ = [("length", W.DWORD), ("data", C.POINTER(C.c_ubyte))]


def crypto_api():
    api = C.WinDLL("advapi32", use_last_error=True)
    handle = C.c_void_p
    signatures = {
        "CryptGetProvParam": [handle, W.DWORD, handle, C.POINTER(W.DWORD), W.DWORD],
        "CryptReleaseContext": [handle, W.DWORD],
        "CryptCreateHash": [handle, W.DWORD, handle, W.DWORD, C.POINTER(handle)],
        "CryptSetHashParam": [handle, W.DWORD, handle, W.DWORD],
        "CryptSignHashW": [handle, W.DWORD, W.LPCWSTR, W.DWORD, handle, C.POINTER(W.DWORD)],
        "CryptDestroyHash": [handle],
    }
    for name, args in signatures.items():
        getattr(api, name).argtypes = args
        getattr(api, name).restype = W.BOOL
    return api


@contextmanager
def certificate_key(thumbprint, silent=True):
    crypt = C.WinDLL("crypt32", use_last_error=True)
    handle = C.c_void_p
    crypt.CertOpenSystemStoreW.argtypes = [handle, W.LPCWSTR]
    crypt.CertOpenSystemStoreW.restype = handle
    crypt.CertFindCertificateInStore.argtypes = [handle, W.DWORD, W.DWORD, W.DWORD, handle, handle]
    crypt.CertFindCertificateInStore.restype = handle
    crypt.CryptAcquireCertificatePrivateKey.argtypes = [handle, W.DWORD, handle, C.POINTER(handle), C.POINTER(W.DWORD), C.POINTER(W.BOOL)]
    crypt.CertFreeCertificateContext.argtypes = [handle]
    crypt.CertCloseStore.argtypes = [handle, W.DWORD]
    store = crypt.CertOpenSystemStoreW(None, "MY")
    if not store:
        raise C.WinError(C.get_last_error())
    context, key = None, handle()
    kind, release = W.DWORD(), W.BOOL()
    api = crypto_api()
    try:
        digest = bytes.fromhex(thumbprint)
        raw = (C.c_ubyte * len(digest)).from_buffer_copy(digest)
        blob = Blob(len(digest), raw)
        context = crypt.CertFindCertificateInStore(store, 0x10001, 0, 0x10000, C.byref(blob), None)
        if not context or not crypt.CryptAcquireCertificatePrivateKey(
            context, 0x40 if silent else 0, None, C.byref(key), C.byref(kind), C.byref(release)
        ):
            raise C.WinError(C.get_last_error())
        if kind.value not in (1, 2):
            raise ValueError("The selected key is not a legacy Windows RSA provider key.")
        yield api, key, kind.value
    finally:
        if release.value and key:
            if kind.value == 0xFFFFFFFF:
                ncrypt = C.WinDLL("ncrypt")
                ncrypt.NCryptFreeObject.argtypes = [handle]
                ncrypt.NCryptFreeObject(key)
            else:
                api.CryptReleaseContext(key, 0)
        if context:
            crypt.CertFreeCertificateContext(context)
        crypt.CertCloseStore(store, 0)


def reader_for_certificate(thumbprint):
    try:
        with certificate_key(thumbprint) as (api, key, _kind):
            size = W.DWORD(4096)
            buffer = C.create_string_buffer(size.value)
            if not api.CryptGetProvParam(key, 43, buffer, C.byref(size), 0):
                return None
            return buffer.value.decode("mbcs") or None
    except (OSError, ValueError):
        return None


def certificates():
    now = datetime.datetime.now(datetime.timezone.utc)
    result = []
    for der, encoding, _trust in ssl.enum_certificates("MY"):
        if encoding != "x509_asn":
            continue
        try:
            cert = x509.Certificate.load(der)
            validity = cert["tbs_certificate"]["validity"]
            usage = cert.key_usage_value.native if cert.key_usage_value else set()
            units = cert.subject.native.get("organizational_unit_name", [])
            units = [units] if isinstance(units, str) else units
            if (cert.public_key.algorithm != "rsa" or cert.ca
                or not validity["not_before"].native <= now <= validity["not_after"].native
                or not {"digital_signature", "non_repudiation"}.issubset(usage)
                or not any(str(unit).upper() == "DOD" for unit in units)):
                continue
            thumbprint = hashlib.sha1(der).hexdigest()
            if reader_for_certificate(thumbprint):
                result.append(dict(thumbprint=thumbprint, certificate=base64.b64encode(der).decode(), provider="csp"))
        except (ValueError, KeyError):
            continue
    return result


def sign_hash(api, key, key_spec, digest):
    if len(digest) != 32:
        raise ValueError("A SHA-256 digest is required.")
    hashed = C.c_void_p()
    if not api.CryptCreateHash(key, 0x800C, None, 0, C.byref(hashed)):
        raise RuntimeError("The legacy card provider does not support SHA-256 signing.")
    try:
        data = (C.c_ubyte * len(digest)).from_buffer_copy(digest)
        if not api.CryptSetHashParam(hashed, 2, data, 0):
            raise C.WinError(C.get_last_error())
        size = W.DWORD()
        if not api.CryptSignHashW(hashed, key_spec, None, 0, None, C.byref(size)):
            raise C.WinError(C.get_last_error())
        if not 128 <= size.value <= 2048:
            raise ValueError("Unsupported RSA signature size from the card provider.")
        signature = (C.c_ubyte * size.value)()
        if not api.CryptSignHashW(hashed, key_spec, None, 0, signature, C.byref(size)):
            raise C.WinError(C.get_last_error())
        # CryptoAPI RSA signatures are little-endian; CMS uses big-endian.
        return bytes(signature[:size.value])[::-1]
    finally:
        api.CryptDestroyHash(hashed)


def sign_digest(thumbprint, digest):
    with certificate_key(thumbprint, silent=False) as (api, key, kind):
        return sign_hash(api, key, kind, digest)
