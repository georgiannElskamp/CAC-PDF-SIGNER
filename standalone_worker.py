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
import time
import uuid
from contextlib import contextmanager
from pathlib import Path, PureWindowsPath

from runtime_config import MAX_PDF, VERSION, state_directory
MAX_REQUEST = MAX_PDF * 4 // 3 + 16384
PREPARED_AGE = 30 * 24 * 60 * 60


def request_pdf(request):
    pdf = base64.b64decode(request["pdf"], validate=True)
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
        self.prepared = self.directory / "Prepared"
        self.bridge = Path(bridge)

    def prune_prepared(self):
        if not self.prepared.is_dir():
            return
        cutoff = time.time() - PREPARED_AGE
        for record in self.prepared.glob("CAC-review-*.json"):
            if not re.fullmatch(r"CAC-review-[0-9a-f]{32}\.json", record.name):
                continue
            try:
                if record.stat().st_mtime >= cutoff:
                    continue
                pdf = record.with_suffix(".pdf")
                if pdf.is_file() and pdf.stat().st_mtime >= cutoff:
                    continue
                pdf.unlink(missing_ok=True)
                record.unlink()
            except OSError:
                pass
        for pdf in self.prepared.glob("CAC-review-*.pdf"):
            if not re.fullmatch(r"CAC-review-[0-9a-f]{32}\.pdf", pdf.name):
                continue
            try:
                if not pdf.with_suffix(".json").exists() and pdf.stat().st_mtime < cutoff:
                    pdf.unlink()
            except OSError:
                pass

    def prepare_form(self, request):
        from onlyoffice_form import prepare_signature

        pdf = request_pdf(request)
        source = request.get("sourcePath")
        if not isinstance(source, str) or not Path(source).is_absolute() or Path(source).suffix.lower() != ".pdf":
            raise ValueError("Save and reopen the local PDF form before signing.")
        writer, field = prepare_signature(pdf, request.get("field"))
        import io
        output = io.BytesIO()
        writer.write(output)
        prepared = output.getvalue()
        if len(prepared) > MAX_PDF or not prepared.startswith(b"%PDF-"):
            raise ValueError("The prepared PDF exceeds the 40 MB limit.")
        self.prepared.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.prune_prepared()
        identifier = uuid.uuid4().hex
        target = self.prepared / ("CAC-review-" + identifier + ".pdf")
        record = target.with_suffix(".json")
        digest = hashlib.sha256(prepared).hexdigest()
        metadata = {"sha256": digest, "field": field, "source": source,
                    "name": Path(source).name}
        try:
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(prepared)
                stream.flush()
                os.fsync(stream.fileno())
            descriptor = os.open(record, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(metadata, stream)
                stream.flush()
                os.fsync(stream.fileno())
        except BaseException:
            target.unlink(missing_ok=True)
            record.unlink(missing_ok=True)
            raise
        return {"ok": True, "prepared": True, "path": str(target), "sha256": digest,
                "field": field}

    def prepared_source(self, source, pdf, field):
        if not source:
            return None
        path = Path(source).resolve()
        if path.parent != self.prepared.resolve():
            return None
        if not re.fullmatch(r"CAC-review-[0-9a-f]{32}\.pdf", path.name):
            raise ValueError("The prepared PDF handoff is invalid. Reopen the form.")
        try:
            record = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError("The prepared PDF handoff is missing. Reopen the form.") from exc
        if (not isinstance(record, dict)
                or record.get("sha256") != hashlib.sha256(pdf).hexdigest()
                or record.get("field") != field
                or not isinstance(record.get("source"), str)
                or not Path(record["source"]).is_absolute()
                or Path(record["source"]).suffix.lower() != ".pdf"
                or record.get("name") != Path(record["source"]).name):
            raise ValueError("The prepared PDF changed. Reopen the form.")
        return record

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

    def pending(self, source_hash, field, source=None):
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
                and (source is None or metadata.get("source") == source)
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
        if kind != "pdf-signature":
            raise ValueError("Unsupported signing request.")
        pdf = request_pdf(request)
        field = request.get("field")
        if not isinstance(field, str) or not field.strip():
            raise ValueError("Click an empty PDF signature field.")
        source = request.get("sourcePath", "")
        if not isinstance(source, str):
            source = ""
        handoff = self.prepared_source(source, pdf, field)
        prepared_path = source if handoff else ""
        if handoff:
            source = handoff["source"]
        self.prepare_output()
        source_hash = hashlib.sha256(pdf).hexdigest()
        pending = self.pending(source_hash, field, source)
        if pending:
            return (*pending, True)
        with card_signer(self.bridge) as signer:
            signed = sign_bytes(pdf, signer, {"field": field, "kind": kind})
        original_name = handoff["name"] if handoff else request.get("name", "document.pdf")
        name = re.sub(r"[^a-zA-Z0-9_. -]", "_", str(original_name))[:120]
        stem = Path(name).stem.strip(". ") or "document"
        identifier = uuid.uuid4().hex[:12]
        self.output.mkdir(parents=True, exist_ok=True)
        target = self.output / f"{stem}-CAC-signed-{identifier}.pdf"
        with target.open("xb") as stream:
            stream.write(signed)
            stream.flush()
            os.fsync(stream.fileno())
        metadata = dict(
            sha256=hashlib.sha256(signed).hexdigest(),
            source=source,
            preparedPath=prepared_path,
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
        sources = [p for p in (metadata["source"], metadata.get("preparedPath")) if p]
        same_source = any(comparable_path(target) == comparable_path(source) for source in sources)
        if target.exists():
            same_source = same_source or any(
                Path(source).exists() and os.path.samefile(target, source) for source in sources
            )
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
        elif request.get("op") == "prepare":
            result = SigningSession(state_directory(), bridge).prepare_form(request)
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
