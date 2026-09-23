"""Check a local release package against its source."""

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
    raise ValueError("Publish by approving and merging the release-verification PR into main.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", help="Require this version tag (used by CI).")
    parser.add_argument("--publish", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    tag = check_release(args.tag)
    if args.publish:
        publish(tag)
