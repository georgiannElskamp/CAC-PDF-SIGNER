"""Require a hosted candidate build for changes to shipped code or toolchains."""

import os
from pathlib import PurePosixPath
import re
import subprocess


def requires_build(paths):
    files = {"requirements-lock.txt", "requirements-linux.txt", "requirements-build.txt", "requirements-native-build.txt", ".python-version",
             "tools/build_standalone.py", "tools/build_linux.py", "tools/bundle_manifest.py",
             "tools/candidate.py", ".github/workflows/build-candidate.yml", ".github/workflows/candidate-checks.yml"}
    prefixes = ("plugin/", "native_linux/", "fonts/", "licenses/")
    return any(path in files or path.startswith(prefixes)
               or (len(PurePosixPath(path).parts) == 1 and path.endswith(".py")) for path in paths)


if __name__ == "__main__":
    base, head = os.environ["BASE"], os.environ["HEAD"]
    if not all(re.fullmatch(r"[a-f0-9]{40}", ref) for ref in (base, head)):
        raise SystemExit("Invalid pull request commit IDs")
    paths = subprocess.check_output(["git", "diff", "--name-only", "-z", base, head]).decode().split("\0")
    required = requires_build(paths)
    with open(os.environ["GITHUB_OUTPUT"], "a") as output:
        output.write(f"required={str(required).lower()}\n")
    print("Full hosted candidate build required" if required else "Source/workflow checks cover this change")
