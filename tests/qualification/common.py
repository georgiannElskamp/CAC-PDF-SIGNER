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


def verify_candidate():
    hosted()
    destination = Path(os.environ["PROBE_INPUT"])
    metadata = json.loads((destination / "metadata.json").read_text(encoding="utf-8"))
    package = destination / "CAC-PDF-Signer.plugin"
    if metadata.get("candidate") is not True or metadata["plugin"]["commit"] != os.environ["GITHUB_SHA"]:
        raise ValueError("Candidate was not built from this tested commit")
    if metadata["plugin"]["sha256"] != sha(package):
        raise ValueError("Candidate plugin digest mismatch")
    with zipfile.ZipFile(package) as bundle:
        for name in ("signing.py", "card_selection.py", "standalone_worker.py",
                     "linux_card.py", "plugin/native-host.js"):
            archived = name.removeprefix("plugin/") if name.startswith("plugin/") else "source/" + name
            if bundle.read(archived).replace(b"\r\n", b"\n") != (ROOT / name).read_bytes().replace(b"\r\n", b"\n"):
                raise ValueError("Tested production source differs: " + name)
    record("input", status="passed", pluginSha256=sha(package),
           candidateCommit=metadata["plugin"]["commit"], candidateRun=os.environ["GITHUB_RUN_ID"])
    return package


if __name__ == "__main__":
    verify_candidate()
