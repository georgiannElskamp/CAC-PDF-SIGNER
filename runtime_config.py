"""Paths and settings for the local signing runtime."""

import json
import os
from pathlib import Path

VERSION = "0.4.1"
MAX_PDF = 40 * 1024 * 1024
DEFAULT_PORT = 47831
APP_NAME = "ONLYOFFICE-CAC-Signature"


def state_directory():
    override = os.environ.get("CAC_SIGNATURE_HOME")
    if override:
        return Path(override).expanduser().resolve()
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        raise RuntimeError(
            "Windows LOCALAPPDATA is unavailable. This integration requires Windows."
        )
    return Path(local) / APP_NAME


def outside_checkout(path):
    path = Path(path).resolve()
    root = Path(__file__).resolve().parent
    if path == root or root in path.parents:
        raise ValueError(
            "Private installation files must be outside the source repository."
        )
    return path


def load_settings(directory=None):
    directory = outside_checkout(directory or state_directory())
    try:
        settings = json.loads((directory / "settings.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise RuntimeError("Run setup_windows.py before starting the helper.") from None
    if not isinstance(settings.get("token"), str) or len(settings["token"]) != 64:
        raise ValueError(
            "Invalid local token. Run setup_windows.py to repair the installation."
        )
    try:
        bytes.fromhex(settings["token"])
    except ValueError:
        raise ValueError("Invalid local token encoding.") from None
    port = settings.get("port")
    if isinstance(port, bool) or not isinstance(port, int) or not 1024 <= port <= 65535:
        raise ValueError("Choose a local port between 1024 and 65535.")
    return settings


def find_onlyoffice(configured=""):
    if configured:
        path = Path(configured).expanduser()
        if path.is_file() and path.name.lower() == "desktopeditors.exe":
            return path.resolve()
        raise ValueError("The configured ONLYOFFICE executable does not exist.")
    candidates = []
    for variable in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        base = os.environ.get(variable)
        if base:
            candidates.extend(
                [
                    Path(base) / "ONLYOFFICE/DesktopEditors/DesktopEditors.exe",
                    Path(base)
                    / "Programs/ONLYOFFICE/DesktopEditors/DesktopEditors.exe",
                ]
            )
    found = next((path for path in candidates if path.is_file()), None)
    if not found:
        raise RuntimeError(
            "ONLYOFFICE Desktop Editors was not found. Supply --onlyoffice with its DesktopEditors.exe path during setup."
        )
    return found
