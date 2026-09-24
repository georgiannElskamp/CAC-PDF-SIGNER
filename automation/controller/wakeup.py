"""Wake the private controller from trusted public repository events."""
import json
import os
import re
from pathlib import Path

from github_api import api, OWNER, PUBLIC, PRIVATE
from pipeline_policy import CODEX, eligible

WORKFLOWS = {".github/workflows/" + name for name in
             ("checks.yml", "dependency-review.yml", "pr-build.yml")}


def pull_numbers(event_name, event):
    if event.get("repository", {}).get("full_name") != PUBLIC:
        return []
    if event_name == "workflow_dispatch":
        number = event.get("inputs", {}).get("pull", "")
        if not re.fullmatch(r"[1-9][0-9]{0,8}", str(number)):
            raise ValueError("A research PR number is required")
        return [int(number)]
    if event_name == "workflow_run":
        run = event.get("workflow_run", {})
        if (event.get("action") != "completed"
                or (run.get("head_repository") or {}).get("full_name") != PUBLIC):
            return []
        if run.get("path") == ".github/workflows/pipeline-activity.yml":
            if run.get("event") not in {"pull_request_target", "pull_request_review", "pull_request_review_comment"}:
                return []
            match = re.fullmatch(r"Research PR ([1-9][0-9]{0,8})", run.get("display_title", ""))
            return [int(match[1])] if match else []
        if run.get("event") != "pull_request" or run.get("path") not in WORKFLOWS:
            return []
        pulls = run.get("pull_requests", [])
        if not pulls:
            sha = run.get("head_sha", "")
            if not re.fullmatch(r"[a-f0-9]{40}", sha):
                return []
            pulls = api(f"/repos/{PUBLIC}/commits/{sha}/pulls", credential="GH_TOKEN")
        return [p["number"] for p in pulls]
    if event_name == "issue_comment":
        issue = event.get("issue", {})
        if (not issue.get("pull_request")
                or event.get("comment", {}).get("user", {}).get("login") not in {OWNER, CODEX}):
            return []
        return [issue["number"]]
    return []


def wake(event_name, event):
    numbers = sorted(set(pull_numbers(event_name, event)))
    if len(numbers) > 100 or any(type(n) is not int or n < 1 for n in numbers):
        raise ValueError("Invalid pull request list")
    current = [n for n in numbers if eligible(api(f"/repos/{PUBLIC}/pulls/{n}", credential="GH_TOKEN"))]
    if not current:
        print("No eligible research PR for this event")
        return False
    if not os.environ.get("CONTROLLER_DISPATCH_TOKEN"):
        raise RuntimeError("Set CONTROLLER_DISPATCH_TOKEN: a fine-grained token with Actions write access only to the private maintenance repository")
    # A full sweep preserves other PRs when GitHub coalesces pending controller runs.
    api(f"/repos/{PRIVATE}/actions/workflows/pipeline.yml/dispatches", "POST",
        {"ref": "main", "inputs": {"dry_run": "false", "pull": "", "release_type": "auto", "event_wakeup": "true"}},
        credential="CONTROLLER_DISPATCH_TOKEN")
    print("Controller notified for research PRs: " + ", ".join(map(str, current)))
    return True


if __name__ == "__main__":
    if os.environ.get("GITHUB_REPOSITORY") != PUBLIC:
        raise SystemExit("Wakeup requires the public plugin repository")
    wake(os.environ["GITHUB_EVENT_NAME"], json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8")))
