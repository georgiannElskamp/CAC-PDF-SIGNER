"""Check source files before packaging."""

import argparse
import re
import struct
import sys
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


def audit(root):
    problems = []
    count = 0
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if ".git" in rel.parts:
            continue  # This checks the working tree, not historical Git objects.
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
