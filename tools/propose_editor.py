"""Propose an editor-pin change only after the compatibility matrix passes."""

import json
import os
from pathlib import Path
import sys
import urllib.error

from automation import api, REPOSITORY, ROOT, validate_manifest


def propose(directory):
    metadata = json.loads((directory / "metadata.json").read_text())
    editor = validate_manifest(metadata["editor"])
    pin = {"version": editor["version"], **{platform: {key: editor[platform][key] for key in ("file", "sha256")}
                                          for platform in ("windows", "linux")}}
    if pin == json.loads((ROOT / "tests/editor-installers.json").read_text()):
        print("Approved editor pin already matches")
        return
    base = api(f"/repos/{REPOSITORY}/git/ref/heads/research")["object"]["sha"]
    if base != metadata["harness"]:
        print("Research advanced during testing; rerun compatibility before proposing a pin")
        return
    branch = f"automation/editor-v{editor['version']}-{editor['linux']['sha256'][:8]}"
    try:
        api(f"/repos/{REPOSITORY}/git/ref/heads/{branch}")
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
    else:
        print("A proposal branch already exists; leaving it for maintainer review")
        return
    run = f"https://github.com/{REPOSITORY}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
    report = (f"# Automated editor compatibility\n\nDesktop Editors **{editor['version']}** passed the hosted checks "
              f"using plugin `{metadata['plugin']['tag']}`. [Evidence]({run}).\n\n"
              "Windows and Linux installation, background startup and removal were tested. Linux signing used a software token. "
              "Physical card and reader coverage remains as recorded in TESTING.md.\n")
    tree_sha = api(f"/repos/{REPOSITORY}/git/commits/{base}")["tree"]["sha"]
    tree = api(f"/repos/{REPOSITORY}/git/trees", method="POST", body={"base_tree": tree_sha, "tree": [
        {"path": "tests/editor-installers.json", "mode": "100644", "type": "blob", "content": json.dumps(pin, indent=2) + "\n"},
        {"path": "docs/COMPATIBILITY.md", "mode": "100644", "type": "blob", "content": report}]})
    commit = api(f"/repos/{REPOSITORY}/git/commits", method="POST", body={"message": "Record tested ONLYOFFICE " + editor["version"],
                 "tree": tree["sha"], "parents": [base]})
    api(f"/repos/{REPOSITORY}/git/refs", method="POST", body={"ref": "refs/heads/" + branch, "sha": commit["sha"]})
    pull = api(f"/repos/{REPOSITORY}/pulls", method="POST", body={"head": branch, "base": "research", "draft": False,
        "title": "Validate ONLYOFFICE " + editor["version"],
        "body": f"The unchanged published plugin passed [hosted compatibility checks]({run}). Update the approved installer pin and record that evidence.\n\nReview the editor hashes and coverage before merging. This does not rebuild or publish a plugin. Hardware coverage is unchanged."})
    print(pull["html_url"])
    api(f"/repos/{REPOSITORY}/actions/workflows/checks.yml/dispatches", method="POST", body={"ref": branch})


if __name__ == "__main__":
    propose(Path(sys.argv[1]))
