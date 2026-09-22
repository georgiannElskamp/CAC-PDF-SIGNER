"""Select only the signing certificate on a physically present Windows smart card."""

import base64
import ctypes as C
from ctypes import wintypes as W

from asn1crypto import x509


def reader_is_present(reader):
    scard = C.WinDLL("winscard")
    handle = C.c_void_p

    class ReaderState(C.Structure):
        _fields_ = [("reader", W.LPCWSTR), ("user", handle), ("current", W.DWORD),
                    ("event", W.DWORD), ("atr_length", W.DWORD), ("atr", C.c_ubyte * 36)]

    scard.SCardEstablishContext.argtypes = [W.DWORD, handle, handle, C.POINTER(handle)]
    scard.SCardGetStatusChangeW.argtypes = [handle, W.DWORD, C.POINTER(ReaderState), W.DWORD]
    scard.SCardReleaseContext.argtypes = [handle]
    context = handle()
    if not reader or scard.SCardEstablishContext(0, None, None, C.byref(context)):
        return False
    try:
        state = ReaderState(reader=reader)
        return (not scard.SCardGetStatusChangeW(context, 0, C.byref(state), 1)
                and bool(state.event & 0x20) and not state.event & (0x4 | 0x8 | 0x10 | 0x200))
    finally:
        scard.SCardReleaseContext(context)


def connected_reader(thumbprint):
    crypt = C.WinDLL("crypt32", use_last_error=True)
    ncrypt = C.WinDLL("ncrypt")
    scard = C.WinDLL("winscard")
    handle = C.c_void_p

    class Blob(C.Structure):
        _fields_ = [("length", W.DWORD), ("data", C.POINTER(C.c_ubyte))]

    class ReaderState(C.Structure):
        _fields_ = [
            ("reader", W.LPCWSTR),
            ("user", handle),
            ("current", W.DWORD),
            ("event", W.DWORD),
            ("atr_length", W.DWORD),
            ("atr", C.c_ubyte * 36),
        ]

    crypt.CertOpenSystemStoreW.argtypes = [handle, W.LPCWSTR]
    crypt.CertOpenSystemStoreW.restype = handle
    crypt.CertFindCertificateInStore.argtypes = [
        handle,
        W.DWORD,
        W.DWORD,
        W.DWORD,
        handle,
        handle,
    ]
    crypt.CertFindCertificateInStore.restype = handle
    crypt.CryptAcquireCertificatePrivateKey.argtypes = [
        handle,
        W.DWORD,
        handle,
        C.POINTER(handle),
        C.POINTER(W.DWORD),
        C.POINTER(W.BOOL),
    ]
    crypt.CertFreeCertificateContext.argtypes = [handle]
    crypt.CertCloseStore.argtypes = [handle, W.DWORD]
    ncrypt.NCryptGetProperty.argtypes = [
        handle,
        W.LPCWSTR,
        handle,
        W.DWORD,
        C.POINTER(W.DWORD),
        W.DWORD,
    ]
    ncrypt.NCryptFreeObject.argtypes = [handle]
    scard.SCardEstablishContext.argtypes = [W.DWORD, handle, handle, C.POINTER(handle)]
    scard.SCardGetStatusChangeW.argtypes = [
        handle,
        W.DWORD,
        C.POINTER(ReaderState),
        W.DWORD,
    ]
    scard.SCardReleaseContext.argtypes = [handle]
    store = crypt.CertOpenSystemStoreW(None, "MY")
    if not store:
        return None
    ctx = None
    key, key_type, free_key, pcsc = handle(), W.DWORD(), W.BOOL(), handle()
    try:
        digest = bytes.fromhex(thumbprint)
        raw = (C.c_ubyte * len(digest)).from_buffer_copy(digest)
        blob = Blob(len(digest), raw)
        ctx = crypt.CertFindCertificateInStore(
            store, 0x10001, 0, 0x10000, C.byref(blob), None
        )
        if not ctx or not crypt.CryptAcquireCertificatePrivateKey(
            ctx, 0x40040, None, C.byref(key), C.byref(key_type), C.byref(free_key)
        ):
            return None
        if key_type.value != 0xFFFFFFFF:
            return None
        size = W.DWORD()
        reader_buffer = C.create_unicode_buffer(512)
        if ncrypt.NCryptGetProperty(
            key,
            "SmartCardReader",
            reader_buffer,
            C.sizeof(reader_buffer),
            C.byref(size),
            0,
        ):
            return None
        reader = reader_buffer.value
        if not reader or scard.SCardEstablishContext(0, None, None, C.byref(pcsc)):
            return None
        state = ReaderState(reader=reader)
        if scard.SCardGetStatusChangeW(pcsc, 0, C.byref(state), 1):
            return None
        # PRESENT, excluding UNKNOWN / UNAVAILABLE / EMPTY / MUTE.
        return (
            reader
            if state.event & 0x20 and not state.event & (0x4 | 0x8 | 0x10 | 0x200)
            else None
        )
    finally:
        if pcsc:
            scard.SCardReleaseContext(pcsc)
        if free_key.value and key:
            ncrypt.NCryptFreeObject(key)
        if ctx:
            crypt.CertFreeCertificateContext(ctx)
        crypt.CertCloseStore(store, 0)


def choose_certificate(candidates, reader_check=connected_reader):
    eligible = []
    for info in candidates:
        cert = x509.Certificate.load(base64.b64decode(info["certificate"]))
        usage = cert.key_usage_value.native if cert.key_usage_value else set()
        if "non_repudiation" not in usage or "digital_signature" not in usage:
            continue
        units = cert.subject.native.get("organizational_unit_name", [])
        if isinstance(units, str):
            units = [units]
        if not any(str(unit).upper() == "DOD" for unit in units):
            continue
        if info.get("provider") == "csp":
            from windows_csp import reader_for_certificate

            present = reader_is_present(reader_for_certificate(info["thumbprint"]))
        else:
            present = reader_check(info["thumbprint"])
        if present:
            eligible.append(info)
    if not eligible:
        raise ValueError(
            "No usable CAC signing certificate was found. Check that the reader is connected, the card's certificates appear in your Windows account, and its CNG or RSA smart-card provider is installed."
        )
    if len(eligible) != 1:
        raise ValueError(
            "More than one CAC signing certificate is available. Leave only the card you want to use connected, then click the signature box again."
        )
    return eligible[0]
