"""Private GitHub scheduler; durable state lives on its state branch."""

import argparse
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from release_manifest import resolve as resolve_plugin
from maintenance import window, scheduled_allowed, require_window

PUBLIC = "georgiannElskamp/CAC-PDF-SIGNER"
UPSTREAM = "ONLYOFFICE/DesktopEditors"
PRIVATE = os.environ.get("GITHUB_REPOSITORY", "")
ASSETS = {"windows": "DesktopEditors_x64.exe", "linux": "onlyoffice-desktopeditors_amd64.deb"}


def api(path, method="GET", body=None, dispatch=False, anonymous=False, closing=False):
    if method not in {"GET", "HEAD"}:
        if closing:
            if (method not in {"POST", "PATCH"} or not re.fullmatch(r"/repos/" + re.escape(PRIVATE) + r"/issues(?:/[0-9]+)?", path)
                    or not scheduled_allowed(os.environ.get("GITHUB_EVENT_NAME"), closing=True)):
                raise ValueError("Closing report can only update its private issue on maintenance day")
        else:
            require_window()
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if not anonymous:
        headers["Authorization"] = "Bearer " + os.environ["DISPATCH_TOKEN" if dispatch else "GH_TOKEN"]
    request = urllib.request.Request("https://api.github.com" + path,
        headers=headers, data=None if body is None else json.dumps(body).encode(), method=method)
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read()
        return json.loads(data) if data else None


def now():
    return datetime.now(timezone.utc).isoformat()


def stale(value, hours):
    return not value or datetime.fromisoformat(value.replace("Z", "+00:00")) < datetime.now(timezone.utc) - timedelta(hours=hours)


def report_stale(value):
    cycle = window()
    if cycle["day"]:
        return not value or datetime.fromisoformat(value.replace("Z", "+00:00")) < cycle["start"]
    return stale(value, 35 * 24)


def full_reconciliation_current(pipeline):
    complete = pipeline.get("fullReconciliation", {})
    run_id = str(complete.get("runId") or "")
    if report_stale(complete.get("completedAt")) or not run_id.isdigit():
        return False
    run = api(f"/repos/{PRIVATE}/actions/runs/{run_id}")
    return run.get("conclusion") == "success"


def load_state():
    try:
        item = api(f"/repos/{PRIVATE}/contents/state.json?ref=state")
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
        return {"records": {}}, None
    return json.loads(base64.b64decode(item["content"])), item["sha"]


def save_state(state):
    _, sha = load_state()
    if not sha:
        try:
            ref = api(f"/repos/{PRIVATE}/git/ref/heads/main")
            api(f"/repos/{PRIVATE}/git/refs", "POST", {"ref": "refs/heads/state", "sha": ref["object"]["sha"]})
        except urllib.error.HTTPError as error:
            if error.code != 422:
                raise
    body = {"message": "Update discovery state", "branch": "state",
            "content": base64.b64encode((json.dumps(state, indent=2, sort_keys=True) + "\n").encode()).decode()}
    if sha:
        body["sha"] = sha
    api(f"/repos/{PRIVATE}/contents/state.json", "PUT", body)


def public_file(path, commit):
    item = api(f"/repos/{PUBLIC}/contents/{path}?ref={commit}", anonymous=True)
    return json.loads(base64.b64decode(item["content"]))


def manifest(release):
    tag = release["tag_name"]
    if not re.fullmatch(r"v\d+(?:\.\d+){1,3}", tag) or release["draft"] or release["prerelease"]:
        raise ValueError("Not a stable editor release")
    result = {"version": tag[1:], "releaseId": release["id"], "publishedAt": release["published_at"]}
    for platform, filename in ASSETS.items():
        found = [asset for asset in release["assets"] if asset["name"] == filename]
        if len(found) != 1 or not re.fullmatch(r"sha256:[a-f0-9]{64}", found[0].get("digest") or ""):
            raise ValueError("Missing installer or official checksum: " + filename)
        asset = found[0]
        if asset["browser_download_url"] != f"https://github.com/{UPSTREAM}/releases/download/{tag}/{filename}":
            raise ValueError("Unexpected installer URL")
        result[platform] = {"file": filename, "sha256": asset["digest"][7:], "assetId": asset["id"], "updatedAt": asset["updated_at"]}
    return result


def fingerprint(editor, approved, commit):
    value = {"editor": editor, "plugin": approved["sha256"], "harness": commit,
             "runners": ["windows-2025", "ubuntu-24.04"], "simulation": "debian:12"}
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def reconcile(state, dispatch=True):
    for key, record in state["records"].items():
        if record["status"] not in ("dispatching", "pending"):
            continue
        if not record.get("runId"):
            runs = api(f"/repos/{PUBLIC}/actions/workflows/compatibility-test.yml/runs?event=workflow_dispatch&per_page=100", dispatch=dispatch)["workflow_runs"]
            requested = datetime.fromisoformat(record["requestedAt"]) - timedelta(seconds=1)
            matches = [run for run in runs if key in run["display_title"]
                       and datetime.fromisoformat(run["created_at"].replace("Z", "+00:00")) >= requested]
            if len(matches) == 1:
                record["runId"] = matches[0]["id"]
        if record.get("runId"):
            run = api(f"/repos/{PUBLIC}/actions/runs/{record['runId']}", dispatch=dispatch)
            record.update(status="completed" if run["status"] == "completed" else "pending",
                          conclusion=run.get("conclusion"), url=run["html_url"])
            if run["status"] == "completed":
                record["completedAt"] = run["updated_at"]


def watch(force=False):
    if not scheduled_allowed(os.environ.get("GITHUB_EVENT_NAME")):
        raise RuntimeError("Monthly discovery deadline passed")
    state, _ = load_state()
    reconcile(state)
    branch = os.environ.get("HARNESS_BRANCH", "main")
    if branch not in {"main", "research"}:
        raise ValueError("Unsupported harness branch")
    commit = api(f"/repos/{PUBLIC}/commits/{branch}", anonymous=True)["sha"]
    approved = resolve_plugin(lambda path: api(path, anonymous=True), public_file("tests/approved-plugin.json", commit))
    baseline = tuple(map(int, public_file("tests/editor-installers.json", commit)["version"].split(".")))
    releases, page = [], 1
    while True:
        batch = api(f"/repos/{UPSTREAM}/releases?per_page=100&page={page}", anonymous=True)
        releases.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    state["pendingAssets"] = []
    dispatched = 0
    for release in sorted(releases, key=lambda value: value.get("published_at") or ""):
        tag = release["tag_name"]
        if release["draft"] or release["prerelease"] or not re.fullmatch(r"v\d+(?:\.\d+){1,3}", tag):
            continue
        if tuple(map(int, tag[1:].split("."))) < baseline:
            continue
        try:
            editor = manifest(release)
        except ValueError as error:
            state["pendingAssets"].append({"tag": tag, "reason": str(error)})
            continue
        key = fingerprint(editor, approved, commit)
        record = state["records"].get(key)
        monthly_control = (record and record.get("conclusion") == "success"
                           and record.get("cycle") != window()["id"])
        if record and (record["status"] != "completed" or not (force or monthly_control)):
            continue
        if dispatched >= 3:
            break
        if not scheduled_allowed(os.environ.get("GITHUB_EVENT_NAME")):
            raise RuntimeError("Monthly discovery deadline passed")
        # Save intent first. An ambiguous dispatch is reconciled, not blindly retried.
        state["records"][key] = {"status": "dispatching", "tag": tag, "requestedAt": now(), "harness": commit,
                               "cycle": window()["id"]}
        save_state(state)
        response = api(f"/repos/{PUBLIC}/actions/workflows/compatibility-test.yml/dispatches", "POST",
                       {"ref": branch, "inputs": {"editor_tag": tag, "request_id": key}}, dispatch=True)
        if response and response.get("workflow_run_id"):
            state["records"][key]["runId"] = response["workflow_run_id"]
        state["records"][key]["status"] = "pending"
        save_state(state)
        dispatched += 1
    state["lastSuccessfulPoll"] = now()
    if stale(state.get("lastComponentDispatch"), 24):
        state["lastComponentDispatch"] = now()
        save_state(state)
        api(f"/repos/{PUBLIC}/actions/workflows/component-watch.yml/dispatches", "POST", {"ref": branch}, dispatch=True)
    save_state(state)
    print(f"Dispatched {dispatched}; waiting for assets: {len(state['pendingAssets'])}")


def health():
    state, _ = load_state()
    reconcile(state, dispatch=False)
    problems = []
    if os.environ.get("PIPELINE_ENABLED") == "true":
        try:
            item = api(f"/repos/{PRIVATE}/contents/pipeline.json?ref=state")
            pipeline = json.loads(base64.b64decode(item["content"]))
        except urllib.error.HTTPError as error:
            if error.code != 404:
                raise
            pipeline = {}
        if not full_reconciliation_current(pipeline):
            problems.append("Research controller has no successful reconciliation for the expected maintenance cycle.")
    if report_stale(state.get("lastSuccessfulPoll")):
        problems.append("No successful discovery for the expected maintenance cycle. Check App credentials and the discovery workflow.")
    for key, record in state["records"].items():
        if record["status"] != "completed":
            problems.append(f"{record['tag']}: dispatch {key[:12]} has no completed result. Inspect before manually retrying.")
        elif record.get("cycle") == window()["id"] and record.get("conclusion") != "success":
            problems.append(f"{record['tag']}: compatibility result is {record.get('conclusion')}; review {record.get('url', '')}.")
    for item in state.get("pendingAssets", []):
        problems.append(item["tag"] + ": " + item["reason"])
    if state.get("lastComponentDispatch"):
        runs = api(f"/repos/{PUBLIC}/actions/workflows/component-watch.yml/runs?per_page=1", anonymous=True)["workflow_runs"]
        if (not runs or runs[0]["created_at"] < state["lastComponentDispatch"][:19] or report_stale(runs[0]["created_at"])
                or runs[0]["conclusion"] != "success"):
            problems.append("The monthly component watch is missing, stale, pending or unsuccessful.")
    try:
        item = api(f"/repos/{PRIVATE}/contents/monthly.json?ref=state")
        monthly = json.loads(base64.b64decode(item["content"]))
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
        monthly = {}
    run_id = monthly.get("cycles", {}).get(window()["id"], {}).get("runs", {}).get("discovery")
    discovery = api(f"/repos/{PRIVATE}/actions/runs/{run_id}") if run_id else None
    if not discovery or discovery["conclusion"] != "success":
        problems.append("Monthly dependency/discovery workflow needs attention; dependency updates are not verified.")
    rows = []
    for repo in (PUBLIC, PRIVATE):
        pulls = api(f"/repos/{repo}/pulls?state=open&per_page=100")
        if len(pulls) == 100:
            problems.append(repo + ": PR listing may be incomplete.")
        for pull in pulls:
            sha = pull["head"]["sha"]
            status = api(f"/repos/{repo}/commits/{sha}/status")["state"]
            checks = api(f"/repos/{repo}/commits/{sha}/check-runs?filter=latest&per_page=100")["check_runs"]
            incomplete = sum(c["status"] != "completed" or c["conclusion"] not in {"success", "skipped", "neutral"} for c in checks)
            rows.append(f"- [{repo} #{pull['number']}]({pull['html_url']}), target `{pull['base']['ref']}`, commit `{sha}`. "
                        f"Commit status: {status}; {incomplete} unfinished/unsuccessful check(s).")
    title = "Monthly maintenance " + window()["id"]
    issues = api(f"/repos/{PRIVATE}/issues?state=all&per_page=100")
    issue = next((item for item in issues if item["title"] == title and not item.get("pull_request")
                  and item.get("user", {}).get("login") == "github-actions[bot]"), None)
    body = ("## Maintenance outcome\n\n" + ("\n\n".join(problems) if problems else "Scheduled checks completed. Review the linked PR evidence before approving.")
            + "\n\n## Pull requests awaiting review or integration\n\n" + ("\n".join(rows) or "No open PRs.")
            + f"\n\n[Dependency and editor results](https://github.com/{PRIVATE}/actions/workflows/discovery.yml). "
            + f"[Bundled component findings](https://github.com/{PUBLIC}/issues). "
            + "Native source/SDK/license changes still require maintainer review. "
            + "A release-verification PR must have current passing evidence before owner approval and manual merge. "
            + "No release is approved by this report. Unfinished work waits for an explicit run or the next monthly window.")
    values = {"title": title, "body": body, "state": "open"}
    if issue:
        if issue["body"] != body or issue["state"] != values["state"]:
            api(f"/repos/{PRIVATE}/issues/{issue['number']}", "PATCH", values, closing=True)
    else:
        api(f"/repos/{PRIVATE}/issues", "POST", {"title": title, "body": body}, closing=True)
    print(body)
    if problems:
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["watch", "health"])
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    watch(args.force) if args.command == "watch" else health()
