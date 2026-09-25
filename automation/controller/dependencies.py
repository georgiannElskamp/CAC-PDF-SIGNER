"""Run Dependabot without write credentials; validate proposals before publishing."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

from github_api import api, pages, optional, PUBLIC, PRIVATE, State
from maintenance import claim, window
from pipeline_policy import pin_only

TARGETS = {"python": (PUBLIC, "research", "pip"),
           "actions": (PUBLIC, "research", "github_actions"),
           "controller": (PRIVATE, "main", "github_actions")}
REQUIREMENTS = {"requirements-lock.txt", "requirements-build.txt", "requirements-dev.txt",
                "requirements-linux.txt", "requirements-native-build.txt"}
PINS = Path(__file__).with_name("dependency-tools.json")


def pin_change(before, after):
    pattern = r"(?m)^([\w.-]+)==[\w.+!-]+$"
    return (before != after and re.sub(pattern, r"\1==PIN", before) == re.sub(pattern, r"\1==PIN", after))


def proposals(content, target, base, originals):
    if len(content.encode()) > 2_000_000:
        raise ValueError("Dependabot output exceeds the limit")
    result, completed = [], 0
    for line in content.splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        kind = event.get("type")
        if kind == "mark_as_processed":
            if event.get("data", {}).get("base-commit-sha") != base:
                raise ValueError("Dependency completion has a different base")
            completed += 1
        if kind in {"record_update_job_error", "record_update_job_unknown_error"}:
            raise ValueError("Dependabot reported an incomplete update job")
        if kind not in {"create_pull_request", "update_pull_request"}:
            continue
        data = event["data"]
        if data["base-commit-sha"] != base:
            raise ValueError("Dependency result has a different base commit")
        files = {}
        for row in data["updated-dependency-files"]:
            directory, name = row["directory"], row["name"]
            path = directory.strip("/") + "/" + name if directory.strip("/") else name
            if (row.get("deleted") or path in files or "\\" in path or path.startswith("/")
                    or any(p in {"", ".", ".."} for p in path.split("/"))):
                raise ValueError("Unsafe dependency file")
            value = row["content"]
            if not isinstance(value, str) or len(value.encode()) > 100_000 or "\x00" in value:
                raise ValueError("Unsupported dependency content")
            if target == "python":
                allowed = path in REQUIREMENTS
                check = pin_change
            else:
                allowed = bool(re.fullmatch(r"\.github/workflows/[A-Za-z0-9_-]+\.ya?ml", path))
                check = pin_only
            if not allowed:
                raise ValueError("Unexpected dependency path: " + path)
            original, mode = originals(path)
            if mode != "100644" or not check(original, value):
                raise ValueError("Dependency update is not an existing-file pin-only change: " + path)
            files[path] = value
        if not files or len(files) > 40:
            raise ValueError("Unexpected dependency proposal size")
        result.append(files)
    if completed != 1:
        raise ValueError("Dependabot did not finish exactly one job")
    if len(result) > 1:
        raise ValueError("Expected one grouped proposal per ecosystem")
    return result


def prepare(target, output):
    repo, branch, ecosystem = TARGETS[target]
    base = api(f"/repos/{repo}/git/ref/heads/{branch}", credential="GH_TOKEN")["object"]["sha"]
    output.mkdir(parents=True, exist_ok=True)
    job = {"job": {"package-manager": ecosystem, "source": {"provider": "github", "repo": repo,
                   "branch": branch, "commit": base, "directory": "/"},
                   "allowed-updates": [{"update-type": "all"}],
                   "dependency-groups": [{"name": "monthly", "rules": {"patterns": ["*"]}}],
                   "reject-external-code": target != "python"},
           "credentials": ([] if target == "python" else [{"type": "git_source", "host": "github.com",
                            "username": "x-access-token", "password": "$GH_TOKEN"}])}
    (output / "job.json").write_text(json.dumps(job), encoding="utf-8")
    (output / "metadata.json").write_text(json.dumps({"base": base, "target": target}), encoding="utf-8")


def scan(target, output, executable):
    prepare(target, output)
    pins = json.loads(PINS.read_text())
    image = pins["images"][TARGETS[target][2]]
    command = [executable, "--updater-image", image, "--proxy-image", pins["images"]["proxy"],
               "update", "-f", str(output / "job.json"), "--timeout", "25m"]
    with (output / "result.jsonl").open("w", encoding="utf-8") as stream:
        # Python metadata resolution can execute package build hooks. It receives
        # public sources only and no registry or repository credential.
        environment = {k: v for k, v in os.environ.items() if target != "python" or not re.search(r"TOKEN|SECRET|KEY|PASSWORD", k)}
        subprocess.run(command, stdout=stream, check=True, timeout=1800, env=environment)


def probe(target, output, executable):
    """Exercise a real update from deliberately old, synthetic pins."""
    if target == "controller":
        return
    repo, _, ecosystem = TARGETS[target]
    folder = output / "fixture"
    folder.mkdir(parents=True)
    path = "requirements-lock.txt" if target == "python" else ".github/workflows/check.yml"
    old = ("requests==2.31.0\n" if target == "python" else
           "name: Fixture\non: push\njobs:\n  check:\n    runs-on: ubuntu-latest\n    steps:\n"
           "      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2\n")
    file = folder / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(old, encoding="utf-8")
    for args in (["init", "-b", "research"], ["add", "."],
                 ["-c", "user.name=Dependency fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", "Synthetic dependency fixture"]):
        subprocess.run(["git", *args], cwd=folder, check=True, stdout=subprocess.DEVNULL)
    base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=folder, text=True).strip()
    job = {"job": {"package-manager": ecosystem, "source": {"provider": "github", "repo": repo,
                   "branch": "research", "commit": base, "directory": "/"},
                   "allowed-updates": [{"update-type": "all"}],
                   "dependency-groups": [{"name": "monthly", "rules": {"patterns": ["*"]}}]}}
    job_file = output / "probe-job.json"
    job_file.write_text(json.dumps(job), encoding="utf-8")
    pins = json.loads(PINS.read_text())
    command = [executable, "--updater-image", pins["images"][ecosystem], "--proxy-image", pins["images"]["proxy"],
               "update", "-f", str(job_file), "--local", str(folder), "--timeout", "25m"]
    environment = {k: v for k, v in os.environ.items() if not re.search(r"TOKEN|SECRET|KEY|PASSWORD", k)}
    result = subprocess.run(command, stdout=subprocess.PIPE, text=True, check=True, timeout=1800, env=environment)
    changed = proposals(result.stdout, target, base, lambda filename: (old, "100644") if filename == path else ("", ""))
    if len(changed) != 1 or path not in changed[0]:
        raise ValueError("Dependabot did not produce the expected synthetic pin update")
    print(target + ": real Dependabot synthetic update validated")


def publish(target, output, dry_run=False):
    repo, branch, _ = TARGETS[target]
    credential = "GH_TOKEN" if target == "controller" or dry_run else "APP_TOKEN"
    def request(path, method="GET", body=None):
        return api(f"/repos/{repo}" + path, method, body, credential=credential)
    meta = json.loads((output / "metadata.json").read_text())
    base = meta["base"]
    if meta["target"] != target or not re.fullmatch(r"[a-f0-9]{40}", base):
        raise ValueError("Invalid dependency result identity")
    if request(f"/git/ref/heads/{branch}")["object"]["sha"] != base:
        raise ValueError("Base advanced; retain the proposal for next month's scan or manually rerun")
    tree_sha = request("/git/commits/" + base)["tree"]["sha"]
    tree = request("/git/trees/" + tree_sha + "?recursive=1")
    if tree.get("truncated"):
        raise ValueError("Incomplete dependency source tree")
    entries = {item["path"]: item for item in tree["tree"] if item["type"] == "blob"}
    def original(path):
        item = entries.get(path)
        if not item:
            raise ValueError("Dependency update adds a file")
        blob = request("/git/blobs/" + item["sha"])
        return base64.b64decode(blob["content"]).decode("utf-8"), item["mode"]
    values = proposals((output / "result.jsonl").read_text(encoding="utf-8"), target, base, original)
    if not values:
        print(target + ": no dependency changes")
        return
    files = values[0]
    print(f"{target}: validated {len(files)} pin file(s)")
    if dry_run:
        return
    # One outstanding proposal per ecosystem; never rewrite a reviewed PR.
    prefix = "automation/dependencies-" + target + "-"
    existing = pages(f"/repos/{repo}/pulls?state=open&base={branch}", credential=credential)
    if any(p["head"]["ref"].startswith(prefix) and (p["head"].get("repo") or {}).get("full_name") == repo for p in existing):
        print(target + ": existing dependency PR needs review; no duplicate created")
        return
    digest = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()[:12]
    head = prefix + digest
    # An existing branch may be an interrupted or previously rejected proposal.
    if optional(f"/repos/{repo}/git/ref/heads/{head}", credential=credential):
        raise ValueError("Dependency branch already exists; inspect before retrying")
    if request(f"/git/ref/heads/{branch}")["object"]["sha"] != base:
        raise ValueError("Base changed before dependency publication")
    updated = request("/git/trees", "POST", {"base_tree": tree_sha, "tree": [
        {"path": path, "mode": "100644", "type": "blob", "content": content} for path, content in files.items()]})
    title = "Update " + target + " dependencies"
    commit = request("/git/commits", "POST", {"message": title, "parents": [base], "tree": updated["sha"]})
    request("/git/refs", "POST", {"ref": "refs/heads/" + head, "sha": commit["sha"]})
    result = request("/pulls", "POST", {"base": branch, "head": head, "title": title,
        "body": "Monthly Dependabot proposal. This changes the pinned build inputs. "
                "Required tests and current-commit review must pass before integration. "
                "Controller updates require separate maintainer review and deployment."})
    print(result["html_url"])


def start(dry_run):
    allowed = dry_run or os.environ.get("GITHUB_EVENT_NAME") != "schedule" or claim(State("monthly.json"), "discovery")
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write("run=" + str(allowed).lower() + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("start", "scan", "publish", "probe"))
    parser.add_argument("--target", choices=TARGETS)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--executable", default="./dependabot")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.command == "start":
        start(args.dry_run)
    elif args.command == "scan":
        scan(args.target, args.output, args.executable)
    elif args.command == "probe":
        probe(args.target, args.output, args.executable)
    else:
        publish(args.target, args.output, args.dry_run)
