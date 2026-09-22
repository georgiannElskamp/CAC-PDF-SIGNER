"""Check a local release, or push it and start GitHub release checks."""

import argparse
import json
import re
import subprocess

from _paths import ROOT
from audit_public import audit

ASSETS = ("CAC-PDF-Signer.plugin", "SHA256SUMS.txt", "INSTALL.txt")


def command(*args):
    return subprocess.run(args, cwd=ROOT, check=True, text=True,
                          stdout=subprocess.PIPE).stdout.strip()


def check_release(tag=None):
    version = json.loads((ROOT / "plugin/config.json").read_text())["version"]
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?", version):
        raise ValueError("Invalid release version.")
    expected = "v" + version
    if tag is not None and tag != expected:
        raise ValueError("Release tag does not match the plugin version.")
    for name in ASSETS:
        if not (ROOT / "release" / name).is_file():
            raise ValueError("Missing release asset: " + name)
    count, findings = audit(ROOT)
    if findings:
        raise ValueError("Release audit failed: " + repr(findings))
    if version not in (ROOT / "docs/RELEASE_NOTES.md").read_text():
        raise ValueError("Release notes have a different version.")
    print(f"Release {expected}: {count} source files and package checks passed.")
    return expected


def publish(tag):
    if command("git", "status", "--porcelain"):
        raise ValueError("Commit the source changes before publishing.")
    remote = command("git", "remote", "get-url", "origin")
    match = re.fullmatch(r"(?:https://github\.com/|git@github\.com:)([\w.-]+/[\w.-]+?)(?:\.git)?", remote)
    if not match:
        raise ValueError("Origin must be a GitHub repository.")
    repo = match[1]
    command("gh", "repo", "view", repo, "--json", "nameWithOwner")
    if command("git", "ls-remote", "--tags", "origin", "refs/tags/" + tag):
        raise ValueError("This release tag already exists. Resume its draft workflow or choose a new version.")
    command("git", "push", "--atomic", "origin", "HEAD:refs/heads/main", "HEAD:refs/tags/" + tag)
    args = ["gh", "release", "create", tag, "--repo", repo, "--verify-tag", "--draft",
            "--title", "CAC PDF Signer " + tag[1:], "--notes-file", "docs/RELEASE_NOTES.md"]
    if "-" in tag:
        args.append("--prerelease")
    command(*args, *(str(ROOT / "release" / name) for name in ASSETS))
    command("gh", "workflow", "run", "release.yml", "--repo", repo,
            "--ref", "main", "--field", "tag=" + tag)
    print(f"Release checks started: https://github.com/{repo}/actions/workflows/release.yml")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", help="Require this version tag (used by CI).")
    parser.add_argument("--publish", action="store_true", help="Push main and the tag, upload a draft, and start release checks.")
    args = parser.parse_args()
    tag = check_release(args.tag)
    if args.publish:
        publish(tag)
