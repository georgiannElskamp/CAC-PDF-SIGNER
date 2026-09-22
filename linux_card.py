"""PKCS#11 signing with the bundled Linux smart-card middleware."""

import ctypes
import datetime
import os
import socket
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

from asn1crypto import x509


def runtime_directory():
    override = os.environ.get("CAC_LINUX_RUNTIME")
    return Path(override) if override else Path(getattr(sys, "_MEIPASS", Path(__file__).parent))


def module_path():
    override = os.environ.get("CAC_PKCS11_MODULE")
    path = Path(override) if override else runtime_directory() / "opensc-pkcs11.so"
    if not path.is_absolute() or not path.is_file():
        raise RuntimeError("The Linux smart-card component is missing. Reinstall the plugin.")
    return path


def check_runtime():
    import pkcs11  # noqa: F401

    ctypes.CDLL(str(module_path()))
    if not os.environ.get("CAC_PKCS11_MODULE") and not (runtime_directory() / "pcscd").is_file():
        raise RuntimeError("The bundled Linux reader component is missing. Reinstall the plugin.")


def available_socket(path):
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(0.25)
            connection.connect(str(path))
        return True
    except OSError:
        return False


@contextmanager
def reader_runtime():
    # A user-selected PKCS#11 provider owns its own reader transport.
    if os.environ.get("CAC_PKCS11_MODULE"):
        yield
        return
    previous = os.environ.get("PCSCLITE_CSOCK_NAME")
    for path in filter(None, (previous, "/run/pcscd/pcscd.comm", "/var/run/pcscd/pcscd.comm")):
        if available_socket(path):
            os.environ["PCSCLITE_CSOCK_NAME"] = path
            try:
                yield
            finally:
                if previous is None:
                    os.environ.pop("PCSCLITE_CSOCK_NAME", None)
                else:
                    os.environ["PCSCLITE_CSOCK_NAME"] = previous
            return
    root = runtime_directory()
    with tempfile.TemporaryDirectory(prefix="cac-pcsc-") as temporary:
        channel = str(Path(temporary) / "pcscd.comm")
        os.environ["PCSCLITE_CSOCK_NAME"] = channel
        environment = dict(os.environ, CAC_PCSC_DIR=temporary,
                           PCSCLITE_HP_DROPDIR=str(root / "pcsc-drivers"))
        process = None
        try:
            process = subprocess.Popen(
                [str(root / "pcscd"), "--foreground", "--error"],
                env=environment, stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            deadline = time.monotonic() + 8
            while not available_socket(channel):
                if process.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError("The bundled Linux reader component could not start. Check USB reader access permissions.")
                time.sleep(0.05)
            yield
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            if previous is None:
                os.environ.pop("PCSCLITE_CSOCK_NAME", None)
            else:
                os.environ["PCSCLITE_CSOCK_NAME"] = previous


def eligible_certificate(cert, now=None):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    validity = cert["tbs_certificate"]["validity"]
    if not validity["not_before"].native <= now <= validity["not_after"].native:
        return False
    usage = cert.key_usage_value.native if cert.key_usage_value else set()
    if not {"digital_signature", "non_repudiation"}.issubset(usage):
        return False
    units = cert.subject.native.get("organizational_unit_name", [])
    if isinstance(units, str):
        units = [units]
    return any(str(unit).upper() == "DOD" for unit in units)


def select_certificate(library):
    from pkcs11 import Attribute, ObjectClass, TokenFlag

    candidates = []
    for token in library.get_tokens():
        if not token.flags & TokenFlag.TOKEN_INITIALIZED:
            continue
        with token.open() as session:
            for obj in session.get_objects({Attribute.CLASS: ObjectClass.CERTIFICATE}):
                try:
                    cert = x509.Certificate.load(bytes(obj[Attribute.VALUE]))
                    identifier = bytes(obj[Attribute.ID])
                except (ValueError, KeyError):
                    continue
                if identifier and eligible_certificate(cert):
                    candidates.append((token, identifier, cert))
    if not candidates:
        raise ValueError("Insert your CAC. No eligible signing certificate is available on a connected Linux reader.")
    if len(candidates) != 1:
        raise ValueError("More than one CAC signing certificate is available. Leave only the card you want to use connected.")
    return candidates[0]


@contextmanager
def card_signer():
    import pkcs11
    from pyhanko.sign.pkcs11 import PKCS11Signer
    from linux_ui import request_pin

    with reader_runtime():
        library = pkcs11.lib(str(module_path()))
        token, identifier, certificate = select_certificate(library)
        if token.flags & pkcs11.TokenFlag.USER_PIN_LOCKED:
            raise ValueError("The CAC PIN is locked. No signing attempt was made.")
        protected = bool(token.flags & pkcs11.TokenFlag.PROTECTED_AUTHENTICATION_PATH)
        pin = pkcs11.PROTECTED_AUTH if protected else request_pin()
        try:
            with token.open(user_pin=pin) as session:
                pin = None
                yield PKCS11Signer(session, signing_cert=certificate, key_id=identifier, embed_roots=False)
        except pkcs11.PinIncorrect as exc:
            raise ValueError("The CAC rejected the PIN. No automatic retry was made.") from exc
        except pkcs11.PinLocked as exc:
            raise ValueError("The CAC PIN is locked.") from exc
        except pkcs11.TokenNotPresent as exc:
            raise ValueError("The CAC was removed before signing completed.") from exc
        finally:
            pin = None
