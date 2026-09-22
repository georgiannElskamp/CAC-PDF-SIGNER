"""Check source files before packaging."""

import argparse
import hashlib
import json
import re
import struct
import sys
import zipfile
from pathlib import Path

FORBIDDEN_SUFFIXES = {
    ".pdf",
    ".plugin",
    ".zip",
    ".exe",
    ".dll",
    ".pem",
    ".key",
    ".cer",
    ".crt",
    ".der",
    ".pfx",
    ".p12",
    ".p7b",
    ".p7s",
    ".jks",
    ".log",
    ".pid",
    ".pyc",
}
FORBIDDEN_NAMES = {"settings.json", "connection.js", ".env", "helper.pid"}
FORBIDDEN_DIRS = {"Signed", "runtime", ".venv", "venv", "__pycache__"}
TEXT_SUFFIXES = {".py", ".js", ".html", ".json", ".md", ".txt", ".yml", ".yaml", ".cmd"}
TEXT_NAMES = {".gitignore", ".gitattributes", "LICENSE", "NOTICE"}
PATTERNS = {
    "embedded key or certificate": re.compile(
        rb"-----BEGIN (?:[A-Z ]*PRIVATE KEY|PUBLIC KEY|CERTIFICATE)-----"
    ),
    "personal Windows profile path": re.compile(
        rb'[A-Za-z]:[\\/]+Users[\\/]+[^\s<>"\x27]+', re.I
    ),
    "personal Unix home path": re.compile(rb"/(?:home|Users)/[A-Za-z0-9_.-]+/"),
    "literal installation token": re.compile(
        rb'["\x27]token["\x27]\s*:\s*["\x27][a-f0-9]{64}["\x27]', re.I
    ),
    "GitHub access token": re.compile(
        rb"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})"
    ),
    "military email address": re.compile(
        rb"[A-Za-z0-9_.+%-]+@[A-Za-z0-9.-]+\.mil\b", re.I
    ),
}


def png_has_only_image_chunks(data):
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return False
    cursor = 8
    while cursor + 12 <= len(data):
        size = struct.unpack(">I", data[cursor : cursor + 4])[0]
        kind = data[cursor + 4 : cursor + 8]
        if kind not in (
            b"IHDR",
            b"IDAT",
            b"IEND",
            b"PLTE",
            b"tRNS",
            b"sRGB",
            b"gAMA",
            b"cHRM",
        ):
            return False
        cursor += size + 12
        if kind == b"IEND":
            return size == 0 and cursor == len(data)
    return False


def source_files(root):
    return [
        path for path in sorted(root.rglob("*"))
        if path.is_file()
        and ".git" not in path.relative_to(root).parts
        and path.relative_to(root).parts[0] != "release"
    ]


def audit_release(root):
    directory = root / "release"
    if not directory.exists():
        return []
    try:
        expected = {"CAC-PDF-Signer.plugin", "SHA256SUMS.txt", "INSTALL.txt"}
        if {p.name for p in directory.iterdir()} != expected:
            raise ValueError("Release must contain one plugin, its checksum, and INSTALL.txt.")
        if directory.is_symlink() or any(p.is_symlink() for p in directory.iterdir()):
            raise ValueError("Release files must not be symbolic links.")
        package = directory / "CAC-PDF-Signer.plugin"
        digest = hashlib.sha256(package.read_bytes()).hexdigest()
        if (directory / "SHA256SUMS.txt").read_text().strip() != digest + "  " + package.name:
            raise ValueError("Release checksum does not match the plugin.")
        files = {p.relative_to(root).as_posix(): p for p in source_files(root)}
        with zipfile.ZipFile(package) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)) or archive.testzip():
                raise ValueError("Duplicate or corrupt archive entries.")
            if any("\\" in n or ":" in n or n.startswith("/") or ".." in n.split("/") for n in names):
                raise ValueError("Unsafe archive path.")
            bundled = {n[7:] for n in names if n.startswith("source/")}
            if bundled != set(files):
                raise ValueError("Bundled source inventory differs from the repository.")
            for name, path in files.items():
                if archive.read("source/" + name) != path.read_bytes():
                    raise ValueError(f"Bundled source is stale: {name}")
            config = json.loads((root / "plugin/config.json").read_text())
            if json.loads(archive.read("config.json")) != config:
                raise ValueError("Release manifest differs from the repository.")
            if config["version"] not in (directory / "INSTALL.txt").read_text():
                raise ValueError("Installation notes have a different version.")
            assets = {"desktop-adapter.js", "plugins.js", "icon.png", "icon@2x.png",
                      "native-client.js", "native-host.js", "native.html",
                      "standalone-background.js", "standalone.html"}
            for name in assets:
                if archive.read(name) != (root / "plugin" / name).read_bytes():
                    raise ValueError(f"Bundled plugin asset is stale: {name}")
            for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
                if archive.read(name) != (root / name).read_bytes():
                    raise ValueError(f"Bundled notice is stale: {name}")
            for path in (root / "licenses").rglob("*"):
                if path.is_file() and archive.read(path.relative_to(root).as_posix()) != path.read_bytes():
                    raise ValueError("Bundled native dependency notices differ.")
            allowed = assets | {"config.json", "bundle.js", "native/cac-signer.exe",
                                "LICENSE", "THIRD_PARTY_NOTICES.md"}
            if not allowed.issubset(names):
                raise ValueError("Release archive is missing required files.")
            bundle = "window.CAC_BUNDLE = " + json.dumps({"version": config["version"]}) + ";\n"
            if archive.read("bundle.js").decode() != bundle:
                raise ValueError("Bundled worker version differs from the manifest.")
            if any(n not in allowed and not n.startswith(("source/", "licenses/")) for n in names):
                raise ValueError("Unexpected file in the release archive.")
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        return [("release", str(error))]
    return []


def audit(root, include_release=True):
    problems = []
    count = 0
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if ".git" in rel.parts:
            continue  # This checks the working tree, not historical Git objects.
        if rel.parts[0] == "release":
            continue
        if path.is_symlink():
            problems.append((str(rel), "symbolic link requires separate review"))
            continue
        if not path.is_file():
            continue
        count += 1
        if (
            path.suffix.lower() in FORBIDDEN_SUFFIXES
            or path.name in FORBIDDEN_NAMES
            or any(
                part in FORBIDDEN_DIRS
                or part.startswith(("backup-", "verification-", "research-"))
                for part in rel.parts
            )
        ):
            problems.append((str(rel), "private or generated file"))
        data = path.read_bytes()
        if path.suffix.lower() == ".png":
            if rel.as_posix() not in (
                "plugin/icon.png",
                "plugin/icon@2x.png",
            ) or not png_has_only_image_chunks(data):
                problems.append((str(rel), "unreviewed image or image metadata"))
        elif path.suffix.lower() not in TEXT_SUFFIXES and path.name not in TEXT_NAMES:
            problems.append((str(rel), "unexpected file type"))
        else:
            try:
                data.decode("utf-8-sig")
            except UnicodeDecodeError:
                problems.append((str(rel), "non-text content"))
        for category, pattern in PATTERNS.items():
            if pattern.search(data):
                problems.append((str(rel), category))
    if include_release:
        problems.extend(audit_release(root))
    return count, problems


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "directory", nargs="?", type=Path, default=Path(__file__).resolve().parent
    )
    args = parser.parse_args()
    count, problems = audit(args.directory.resolve())
    for path, category in problems:
        print(f"FAIL: {path}: {category}")
    print(
        f"{'FAIL' if problems else 'PASS'}: checked {count} files; {len(problems)} findings."
    )
    sys.exit(bool(problems))
