"""Handle one signing request over standard input/output."""

import base64
import ctypes
import hashlib
import json
import logging
import os
import re
import sys
import tempfile
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path

from runtime_config import MAX_PDF, state_directory

VERSION = "0.5.2"
MAX_REQUEST = MAX_PDF * 4 // 3 + 16384


def emit(message):
    print(json.dumps(message, ensure_ascii=True), flush=True)


@contextmanager
def signing_lock():
    """Serialize PIN/Save As dialogs across PDF tabs in this Windows session."""
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    kernel.CreateMutexW.restype = ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel.WaitForSingleObject.restype = ctypes.c_uint32
    kernel.ReleaseMutex.argtypes = [ctypes.c_void_p]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.CreateMutexW(None, False, "Local\\ONLYOFFICE-CAC-Signing")
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    acquired = kernel.WaitForSingleObject(handle, 0) in (0, 0x80)
    try:
        if not acquired:
            raise ValueError(
                "Another CAC signing or Save As operation is already open."
            )
        yield
    finally:
        if acquired:
            kernel.ReleaseMutex(handle)
        kernel.CloseHandle(handle)


class SigningSession:
    def __init__(self, directory, bridge):
        self.directory = Path(directory)
        self.output = self.directory / "Signed"
        self.bridge = Path(bridge)

    def record(self, identifier, metadata):
        self.output.mkdir(parents=True, exist_ok=True)
        path = self.output / (identifier + ".json")
        temporary = path.with_suffix(".json.tmp")
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(metadata, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)

    def pending(self, source_hash, field):
        for path in sorted(
            self.output.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True
        ):
            try:
                metadata = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if (
                isinstance(metadata, dict)
                and re.fullmatch(r"[0-9a-f]{12}", path.stem)
                and metadata.get("sourceHash") == source_hash
                and metadata.get("field") == field
                and not metadata.get("savedPath")
            ):
                # Reject damaged recovery instead of signing again.
                self.content(metadata)
                return path.stem, metadata
        return None

    def content(self, metadata):
        name = metadata["recoveryName"]
        if not isinstance(name, str) or Path(name).name != name or ":" in name:
            raise ValueError("Invalid signed recovery record.")
        content = (self.output / name).read_bytes()
        if hashlib.sha256(content).hexdigest() != metadata["sha256"]:
            raise ValueError("The signed recovery copy changed. It was not saved.")
        return content

    def sign(self, request):
        from card_selection import choose_certificate
        from signing import CardSigner, certificates, sign_bytes

        pdf = base64.b64decode(request["pdf"], validate=True)
        if len(pdf) > MAX_PDF or not pdf.startswith(b"%PDF-"):
            raise ValueError("Choose a PDF smaller than 40 MB.")
        field = request.get("field")
        if not isinstance(field, str) or not field.strip():
            raise ValueError("Click an empty PDF signature field.")
        source_hash = hashlib.sha256(pdf).hexdigest()
        pending = self.pending(source_hash, field)
        if pending:
            return (*pending, True)
        info = choose_certificate(certificates(self.bridge))
        signed = sign_bytes(pdf, CardSigner(info, self.bridge), {"field": field})
        name = re.sub(
            r"[^a-zA-Z0-9_. -]", "_", str(request.get("name", "document.pdf"))
        )[:120]
        stem = Path(name).stem.strip(". ") or "document"
        identifier = uuid.uuid4().hex[:12]
        self.output.mkdir(parents=True, exist_ok=True)
        target = self.output / f"{stem}-CAC-signed-{identifier}.pdf"
        with target.open("xb") as stream:
            stream.write(signed)
            stream.flush()
            os.fsync(stream.fileno())
        source = request.get("sourcePath", "")
        if not isinstance(source, str):
            source = ""
        metadata = dict(
            sha256=hashlib.sha256(signed).hexdigest(),
            source=source,
            name=name,
            sourceHash=source_hash,
            field=field,
            recoveryName=target.name,
            savedPath="",
        )
        self.record(identifier, metadata)
        return identifier, metadata, False

    def save(self, identifier, metadata, filename):
        target = Path(filename)
        if (
            not target.is_absolute()
            or target.suffix.lower() != ".pdf"
            or ":" in str(target)[2:]
        ):
            raise ValueError("Choose a PDF file in the Save As dialog.")
        target = target.resolve()
        source = metadata["source"]
        if source and os.path.normcase(str(target)) == os.path.normcase(
            str(Path(source).resolve())
        ):
            raise ValueError(
                "Choose a different filename to preserve the original PDF."
            )
        content = self.content(metadata)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=target.parent, prefix=".cac-", suffix=".tmp", delete=False
            ) as stream:
                temporary = Path(stream.name)
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
            temporary = None
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)
        if hashlib.sha256(target.read_bytes()).hexdigest() != metadata["sha256"]:
            raise ValueError(
                "Saved PDF verification failed. The recovery copy is retained."
            )
        self.record(identifier, {**metadata, "savedPath": str(target)})
        return target

    def run(self, request):
        from save_dialog import choose_pdf

        with signing_lock():
            identifier, metadata, recovered = self.sign(request)
            emit({"event": "signed", "recovered": recovered})
            name = Path(metadata["name"]).stem + "-signed.pdf"
            folder = (
                str(Path(metadata["source"]).parent)
                if metadata["source"]
                else str(self.directory)
            )
            filename = choose_pdf(name, folder)
            if not filename:
                return {"ok": True, "cancelled": True, "integrityVerified": True}
            target = self.save(identifier, metadata, filename)
            result = {
                "ok": True,
                "saved": True,
                "integrityVerified": True,
                "sha256": metadata["sha256"],
                "path": str(target),
            }
            return result


def main():
    # Bound the startup wait for a request.
    watchdog = threading.Timer(30, lambda: os._exit(2))
    watchdog.daemon = True
    watchdog.start()
    emit({"event": "ready", "version": VERSION})
    try:
        line = sys.stdin.buffer.readline(MAX_REQUEST + 1)
        if len(line) > MAX_REQUEST or not line.endswith(b"\n"):
            raise ValueError("Invalid signing request length.")
        watchdog.cancel()
        request = json.loads(line)
        if not isinstance(request, dict):
            raise ValueError("A signing request object is required.")
        bridge = (
            Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
            / "pdfsign-bridge.exe"
        )
        if not bridge.is_file():
            raise RuntimeError(
                "The plugin's bundled signing component is missing. Reinstall the plugin."
            )
        if request.get("op") == "health":
            import signing  # noqa: F401 -- validate packaged dependencies without accessing a card

            result = {"ok": True, "version": VERSION, "bundledBridge": True}
        elif request.get("op") == "sign":
            result = SigningSession(state_directory(), bridge).run(request)
        else:
            raise ValueError("Unknown signing operation.")
        emit({"event": "result", **result})
        return 0
    except Exception as exc:
        emit({"event": "result", "ok": False, "error": str(exc)})
        return 1
    finally:
        watchdog.cancel()


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)
    raise SystemExit(main())
