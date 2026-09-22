"""Stage a successful hosted candidate without replacing an existing release."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.error

from automation import api, REPOSITORY


def validate_run(run):
    if (run["path"] != ".github/workflows/build-candidate.yml" or run["event"] != "workflow_dispatch"
            or run["head_branch"] != "main" or run["status"] != "completed" or run["conclusion"] != "success"
            or not re.fullmatch(r"[a-f0-9]{40}", run["head_sha"])):
        raise ValueError("Select a successful Build candidate run from main")
    return run["head_sha"]


def inspect(run_id):
    if not re.fullmatch(r"[1-9][0-9]{0,19}", run_id):
        raise ValueError("Supply a numeric Build candidate run ID")
    commit = validate_run(api(f"/repos/{REPOSITORY}/actions/runs/{run_id}"))
    comparison = api(f"/repos/{REPOSITORY}/compare/{commit}...main")
    if comparison["status"] not in ("ahead", "identical"):
        raise ValueError("Candidate source is outside main history")
    with open(os.environ["GITHUB_OUTPUT"], "a") as output:
        output.write(f"source_commit={commit}\n")


def optional(path):
    try:
        return api(path)
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
        return None


def stage(source, candidate, commit):
    version = json.loads((source / "plugin/config.json").read_text())["version"]
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?", version):
        raise ValueError("Invalid candidate version")
    tag = "v" + version
    metadata = json.loads((candidate / "metadata.json").read_text())
    digest = hashlib.sha256((candidate / "CAC-PDF-Signer.plugin").read_bytes()).hexdigest()
    if metadata.get("candidate") is not True or metadata["plugin"] != {"tag": tag, "commit": commit, "sha256": digest}:
        raise ValueError("Candidate metadata does not match the tested source and package")
    release = optional(f"/repos/{REPOSITORY}/releases/tags/{tag}")
    if release and not release["draft"]:
        raise ValueError("This version is already published; select a new version before building")
    reference = optional(f"/repos/{REPOSITORY}/git/ref/tags/{tag}")
    if reference and (reference["object"]["type"] != "commit" or reference["object"]["sha"] != commit):
        raise ValueError("The release tag already identifies different source")
    if not reference:
        api(f"/repos/{REPOSITORY}/git/refs", method="POST", body={"ref": "refs/tags/" + tag, "sha": commit})
    if not release:
        subprocess.run(["gh", "release", "create", tag, "--repo", REPOSITORY, "--verify-tag", "--draft",
                        "--title", "CAC PDF Signer " + version, "--notes-file", str(source / "docs/RELEASE_NOTES.md")], check=True)
        release = api(f"/repos/{REPOSITORY}/releases/tags/{tag}")
    existing = {item["name"]: item.get("digest") for item in release["assets"]}
    missing = []
    for name in ("CAC-PDF-Signer.plugin", "SHA256SUMS.txt", "INSTALL.txt", "components.cdx.json"):
        path = candidate / name
        expected = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        if name in existing:
            if existing[name] != expected:
                raise ValueError("Draft already contains different bytes: " + name)
        else:
            missing.append(str(path))
    if missing:
        subprocess.run(["gh", "release", "upload", tag, "--repo", REPOSITORY, *missing], check=True)
    subprocess.run(["gh", "workflow", "run", "release.yml", "--repo", REPOSITORY, "--ref", "main", "--field", "tag=" + tag], check=True)
    print("Draft staged. Publication still requires the release environment approval.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    query = sub.add_parser("inspect")
    query.add_argument("run_id")
    write = sub.add_parser("stage")
    write.add_argument("source", type=Path)
    write.add_argument("candidate", type=Path)
    write.add_argument("commit")
    args = parser.parse_args()
    inspect(args.run_id) if args.command == "inspect" else stage(args.source, args.candidate, args.commit)
