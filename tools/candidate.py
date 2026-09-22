"""Prepare hosted build inputs and an audited candidate's release files."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import tarfile
import zipfile

from _paths import ROOT
from automation import download
from audit_public import audit
from watch_components import inventory

BRIDGE_URL = "https://github.com/192d-Wing/pdf-sign/releases/download/v0.1.0/pdfsign-bridge_0.1.0_windows_amd64.zip"
BRIDGE_ARCHIVE_SHA256 = "c65fde8bed039378f13ef663781bee2498e4418cb2361a4e94759e39ef5b4910"


def inputs(directory):
    directory.mkdir(parents=True, exist_ok=True)
    archive = directory / "bridge.zip"
    download(BRIDGE_URL, archive, BRIDGE_ARCHIVE_SHA256)
    with zipfile.ZipFile(archive) as source:
        matches = [name for name in source.namelist() if Path(name).name == "pdfsign-bridge.exe"]
        if len(matches) != 1:
            raise ValueError("Unexpected bridge archive")
        (directory / "pdfsign-bridge.exe").write_bytes(source.read(matches[0]))
    with tarfile.open(directory / "linux-bundle.tar") as source:
        source.extractall(directory / "linux-bundle", filter="data")


def finish(directory):
    version = json.loads((ROOT / "plugin/config.json").read_text())["version"]
    installation = (f"CAC PDF Signer {version}\n\n"
                    "Install CAC-PDF-Signer.plugin through ONLYOFFICE Plugin Manager, then enable it under Background plugins.\n"
                    "See the corresponding source documentation for platform requirements and validation limits.\n"
                    "Check the release page for approval status and compatibility evidence.\n")
    release = ROOT / "release"
    release.mkdir(exist_ok=True)
    for name in ("CAC-PDF-Signer.plugin", "SHA256SUMS.txt"):
        (release / name).write_bytes((directory / name).read_bytes())
    (release / "INSTALL.txt").write_text(installation, encoding="utf-8")
    count, findings = audit(ROOT)
    if findings:
        raise ValueError("Candidate audit failed: " + repr(findings))
    print(f"Candidate audit passed: {count} source files")
    (directory / "INSTALL.txt").write_text(installation, encoding="utf-8")
    (directory / "editor.json").write_bytes((ROOT / "tests/editor-installers.json").read_bytes())
    metadata = {"plugin": {"tag": "v" + version, "commit": os.environ["GITHUB_SHA"],
                           "sha256": hashlib.sha256((directory / "CAC-PDF-Signer.plugin").read_bytes()).hexdigest()},
                "harness": os.environ["GITHUB_SHA"], "candidate": True}
    (directory / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    (directory / "components.cdx.json").write_text(json.dumps(inventory(), indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["inputs", "finish"])
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    inputs(args.directory) if args.command == "inputs" else finish(args.directory)
