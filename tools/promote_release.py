"""Publish the exact candidate approved in the release-verification PR."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from _paths import ROOT
sys.path.insert(0, str(ROOT / "automation/controller"))
from github_api import api, optional, pages, PUBLIC, OWNER
from pipeline_policy import APP, candidate_run

REPO = "/repos/" + PUBLIC
ASSETS = ("CAC-PDF-Signer.plugin", "SHA256SUMS.txt", "INSTALL.txt", "components.cdx.json", "release-evidence.json")


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def approved_pull(pull, reviews, commit):
    if not (pull.get("merged") and pull["base"]["ref"] == "main"
            and pull["head"]["ref"] == "release-verification"
            and pull["head"]["repo"]["full_name"] == PUBLIC
            and pull["user"]["login"] == APP
            and pull["merged_by"]["login"] == OWNER
            and pull["merge_commit_sha"] == commit):
        raise ValueError("Publication requires the maintainer's merge of the App's verification PR")
    owner_reviews = sorted((r for r in reviews if r["user"]["login"] == OWNER
                            and r["state"] != "COMMENTED"), key=lambda r: r["submitted_at"])
    if not owner_reviews or owner_reviews[-1]["state"] != "APPROVED" or owner_reviews[-1]["commit_id"] != pull["head"]["sha"]:
        raise ValueError("The maintainer must approve the exact verified commit before merging")


def inspect(commit):
    if not re.fullmatch(r"[a-f0-9]{40}", commit):
        raise ValueError("Invalid main commit")
    if api(REPO + "/git/ref/heads/main")["object"]["sha"] != commit:
        raise ValueError("Publication can only resume at the current main commit")
    pulls = pages(REPO + f"/commits/{commit}/pulls")
    matches = [p for p in pulls if p.get("merged_at") and p["base"]["ref"] == "main"
               and p["head"]["ref"] == "release-verification" and p["merge_commit_sha"] == commit]
    if len(matches) != 1:
        raise ValueError("No unique merged verification PR for this commit")
    pull = api(REPO + f"/pulls/{matches[0]['number']}")
    approved_pull(pull, pages(REPO + f"/pulls/{pull['number']}/reviews"), commit)
    candidate = pull["head"]["sha"]
    if api(REPO + "/git/commits/" + candidate)["tree"]["sha"] != api(REPO + "/git/commits/" + commit)["tree"]["sha"]:
        raise ValueError("Merged source differs from the verified candidate")
    runs = pages(REPO + f"/actions/workflows/build-candidate.yml/runs?branch=release-verification&head_sha={candidate}", key="workflow_runs")
    run = max(runs, key=lambda r: (r["id"], r.get("run_attempt", 1))) if runs else None
    if not run or not candidate_run(run, candidate, "release-verification"):
        raise ValueError("The latest candidate run did not pass")
    jobs = pages(REPO + f"/actions/runs/{run['id']}/jobs?filter=latest", key="jobs")
    gates = [j for j in jobs if j["name"] == "Candidate qualification"]
    if len(gates) != 1 or gates[0]["conclusion"] != "success":
        raise ValueError("Candidate qualification is missing or unsuccessful")
    artifacts = pages(REPO + f"/actions/runs/{run['id']}/artifacts", key="artifacts")
    candidates = [a for a in artifacts if a["name"] == "candidate" and not a["expired"]]
    if len(candidates) != 1:
        raise ValueError("Tested candidate expired or is ambiguous; rebuild and reapprove a new candidate")
    return {"main": commit, "candidate": candidate, "run": run["id"], "pr": pull["number"], "artifact": candidates[0]["id"]}


def validate_package(directory, proof):
    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / ".github/release-candidate.json").read_text(encoding="utf-8"))
    version = json.loads((ROOT / "plugin/config.json").read_text(encoding="utf-8"))["version"]
    if manifest["version"] != version or not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Invalid final candidate version")
    digest = sha256(directory / "CAC-PDF-Signer.plugin")
    if (metadata.get("candidate") is not True or metadata.get("harness") != proof["candidate"]
            or metadata["plugin"] != {"tag": "v" + version, "commit": proof["candidate"], "sha256": digest}):
        raise ValueError("Package, tested source and candidate metadata differ")
    checksum = (directory / "SHA256SUMS.txt").read_text(encoding="utf-8").split()
    if checksum != [digest, "CAC-PDF-Signer.plugin"]:
        raise ValueError("Candidate checksum file differs")
    release = ROOT / "release"
    release.mkdir(exist_ok=True)
    for name in ASSETS[:3]:
        (release / name).write_bytes((directory / name).read_bytes())
    from publish_release import check_release
    check_release("v" + version)
    evidence = {"tag": "v" + version, "file": "CAC-PDF-Signer.plugin", "sha256": digest,
                "commit": proof["main"], "candidateCommit": proof["candidate"],
                "candidateRun": proof["run"], "approvalPullRequest": proof["pr"], "schema": 1}
    (directory / "release-evidence.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    return evidence


def publish(directory, proof):
    if inspect(proof["main"]) != proof:
        raise ValueError("Release evidence changed during publication")
    evidence = validate_package(directory, proof)
    tag = evidence["tag"]
    ref = optional(REPO + "/git/ref/tags/" + tag)
    if ref and (ref["object"]["type"] != "commit" or ref["object"]["sha"] != proof["main"]):
        raise ValueError("Existing tag does not identify this approved main commit")
    if not ref:
        api(REPO + "/git/refs", "POST", {"ref": "refs/tags/" + tag, "sha": proof["main"]})
    release = optional(REPO + "/releases/tags/" + tag)
    if not release:
        release = api(REPO + "/releases", "POST", {"tag_name": tag, "name": "CAC PDF Signer " + tag[1:],
            "draft": True, "prerelease": False, "body": (ROOT / "docs/RELEASE_NOTES.md").read_text(encoding="utf-8")})
    existing = {a["name"]: a.get("digest") for a in release["assets"]}
    missing = []
    for name in ASSETS:
        if name in existing and existing[name] != "sha256:" + sha256(directory / name):
            raise ValueError("Existing release asset differs: " + name)
        if name not in existing:
            missing.append(str(directory / name))
    if missing:
        if not release["draft"]:
            raise ValueError("Published release is incomplete; refusing to alter it")
        subprocess.run(["gh", "release", "upload", tag, "--repo", PUBLIC, *missing], check=True)
    uploaded = api(REPO + "/releases/tags/" + tag)
    digests = {a["name"]: a.get("digest") for a in uploaded["assets"]}
    if any(digests.get(name) != "sha256:" + sha256(directory / name) for name in ASSETS):
        raise ValueError("Uploaded asset verification failed")
    if uploaded["draft"]:
        api(REPO + f"/releases/{uploaded['id']}", "PATCH", {"draft": False, "prerelease": False, "make_latest": "true"})
    print("Published verified candidate: https://github.com/" + PUBLIC + "/releases/tag/" + tag)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["inspect", "validate", "publish"])
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    os.environ["APP_TOKEN"] = os.environ["GH_TOKEN"]
    if os.environ.get("GITHUB_REPOSITORY") != PUBLIC or os.environ.get("GITHUB_REF") != "refs/heads/main":
        raise SystemExit("Publication requires the protected main workflow")
    args.directory.mkdir(parents=True, exist_ok=True)
    proof_file = args.directory / "approval.json"
    if args.command == "inspect":
        proof = inspect(os.environ["GITHUB_SHA"])
        proof_file.write_text(json.dumps(proof), encoding="utf-8")
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
            output.write(f"run={proof['run']}\nartifact={proof['artifact']}\n")
    elif args.command == "validate":
        validate_package(args.directory, json.loads(proof_file.read_text(encoding="utf-8")))
    else:
        publish(args.directory, json.loads(proof_file.read_text(encoding="utf-8")))
