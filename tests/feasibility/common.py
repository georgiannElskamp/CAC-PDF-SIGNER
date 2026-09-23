"""Shared helpers for disposable hosted probes."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
REPORT = Path(os.environ["PROBE_REPORT"])
REPORT.mkdir(parents=True, exist_ok=True)


def hosted():
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted":
        raise RuntimeError("These probes require a disposable GitHub-hosted runner.")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def record(name, **values):
    value = {"probe": name, "source": os.environ.get("GITHUB_SHA"), **values}
    (REPORT / (name + ".json")).write_text(json.dumps(value, indent=2), encoding="utf-8")
    print(json.dumps(value), flush=True)


def extract(package, target):
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(package) as archive:
        for name in archive.namelist():
            if name.startswith("/") or "\\" in name or ":" in name or ".." in name.split("/"):
                raise ValueError("Unsafe package member")
        archive.extractall(target)
    return target


def fetch_candidate():
    hosted()
    destination = Path(os.environ["PROBE_INPUT"])
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination / "candidate.zip"
    with archive.open("wb") as stream:
        subprocess.run(["gh", "api", "/repos/georgiannElskamp/CAC-PDF-SIGNER/actions/artifacts/10723929192/zip"],
                       check=True, stdout=stream, timeout=180)
    expected = "87100f6ad7b4643ea776b18798a19c85a9310d81bd6c93da1f06555eeea9a513"
    if sha(archive) != expected:
        raise ValueError("Candidate archive differs from the recorded passing build")
    extract(archive, destination)
    archive.unlink()
    metadata = json.loads((destination / "metadata.json").read_text())
    package = destination / "CAC-PDF-Signer.plugin"
    if metadata["plugin"]["sha256"] != sha(package):
        raise ValueError("Candidate plugin digest mismatch")
    with zipfile.ZipFile(package) as bundle:
        for name in ("signing.py", "card_selection.py", "standalone_worker.py",
                     "linux_card.py", "plugin/native-host.js"):
            archived = name.removeprefix("plugin/") if name.startswith("plugin/") else "source/" + name
            if bundle.read(archived).replace(b"\r\n", b"\n") != (ROOT / name).read_bytes().replace(b"\r\n", b"\n"):
                raise ValueError("Tested production source differs: " + name)
    record("input", status="passed", pluginSha256=sha(package), archiveSha256=expected,
           candidateCommit=metadata["plugin"]["commit"], candidateRun=35796720185)
    return package


if __name__ == "__main__":
    fetch_candidate()
