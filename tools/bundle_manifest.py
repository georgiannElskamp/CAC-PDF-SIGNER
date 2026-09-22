"""Bind each native bundle to its inputs and packaged files."""

import hashlib
import json

from _paths import ROOT
from runtime_config import VERSION


def source_hashes(root):
    files = list(root.glob("*.py"))
    files += [root / name for name in ("requirements-lock.txt", "requirements-linux.txt", "requirements-build.txt")]
    files += [p for p in (root / "fonts").rglob("*") if p.is_file()]
    result = {}
    for path in sorted(files):
        data = path.read_bytes()
        if path.suffix.lower() not in (".ttf", ".otf"):
            data = data.replace(b"\r\n", b"\n")
        result[path.relative_to(root).as_posix()] = hashlib.sha256(data).hexdigest()
    return result


def write_manifest(directory, root, platform, architecture):
    files = {p.relative_to(directory).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted(directory.rglob("*")) if p.is_file() and p != directory / "manifest.json"}
    manifest = dict(version=VERSION, platform=platform, architecture=architecture,
                    format="onedir", runtimeSources=source_hashes(root), files=files)
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def verify_manifest(directory, root):
    manifest = json.loads((directory / "manifest.json").read_text())
    if manifest.get("version") != VERSION or manifest.get("format") != "onedir":
        raise ValueError("Native bundle version or format differs. Rebuild the worker.")
    if manifest["runtimeSources"] != source_hashes(root):
        raise ValueError("Native worker has stale runtime sources or dependencies. Rebuild the worker.")
    actual = {p.relative_to(directory).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in directory.rglob("*") if p.is_file() and p != directory / "manifest.json"}
    if actual != manifest["files"]:
        raise ValueError("Native bundle files differ from their manifest.")
    return manifest
