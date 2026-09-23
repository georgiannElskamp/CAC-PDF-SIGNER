"""Pure policy checks shared by controller tests."""
import re
from github_api import OWNER, PUBLIC

PERMANENT = {"main", "research", "release-verification"}
APP = "georgiannelskamp-cac-maintenance[bot]"
CODEX = "chatgpt-codex-connector[bot]"
AUTHORS = {OWNER, "dependabot[bot]", CODEX, APP, "github-actions[bot]"}
PROTECTED = ("automation/", ".github/", "tools/prepare_release.py", "tools/promote_release.py",
             "tools/publish_release.py", "tools/audit_public.py", "tools/run_tests.py",
             "tools/build_scope.py", "tools/candidate.py", "tests/test_pipeline", "AGENTS.md")


def eligible(pull):
    return (pull["state"] == "open" and not pull.get("draft")
            and pull["base"]["ref"] == "research"
            and pull["head"]["repo"] and pull["head"]["repo"]["full_name"] == PUBLIC
            and pull["user"]["login"] in AUTHORS
            and pull["head"]["ref"] not in PERMANENT)


def pin_only(before, after):
    pattern = r"(?m)(\buses:\s+[A-Za-z0-9_./-]+)@[a-f0-9]{40}(?:[ \t]+#[^\n]*)?"
    return before != after and re.sub(pattern, r"\1@PIN", before) == re.sub(pattern, r"\1@PIN", after)


def sensitive(files):
    return [row for row in files if any(row[key].startswith(PROTECTED)
            for key in ("filename", "previous_filename") if key in row)]


def next_version(previous, kind):
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)(?:-[A-Za-z0-9.-]+)?", previous)
    if not match or kind not in {"major", "minor", "patch"}:
        raise ValueError("Unsupported version or release type")
    major, minor, patch = map(int, match.groups())
    return {"major": f"{major+1}.0.0", "minor": f"{major}.{minor+1}.0",
            "patch": f"{major}.{minor}.{patch+1}"}[kind]


def candidate_run(run, sha, branch):
    return (run["path"] == ".github/workflows/build-candidate.yml"
            and run["event"] in {"push", "workflow_dispatch"}
            and run["head_branch"] == branch and run["head_sha"] == sha
            and run["status"] == "completed" and run["conclusion"] == "success")


def review_result(sha, request, comments, reviews, inline, reactions):
    since = request["created_at"]
    def fresh(item):
        return item["user"]["login"] == CODEX and (item.get("submitted_at") or item.get("created_at") or "") >= since
    current = {r["id"]: r for r in reviews if fresh(r) and r["commit_id"] == sha}
    findings = [c for c in inline if fresh(c) and c.get("original_commit_id") == sha
                and c.get("pull_request_review_id") in current]
    if findings or any(r.get("state") == "CHANGES_REQUESTED" or re.search(r"\[P[0-3]\]", r.get("body", "")) for r in current.values()):
        return "findings"
    completed = False
    for comment in comments:
        if comment["user"]["login"] != CODEX or comment.get("updated_at", "") < since:
            continue
        body = comment.get("body") or ""
        if "<!-- codex-pull-request-review-summary -->" not in body:
            continue
        for line in body.splitlines():
            stamps = re.findall(r'datetime="([^"]+)"', line)
            if ("Code Review" in line and "Completed" in line and f"`{sha[:7]}`" in line
                    and "Manual request" in line and any(s[:19] >= since[:19] for s in stamps)):
                completed = True
    clean = any(fresh(c) and "Codex Review: Didn't find any major issues." in (c.get("body") or "")
                and re.search(r"\*\*Reviewed commit:\*\* `" + sha[:10] + r"[a-f0-9]*`", c["body"])
                for c in comments)
    positive = any(fresh(r) and r["content"] == "+1" for r in reactions)
    if completed and (clean or positive):
        return "clean"
    if any(fresh(c) and any(t in (c.get("body") or "").lower() for t in
            ("usage limit", "rate limit", "create a codex account", "create an environment")) for c in comments):
        return "unavailable"
    return "pending"
