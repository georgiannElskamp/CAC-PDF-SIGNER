"""Set up the legacy signing helper."""

import argparse
import hashlib
import io
import json
import os
import platform
import secrets
import shutil
import subprocess
import sys
import urllib.request
import venv
import zipfile
from pathlib import Path

from build_plugin import build
from runtime_config import (
    DEFAULT_PORT,
    find_onlyoffice,
    load_settings,
    outside_checkout,
    state_directory,
)

ROOT = Path(__file__).resolve().parent
BRIDGE_URL = "https://github.com/192d-Wing/pdf-sign/releases/download/v0.1.0/pdfsign-bridge_0.1.0_windows_amd64.zip"
BRIDGE_ZIP_SHA256 = "c65fde8bed039378f13ef663781bee2498e4418cb2361a4e94759e39ef5b4910"
BRIDGE_EXE_SHA256 = "0c641a9a326498e90d9d5f887bfe694d389b8e7ee74857b551c240382431b067"
HELPER_FILES = [
    "helper.py",
    "signing.py",
    "runtime_config.py",
    "card_selection.py",
    "visible_signature.py",
    "save_dialog.py",
]


def prepare_settings(directory, port=DEFAULT_PORT, onlyoffice=""):
    directory = outside_checkout(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "settings.json"
    if path.exists():
        settings = load_settings(directory)
    else:
        settings = {"port": port, "token": secrets.token_hex(32), "onlyofficePath": ""}
    if not 1024 <= port <= 65535:
        raise ValueError("Choose a port between 1024 and 65535.")
    settings["port"] = port
    settings["onlyofficePath"] = str(
        find_onlyoffice(onlyoffice or settings.get("onlyofficePath", ""))
    )
    temporary = directory / "settings.json.tmp"
    temporary.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    os.replace(temporary, path)
    return settings


def install_bridge(directory, archive_path=None):
    directory = outside_checkout(directory)
    target = directory / "pdfsign-bridge.exe"
    if (
        target.exists()
        and hashlib.sha256(target.read_bytes()).hexdigest() == BRIDGE_EXE_SHA256
    ):
        return target
    if archive_path:
        archive_bytes = Path(archive_path).read_bytes()
    else:
        request = urllib.request.Request(
            BRIDGE_URL, headers={"User-Agent": "ONLYOFFICE-CAC-Signature-Setup"}
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            archive_bytes = response.read(32 * 1024 * 1024 + 1)
    if hashlib.sha256(archive_bytes).hexdigest() != BRIDGE_ZIP_SHA256:
        raise ValueError(
            "The bridge download did not match the pinned release checksum."
        )
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        matches = [
            name
            for name in archive.namelist()
            if Path(name).name == "pdfsign-bridge.exe"
        ]
        if len(matches) != 1:
            raise ValueError("Unexpected bridge archive layout.")
        binary = archive.read(matches[0])
    if hashlib.sha256(binary).hexdigest() != BRIDGE_EXE_SHA256:
        raise ValueError("The signing bridge did not match its pinned checksum.")
    target.write_bytes(binary)
    return target


def prepare(
    directory,
    port=DEFAULT_PORT,
    onlyoffice="",
    archive_path=None,
    install_dependencies=True,
):
    directory = outside_checkout(directory)
    prepare_settings(directory, port, onlyoffice)
    install_bridge(directory, archive_path)
    app = directory / "app"
    app.mkdir(exist_ok=True)
    for name in HELPER_FILES:
        shutil.copy2(ROOT / name, app / name)
    shutil.copy2(ROOT / "LICENSE", app / "LICENSE")
    shutil.copy2(
        ROOT / "licenses/pdf-sign-APACHE-2.0.txt",
        directory / "pdfsign-bridge-LICENSE.txt",
    )
    runtime = directory / "runtime"
    python = runtime / "Scripts/python.exe"
    if install_dependencies:
        if not python.exists():
            venv.EnvBuilder(with_pip=True).create(runtime)
        subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "-r",
                str(ROOT / "requirements-lock.txt"),
            ],
            check=True,
        )
    # Relative launcher paths remain valid for account names and paths containing spaces.
    (directory / "Start CAC Helper.cmd").write_text(
        '@echo off\nset "CAC_SIGNATURE_HOME=%~dp0"\nstart "" "%~dp0runtime\\Scripts\\pythonw.exe" "%~dp0app\\helper.py"\n',
        encoding="utf-8",
    )
    return build(directory)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir", type=Path, help="Private installation folder outside the checkout"
    )
    parser.add_argument(
        "--onlyoffice",
        default="",
        help="Path to DesktopEditors.exe if autodetection fails",
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--bridge-zip",
        type=Path,
        help="Use an already-downloaded official bridge archive",
    )
    args = parser.parse_args()
    if sys.platform != "win32" or platform.architecture()[0] != "64bit":
        parser.error("64-bit Windows and 64-bit Python are required.")
    if sys.version_info < (3, 11):
        parser.error("Python 3.11 or newer is required; 3.11 is the tested version.")
    directory = outside_checkout(args.data_dir or state_directory())
    package = prepare(directory, args.port, args.onlyoffice, args.bridge_zip)
    print("Setup complete. Start the helper with:", directory / "Start CAC Helper.cmd")
    print("Install this private file using ONLYOFFICE Plugin Manager:", package)
    print("Do not upload the private installation folder or generated package.")
