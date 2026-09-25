"""Paths for the signing runtime."""

import os
import sys
from pathlib import Path

VERSION = "0.10.0"
MAX_PDF = 40 * 1024 * 1024
APP_NAME = "ONLYOFFICE-CAC-Signature"


def state_directory():
    override = os.environ.get("CAC_SIGNATURE_HOME")
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "linux":
        local = os.environ.get("XDG_DATA_HOME")
        base = Path(local) if local and Path(local).is_absolute() else Path.home() / ".local/share"
        return base / APP_NAME
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
            "Build output must be outside the source repository."
        )
    return path
