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
from pathlib import Path, PureWindowsPath

from runtime_config import MAX_PDF, VERSION, state_directory
MAX_REQUEST = MAX_PDF * 4 // 3 + 16384


def read_form_source(source):
    if not isinstance(source, str) or not source:
        raise ValueError("Save and reopen the ONLYOFFICE PDF form before signing.")
    path = Path(source)
    if not path.is_absolute() or path.suffix.lower() != ".pdf":
        raise ValueError("A saved local PDF form is required.")
    before = path.stat()
    if before.st_size > MAX_PDF:
        raise ValueError("Choose a PDF smaller than 40 MB.")
    pdf = path.read_bytes()
    after = path.stat()
    if (before.st_dev, before.st_ino, before.st_mtime_ns, before.st_size) != (
        after.st_dev, after.st_ino, after.st_mtime_ns, after.st_size
    ):
        raise ValueError("The PDF changed while it was being read. Reopen it and retry.")
    if len(pdf) > MAX_PDF or not pdf.startswith(b"%PDF-"):
        raise ValueError("Choose a PDF smaller than 40 MB.")
    return pdf


def valid_windows_destination(filename):
    path = PureWindowsPath(filename)
    drive = path.drive
    if drive.lower().startswith("\\\\?\\unc\\"):
        drive = "\\\\" + drive[8:]
    elif drive.startswith("\\\\?\\"):
        drive = drive[4:]
    valid_drive = re.fullmatch(r"[A-Za-z]:|\\\\(?![.?]\\)[^\\:?]+\\[^\\:?]+", drive)
    return bool(path.is_absolute() and valid_drive
                and not any(":" in part for part in path.parts[1:]))


def comparable_path(filename):
    value = str(Path(filename).resolve())
    if sys.platform == "win32":
        if value.lower().startswith("\\\\?\\unc\\"):
            value = "\\\\" + value[8:]
        elif value.startswith("\\\\?\\"):
            value = value[4:]
    return os.path.normcase(value)


def emit(message):
    print(json.dumps(message, ensure_ascii=True), flush=True)


@contextmanager
def signing_lock():
    """Serialize PIN/Save As dialogs across the user's PDF tabs."""
    if sys.platform == "linux":
        import fcntl

        directory = state_directory()
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = os.open(directory / "signing.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ValueError("Another CAC signing or Save As operation is already open.") from exc
            yield
        finally:
            os.close(descriptor)
        return
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

    def prepare_output(self):
        try:
            self.output.mkdir(parents=True, exist_ok=True, mode=0o700)
            with tempfile.TemporaryFile(dir=self.output) as stream:
                stream.write(b"recovery storage check")
                stream.flush()
                os.fsync(stream.fileno())
        except OSError as exc:
            raise RuntimeError(
                "Cannot write the signed recovery folder. Check its permissions and free space before signing."
            ) from exc

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
        from platform_card import card_signer
        from signing import sign_bytes

        kind = request.get("kind", "pdf-signature")
        if kind == "onlyoffice-form":
            pdf = read_form_source(request.get("sourcePath"))
            expected = request.get("expectedSourceHash")
            if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
                raise ValueError("Reopen the PDF form before signing.")
            if hashlib.sha256(pdf).hexdigest() != expected:
                raise ValueError("The PDF changed after opening. Reopen it before signing.")
        elif kind == "pdf-signature":
            pdf = base64.b64decode(request["pdf"], validate=True)
        else:
            raise ValueError("Unsupported signing request.")
        if len(pdf) > MAX_PDF or not pdf.startswith(b"%PDF-"):
            raise ValueError("Choose a PDF smaller than 40 MB.")
        field = request.get("field")
        if not isinstance(field, str) or not field.strip():
            raise ValueError("Click an empty PDF signature field.")
        self.prepare_output()
        source_hash = hashlib.sha256(pdf).hexdigest()
        pending = self.pending(source_hash, field)
        if pending:
            return (*pending, True)
        with card_signer(self.bridge) as signer:
            signed = sign_bytes(pdf, signer, {"field": field, "kind": kind})
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
            or (sys.platform == "win32" and not valid_windows_destination(filename))
        ):
            raise ValueError("Choose a PDF file in the Save As dialog.")
        target = target.resolve()
        source = metadata["source"]
        same_source = source and comparable_path(target) == comparable_path(source)
        if source and target.exists() and Path(source).exists():
            same_source = same_source or os.path.samefile(target, source)
        if same_source:
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
        from save_dialog import check_desktop, choose_pdf

        with signing_lock():
            check_desktop()
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


def wait_for_acknowledgment():
    # ONLYOFFICE can discard queued output when the process exits.
    timeout = threading.Timer(10, lambda: os._exit(2))
    timeout.daemon = True
    timeout.start()
    try:
        sys.stdin.buffer.readline(128)
    finally:
        timeout.cancel()


def main():
    # Bound the startup wait for a request.
    watchdog = threading.Timer(30, lambda: os._exit(2))
    watchdog.daemon = True
    watchdog.start()
    request = None
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
        if sys.platform == "win32" and not bridge.is_file():
            raise RuntimeError(
                "The plugin's bundled signing component is missing. Reinstall the plugin."
            )
        if request.get("op") in ("health", "preflight"):
            import signing  # noqa: F401 -- validate packaged dependencies without accessing a card
            import unicode_font  # noqa: F401
            root = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
            if not all((root / "fonts" / name).is_file() for name in ("NotoSans-Regular.ttf", "NotoSansCJKsc-Regular.otf")):
                raise RuntimeError("The bundled signature fonts are missing. Reinstall the plugin.")
            if sys.platform == "linux":
                from linux_card import check_runtime

                check_runtime()
            result = {"ok": True, "version": VERSION, "platform": sys.platform,
                      "bundledBridge": True, "dependencyCheckOnly": True}
            if request["op"] == "preflight":
                from save_dialog import check_desktop

                check_desktop()
                SigningSession(state_directory(), bridge).prepare_output()
                result.update(dependencyCheckOnly=False, desktopReady=True,
                              recoveryWritable=True, cardChecked=False)
                if "sourcePath" in request:
                    result["sourceHash"] = hashlib.sha256(
                        read_form_source(request["sourcePath"])
                    ).hexdigest()
        elif request.get("op") == "sign":
            result = SigningSession(state_directory(), bridge).run(request)
        else:
            raise ValueError("Unknown signing operation.")
        emit({"event": "result", **result})
        return 0
    except Exception as exc:
        if sys.platform == "linux":
            from linux_ui import Cancelled

            if isinstance(exc, Cancelled):
                emit({"event": "result", "ok": True, "cancelled": True})
                return 0
        emit({"event": "result", "ok": False, "error": str(exc)})
        return 1
    finally:
        watchdog.cancel()
        if isinstance(request, dict) and request.get("acknowledgeResult") is True:
            wait_for_acknowledgment()


if __name__ == "__main__":
    if sys.platform == "linux":
        os.umask(0o077)
    logging.disable(logging.CRITICAL)
    raise SystemExit(main())
