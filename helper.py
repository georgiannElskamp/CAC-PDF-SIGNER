"""Authenticated loopback service for signing and saving PDF signature fields."""

import base64
import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from card_selection import choose_certificate
from runtime_config import (
    MAX_PDF,
    VERSION,
    find_onlyoffice,
    load_settings,
    state_directory,
)
from signing import CardSigner, certificates, sign_bytes

ROOT = Path(__file__).resolve().parent
DATA = state_directory()
SETTINGS = load_settings(DATA)
PORT = SETTINGS["port"]
BRIDGE = DATA / "pdfsign-bridge.exe"
OUTPUT = DATA / "Signed"
SIGN_LOCK = threading.Lock()
SAVE_LOCK = threading.Lock()
OUTPUTS = {}
OUTPUT_META = {}
EVENTS = []


def record_output(identifier, metadata):
    """Persist recovery before returning a signature or showing a chooser."""
    path = OUTPUT / f"{identifier}.json"
    temporary = path.with_suffix(".json.tmp")
    with temporary.open("w", encoding="utf-8") as out:
        json.dump(metadata, out)
        out.flush()
        os.fsync(out.fileno())
    os.replace(temporary, path)
    OUTPUT_META[identifier] = metadata


def load_outputs():
    for path in OUTPUT.glob("*.json"):
        try:
            metadata = json.loads(path.read_text(encoding="utf-8"))
            target = OUTPUT / metadata["recoveryName"]
            if (
                not re.fullmatch("[0-9a-f]{12}", path.stem)
                or target.parent != OUTPUT
                or not target.is_file()
            ):
                continue
            OUTPUTS[path.stem] = target
            OUTPUT_META[path.stem] = metadata
        except (ValueError, KeyError, OSError):
            continue


def output_result(identifier, recovered=False):
    target = OUTPUTS[identifier]
    metadata = OUTPUT_META[identifier]
    if hashlib.sha256(target.read_bytes()).hexdigest() != metadata["sha256"]:
        raise ValueError("The signed recovery copy changed. It was not saved.")
    return {
        "ok": True,
        "id": identifier,
        "path": str(target),
        "integrityVerified": True,
        "sha256": metadata["sha256"],
        "recovered": recovered,
    }


def save_output(identifier, filename):
    source = OUTPUTS.get(identifier)
    if not source:
        raise ValueError(
            "Signed copy is not available. Click the signature box to retry."
        )
    metadata = OUTPUT_META[identifier]
    target = Path(str(filename))
    if (
        not target.is_absolute()
        or target.suffix.lower() != ".pdf"
        or ":" in str(target)[2:]
    ):
        raise ValueError("Choose a PDF file in the Save As dialog.")
    target = target.resolve()
    original = metadata["source"]
    if original and os.path.normcase(str(target)) == os.path.normcase(
        str(Path(original).resolve())
    ):
        raise ValueError(
            "Choose a different filename for the signed copy to preserve the original."
        )
    content = source.read_bytes()
    expected = metadata["sha256"]
    if hashlib.sha256(content).hexdigest() != expected:
        raise ValueError("The signed recovery copy changed. It was not saved.")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=target.parent, prefix=".cac-", suffix=".tmp", delete=False
        ) as out:
            temporary = Path(out.name)
            out.write(content)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, target)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    if hashlib.sha256(target.read_bytes()).hexdigest() != expected:
        raise ValueError(
            "The saved file failed its integrity check. The recovery copy is retained."
        )
    record_output(identifier, {**metadata, "savedPath": str(target)})
    return {"ok": True, "sha256": expected, "path": str(target)}


def save_with_dialog(identifier):
    if identifier not in OUTPUTS:
        raise ValueError(
            "Signed copy is not available. Click the signature box to retry."
        )
    if not SAVE_LOCK.acquire(blocking=False):
        raise ValueError("A Save As dialog is already open. Finish or cancel it first.")
    try:
        output_result(identifier)
        metadata = OUTPUT_META[identifier]
        name = Path(metadata["name"]).stem + "-signed.pdf"
        folder = (
            str(Path(metadata["source"]).parent) if metadata["source"] else str(DATA)
        )
        # A dedicated GUI thread/process avoids the editor's iframe/IPC callback handoff.
        python = str(Path(sys.executable).with_name("python.exe"))
        proc = subprocess.run(
            [python, str(ROOT / "save_dialog.py"), name, folder],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        try:
            result = json.loads(proc.stdout)
        except ValueError:
            raise RuntimeError(
                "Windows Save As did not finish. Click the signature box to retry; the signed copy is retained."
            )
        if proc.returncode or result.get("error"):
            raise RuntimeError(result.get("error", "Windows Save As did not finish."))
        if not result.get("path"):
            return {"ok": True, "cancelled": True}
        return save_output(identifier, result["path"])
    finally:
        SAVE_LOCK.release()


class Handler(BaseHTTPRequestHandler):
    server_version = "LocalCAC/" + VERSION

    def log_message(self, *_args):
        pass  # No document contents, certificate subjects, or secrets in logs.

    def valid_origin(self):
        return self.headers.get("Origin", "null") in ("null", "file://")

    def authorized(self):
        return (
            self.headers.get("Host") == f"127.0.0.1:{PORT}"
            and self.valid_origin()
            and hmac.compare_digest(
                self.headers.get("X-CAC-Token", ""), SETTINGS["token"]
            )
        )

    def reply(self, code, data):
        payload = json.dumps(data).encode()
        self.send_response(code)
        if self.valid_origin():
            self.send_header(
                "Access-Control-Allow-Origin", self.headers.get("Origin", "null")
            )
        self.send_header("Vary", "Origin")
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_OPTIONS(self):
        if self.headers.get("Host") != f"127.0.0.1:{PORT}" or not self.valid_origin():
            return self.reply(403, {"error": "Origin denied."})
        self.send_response(204)
        self.send_header(
            "Access-Control-Allow-Origin", self.headers.get("Origin", "null")
        )
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-CAC-Token")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.end_headers()

    def do_GET(self):
        if not self.authorized():
            return self.reply(403, {"error": "Local plugin authorization required."})
        try:
            if self.path == "/health":
                self.reply(
                    200, {"ok": True, "version": VERSION, "outputFolder": str(OUTPUT)}
                )
            elif self.path == "/status":
                self.reply(200, {"events": list(EVENTS)})
            else:
                self.reply(404, {"error": "Not found."})
        except Exception as exc:
            self.reply(400, {"error": str(exc)})

    def do_POST(self):
        if not self.authorized():
            return self.reply(403, {"error": "Local plugin authorization required."})
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= (MAX_PDF * 4 // 3 + 8192):
                return self.reply(413, {"error": "Request too large."})
            if self.headers.get("Content-Type") != "application/json":
                return self.reply(415, {"error": "JSON required."})
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise ValueError("A JSON object is required.")
            if self.path == "/event":
                event = {
                    k: str(data[k])[:400]
                    for k in ("stage", "version", "error")
                    if k in data
                }
                EVENTS.append(event)
                del EVENTS[:-30]
                self.reply(200, {"ok": True})
            elif self.path == "/sign-auto":
                if not SIGN_LOCK.acquire(blocking=False):
                    return self.reply(
                        409, {"error": "Another signing request is in progress."}
                    )
                try:
                    pdf = base64.b64decode(data["pdf"], validate=True)
                    if len(pdf) > MAX_PDF or not pdf.startswith(b"%PDF-"):
                        raise ValueError("Choose a PDF smaller than 40 MB.")
                    source_hash = hashlib.sha256(pdf).hexdigest()
                    appearance = data.get("appearance")
                    field = (
                        appearance.get("field")
                        if isinstance(appearance, dict)
                        else None
                    )
                    if not isinstance(field, str) or not field.strip():
                        raise ValueError("Click an empty PDF signature field.")
                    pending = next(
                        (
                            key
                            for key, value in reversed(list(OUTPUT_META.items()))
                            if value.get("sourceHash") == source_hash
                            and value.get("field") == field
                            and not value.get("savedPath")
                        ),
                        None,
                    )
                    if pending:
                        return self.reply(200, output_result(pending, recovered=True))
                    info = choose_certificate(certificates(BRIDGE))
                    signed = sign_bytes(pdf, CardSigner(info, BRIDGE), {"field": field})
                    safe = re.sub(
                        r"[^a-zA-Z0-9_. -]", "_", str(data.get("name", "document.pdf"))
                    )[:120]
                    stem = Path(safe).stem.strip(". ") or "document"
                    identifier = uuid.uuid4().hex[:12]
                    OUTPUT.mkdir(exist_ok=True)
                    target = OUTPUT / f"{stem}-CAC-signed-{identifier}.pdf"
                    with target.open("xb") as out:
                        out.write(signed)
                        out.flush()
                        os.fsync(out.fileno())
                    OUTPUTS[identifier] = target
                    record_output(
                        identifier,
                        {
                            "sha256": hashlib.sha256(signed).hexdigest(),
                            "source": data.get("sourcePath", ""),
                            "name": safe,
                            "sourceHash": source_hash,
                            "field": field,
                            "recoveryName": target.name,
                            "savedPath": "",
                        },
                    )
                    self.reply(200, output_result(identifier))
                finally:
                    SIGN_LOCK.release()
            elif self.path == "/save-dialog":
                self.reply(200, save_with_dialog(data.get("id")))
            elif self.path == "/open":
                identifier = data.get("id")
                target = OUTPUT_META.get(identifier, {}).get("savedPath")
                if not target:
                    raise ValueError("Save the signed copy before opening it.")
                subprocess.Popen(
                    [
                        str(find_onlyoffice(SETTINGS.get("onlyofficePath", ""))),
                        str(target),
                    ]
                )
                self.reply(200, {"ok": True})
            else:
                self.reply(404, {"error": "Not found."})
        except Exception as exc:
            self.reply(400, {"error": str(exc)})


if __name__ == "__main__":
    load_outputs()
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    server.daemon_threads = True
    server.serve_forever()
