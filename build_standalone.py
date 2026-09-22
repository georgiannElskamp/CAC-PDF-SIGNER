"""Build the combined plugin from Windows and Linux workers."""

import argparse
import hashlib
import importlib.metadata
import json
import os
import ssl
import subprocess
import sys
import zipfile
from pathlib import Path

from audit_public import audit, source_files
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
    "launch-linux.sh",
    "standalone-background.js",
)
REQUIRED_NOTICES = {
    "pdf-sign-APACHE-2.0.txt",
    "reportlab-BSD-3-Clause.txt",
    "go-BSD-3-Clause.txt",
    "go-x-sys-BSD-3-Clause.txt",
    "openssl-3.0.13-APACHE-2.0.txt",
    "openssl-4.0.2-APACHE-2.0.txt",
    "microsoft-runtime-CPython.txt",
}


def native_licenses():
    directory = ROOT / "licenses"
    for name in REQUIRED_NOTICES:
        if not (directory / name).is_file():
            raise ValueError(f"Required license missing: {name}")
    manifest = json.loads((directory / "manifest.json").read_text())
    for item in manifest["files"]:
        path = directory / item["file"]
        if path.parent != directory or not path.is_file():
            raise ValueError("Invalid license manifest entry.")
        if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError(f"License checksum mismatch: {item['file']}")
    return {
        "licenses/" + path.relative_to(directory).as_posix(): path.read_bytes()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


def build_environment():
    env = os.environ.copy()
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)
    base = Path(sys.base_prefix)
    if sys.platform != "win32":
        env["PATH"] = os.pathsep.join((str(Path(sys.executable).parent), "/usr/bin", "/bin"))
        return env
    windows = Path(os.environ["SystemRoot"])
    env["PATH"] = os.pathsep.join(
        str(path)
        for path in (Path(sys.executable).parent, base, base / "DLLs",
                     windows / "System32", windows)
    )
    return env


def verify_native(executable, bridge):
    from PyInstaller.archive.readers import CArchiveReader

    archive = CArchiveReader(str(executable))
    base = Path(sys.base_prefix)
    expected = {
        "python3.dll": base / "python3.dll",
        "python311.dll": base / "python311.dll",
        "vcruntime140.dll": base / "vcruntime140.dll",
        "libcrypto-3.dll": base / "DLLs/libcrypto-3.dll",
        "libssl-3.dll": base / "DLLs/libssl-3.dll",
        "libffi-8.dll": base / "DLLs/libffi-8.dll",
    }
    dlls = {name.lower(): name for name in archive.toc if name.lower().endswith(".dll")}
    if set(dlls) != set(expected):
        raise ValueError(
            "Unreviewed native library inventory: "
            f"extra={sorted(set(dlls) - set(expected))}, "
            f"missing={sorted(set(expected) - set(dlls))}"
        )
    for name, path in expected.items():
        if archive.extract(dlls[name]) != path.read_bytes():
            raise ValueError(f"Bundled library differs from the Python runtime: {name}")
    if archive.extract("pdfsign-bridge.exe") != bridge.read_bytes():
        raise ValueError("Bundled bridge differs from the pinned release.")


def licenses():
    """Collect dependency licenses for the release archive."""
    from cryptography.hazmat.backends.openssl.backend import backend

    if (
        sys.version_info[:3] != (3, 11, 9)
        or ssl.OPENSSL_VERSION.split()[1] != ("3.0.13" if sys.platform == "win32" else "3.0.14")
        or backend.openssl_version_text().split()[1] != "4.0.2"
    ):
        raise ValueError("Runtime versions changed; update the native license inventory.")
    names = [
        line.split("==")[0]
        for line in (ROOT / "requirements-lock.txt").read_text().splitlines()
        if "==" in line
    ]
    names.append("pyinstaller")
    names.append("setuptools")
    if sys.platform == "linux":
        names.append("python-pkcs11")
    result = native_licenses()
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
    if not python_license.exists():
        python_license = Path(sys.base_prefix) / "lib/python3.11/LICENSE.txt"
    result["licenses/dependencies/Python/LICENSE.txt"] = python_license.read_bytes()
    return result


def build(destination, bridge, reuse_executable=False, linux_bundle=None):
    if sys.platform != "win32" or sys.maxsize <= 2**32:
        raise ValueError("Build with 64-bit Python on Windows.")
    if linux_bundle is None:
        raise ValueError("Supply the Linux bundle for the combined plugin.")
    linux_runtime = linux_bundle / "native/linux-x86_64"
    linux_manifest = json.loads((linux_runtime / "manifest.json").read_text())
    if linux_manifest["version"] != VERSION or linux_manifest["sha256"] != hashlib.sha256((linux_runtime / "cac-signer").read_bytes()).hexdigest():
        raise ValueError("Linux runtime version or checksum differs from its manifest.")
    for name, digest in linux_manifest["runtimeSources"].items():
        if Path(name).name != name or hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
            raise ValueError("Linux worker has stale runtime source: " + name)
    destination = outside_checkout(destination)
    destination.mkdir(parents=True, exist_ok=True)
    count, findings = audit(ROOT, include_release=False)
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
        subprocess.run(command, cwd=destination, env=build_environment(), check=True)
    verify_native(executable, bridge)
    check = subprocess.run(
        [str(executable)],
        input='{"op":"health"}\n',
        text=True,
        capture_output=True,
        timeout=60,
        creationflags=subprocess.CREATE_NO_WINDOW,
        env=build_environment(),
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
    if config["version"] != VERSION or config["variations"][0]["url"] != "standalone.html":
        raise ValueError("Plugin manifest does not match the standalone worker.")
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
        if linux_bundle:
            for path in sorted(linux_bundle.rglob("*")):
                if path.is_file():
                    name = path.relative_to(linux_bundle).as_posix()
                    if not name.startswith(("native/linux-", "licenses/linux/", "native-sources/linux/")):
                        raise ValueError("Unexpected Linux bundle file: " + name)
                    archive.write(path, name)
        for path in source_files(ROOT):
            archive.write(path, "source/" + path.relative_to(ROOT).as_posix())
        for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
            archive.write(ROOT / name, name)
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
    parser.add_argument("--linux-bundle", type=Path, required=True)
    parser.add_argument(
        "--reuse-executable",
        action="store_true",
        help="Repackage assets only; never use after changing Python code.",
    )
    args = parser.parse_args()
    print(build(args.output, args.bridge, args.reuse_executable, args.linux_bundle))
