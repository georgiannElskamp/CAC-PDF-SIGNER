"""Paths for the signing runtime."""

import os
from pathlib import Path

VERSION = "0.5.3"
MAX_PDF = 40 * 1024 * 1024
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
            "Build output must be outside the source repository."
        )
    return path
