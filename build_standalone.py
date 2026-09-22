"""Build the standalone Windows plugin."""

import argparse
import hashlib
import importlib.metadata
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

from audit_public import audit
from runtime_config import outside_checkout
from standalone_worker import VERSION

ROOT = Path(__file__).resolve().parent
BRIDGE_SHA256 = "0c641a9a326498e90d9d5f887bfe694d389b8e7ee74857b551c240382431b067"
ASSETS = (
    "desktop-adapter.js",
    "plugins.js",
    "icon.png",
    "icon@2x.png",
    "native-client.js",
    "native-host.js",
    "native.html",
    "standalone-background.js",
)


def licenses():
    """Collect dependency licenses for the release archive."""
    names = [
        line.split("==")[0]
        for line in (ROOT / "requirements-lock.txt").read_text().splitlines()
        if "==" in line
    ]
    names.append("pyinstaller")
    names.append("setuptools")
    result = {}
    for name in names:
        distribution = importlib.metadata.distribution(name)
        found = False
        for item in distribution.files or []:
            parts = Path(str(item)).parts
            if any(
                part.lower().startswith(("license", "licence", "copying", "notice"))
                for part in parts
            ):
                file = Path(distribution.locate_file(item))
                if file.is_file():
                    # Keep vendor subdirectories so independent licenses cannot collide.
                    safe_parts = [part for part in parts if part not in (".", "..")]
                    result[f"licenses/dependencies/{name}/" + "/".join(safe_parts)] = (
                        file.read_bytes()
                    )
                    found = True
        if not found:
            raise ValueError(
                f"License file missing for {name}; review the distribution before publishing."
            )
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    result["licenses/dependencies/Python/LICENSE.txt"] = python_license.read_bytes()
    return result


def build(destination, bridge, reuse_executable=False):
    if sys.platform != "win32" or sys.maxsize <= 2**32:
        raise ValueError("Build with 64-bit Python on Windows.")
    destination = outside_checkout(destination)
    destination.mkdir(parents=True, exist_ok=True)
    count, findings = audit(ROOT)
    if findings:
        raise ValueError(f"Source publication audit failed: {findings}")
    if hashlib.sha256(bridge.read_bytes()).hexdigest() != BRIDGE_SHA256:
        raise ValueError(
            "The signing bridge does not match the pinned upstream release."
        )
    notices = licenses()
    executable = destination / "dist" / "cac-signer.exe"
    if not reuse_executable:
        command = [
            sys.executable,
            "-B",
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onefile",
            "--console",
            "--noupx",
            "--name",
            "cac-signer",
            "--distpath",
            str(executable.parent),
            "--workpath",
            str(destination / "work"),
            "--specpath",
            str(destination),
            "--add-binary",
            str(bridge.resolve()) + os.pathsep + ".",
            "--collect-data",
            "pyhanko",
            "--collect-data",
            "tzdata",
            str(ROOT / "standalone_worker.py"),
        ]
        subprocess.run(command, cwd=destination, check=True)
    check = subprocess.run(
        [str(executable)],
        input='{"op":"health"}\n',
        text=True,
        capture_output=True,
        timeout=60,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    events = [json.loads(line) for line in check.stdout.splitlines()]
    if (
        check.returncode
        or not events
        or events[-1].get("version") != VERSION
        or not events[-1].get("ok")
    ):
        raise RuntimeError(
            "Bundled dependency self-check failed: " + check.stdout + check.stderr
        )
    config = json.loads((ROOT / "plugin/config.json").read_text())
    config["version"] = VERSION
    config["variations"][0]["url"] = "standalone.html"
    if config["variations"][0]["type"] != "background":
        raise ValueError("The standalone plugin must be a background plugin.")
    target = destination / "CAC-PDF-Signer.plugin"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("config.json", json.dumps(config, indent=2))
        archive.writestr(
            "bundle.js",
            "window.CAC_BUNDLE = " + json.dumps({"version": VERSION}) + ";\n",
        )
        archive.write(ROOT / "plugin/standalone.html", "standalone.html")
        for name in ASSETS:
            archive.write(ROOT / "plugin" / name, name)
        archive.write(executable, "native/cac-signer.exe")
        for path in sorted(ROOT.rglob("*")):
            if path.is_file() and ".git" not in path.relative_to(ROOT).parts:
                archive.write(path, "source/" + path.relative_to(ROOT).as_posix())
        for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
            archive.write(ROOT / name, name)
        archive.write(
            ROOT / "licenses/pdf-sign-APACHE-2.0.txt",
            "licenses/pdf-sign-APACHE-2.0.txt",
        )
        archive.write(
            ROOT / "licenses/reportlab-BSD-3-Clause.txt",
            "licenses/reportlab-BSD-3-Clause.txt",
        )
        for name, content in notices.items():
            archive.writestr(name, content)
    with zipfile.ZipFile(target) as archive:
        if (
            archive.testzip()
            or "connection.js" in archive.namelist()
            or "settings.json" in archive.namelist()
        ):
            raise RuntimeError("Invalid standalone package.")
    (destination / "SHA256SUMS.txt").write_text(
        hashlib.sha256(target.read_bytes()).hexdigest() + "  " + target.name + "\n",
        encoding="ascii",
    )
    print(
        f"Built {target.name}; source audit {count} files; bundled dependency self-check passed."
    )
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--bridge", required=True, type=Path)
    parser.add_argument(
        "--reuse-executable",
        action="store_true",
        help="Repackage assets only; never use after changing Python code.",
    )
    args = parser.parse_args()
    print(build(args.output, args.bridge, args.reuse_executable))
