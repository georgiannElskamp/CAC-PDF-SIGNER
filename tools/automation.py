"""Resolve official releases and report hosted compatibility checks."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request

REPOSITORY = "georgiannElskamp/CAC-PDF-SIGNER"
UPSTREAM = "ONLYOFFICE/DesktopEditors"
ROOT = Path(__file__).resolve().parents[1]
ASSETS = {"windows": "DesktopEditors_x64.exe", "linux": "onlyoffice-desktopeditors_amd64.deb"}
TAG = re.compile(r"v[0-9]+(?:\.[0-9]+){1,3}\Z")
SHA256 = re.compile(r"[a-f0-9]{64}\Z")


def api(path, *, method="GET", body=None):
    if not path.startswith("/") or ".." in path.split("/"):
        raise ValueError("Invalid GitHub API path")
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    token = os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = "Bearer " + token
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request("https://api.github.com" + path, data=data, headers=headers, method=method)
    # Retrying writes can duplicate issues or dispatches after an ambiguous response.
    attempts = 3 if method == "GET" else 1
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                raw = response.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as error:
            if attempt + 1 == attempts or error.code not in (429, 500, 502, 503, 504):
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt + 1 == attempts:
                raise
        time.sleep(2 ** attempt)


def validate_manifest(manifest):
    if not TAG.fullmatch("v" + str(manifest.get("version", ""))):
        raise ValueError("Invalid editor version")
    for platform, name in ASSETS.items():
        pin = manifest.get(platform, {})
        if pin.get("file") != name or not SHA256.fullmatch(str(pin.get("sha256", ""))):
            raise ValueError("Missing or invalid official installer: " + platform)
    return manifest


def editor_manifest(release):
    tag = release.get("tag_name", "")
    if release.get("draft") or release.get("prerelease") or not TAG.fullmatch(tag):
        raise ValueError("Only stable Desktop Editors releases are accepted")
    result = {"version": tag[1:], "releaseId": release["id"], "publishedAt": release["published_at"]}
    for platform, filename in ASSETS.items():
        assets = [item for item in release.get("assets", []) if item["name"] == filename]
        if len(assets) != 1:
            raise ValueError("Release assets incomplete: " + filename)
        item = assets[0]
        digest = item.get("digest") or ""
        expected_url = f"https://github.com/{UPSTREAM}/releases/download/{tag}/{filename}"
        if not digest.startswith("sha256:") or not SHA256.fullmatch(digest[7:]):
            raise ValueError("Official SHA-256 digest unavailable: " + filename)
        if item.get("browser_download_url") != expected_url:
            raise ValueError("Unexpected official installer URL")
        result[platform] = {"file": filename, "sha256": digest[7:], "assetId": item["id"], "updatedAt": item["updated_at"]}
    return validate_manifest(result)


def resolve_editor(tag):
    if tag and not TAG.fullmatch(tag):
        raise ValueError("Invalid editor release tag")
    endpoint = "tags/" + tag if tag else "latest"
    return editor_manifest(api(f"/repos/{UPSTREAM}/releases/{endpoint}"))


def download(url, destination, digest):
    if not SHA256.fullmatch(digest):
        raise ValueError("Invalid expected checksum")
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".partial")
    try:
        for attempt in range(3):
            try:
                actual = hashlib.sha256()
                # Public asset URLs need no token, including after redirects to asset storage.
                with urllib.request.urlopen(url, timeout=120) as response, temporary.open("wb") as output:
                    while chunk := response.read(1024 * 1024):
                        actual.update(chunk)
                        output.write(chunk)
                if actual.hexdigest() != digest:
                    raise ValueError("Downloaded asset checksum differs from the approved digest")
                temporary.replace(destination)
                return
            except (urllib.error.URLError, TimeoutError):
                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)
    finally:
        temporary.unlink(missing_ok=True)


def combination(manifest, approved, harness):
    values = {"editor": manifest, "plugin": approved["sha256"], "harness": harness,
              "runners": ["windows-2025", "ubuntu-24.04"], "simulation": "debian:12"}
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


def prepare(tag, output):
    output.mkdir(parents=True, exist_ok=True)
    approved = json.loads((ROOT / "tests/approved-plugin.json").read_text())
    manifest = resolve_editor(tag)
    release = api(f"/repos/{REPOSITORY}/releases/tags/{approved['tag']}")
    if release["draft"] or release["prerelease"]:
        raise ValueError("The approved plugin must be published and marked stable")
    assets = [item for item in release["assets"] if item["name"] == approved["file"]]
    if len(assets) != 1 or assets[0].get("digest") != "sha256:" + approved["sha256"]:
        raise ValueError("The approved plugin asset changed")
    url = f"https://github.com/{REPOSITORY}/releases/download/{approved['tag']}/{approved['file']}"
    if assets[0]["browser_download_url"] != url:
        raise ValueError("Unexpected plugin URL")
    download(url, output / approved["file"], approved["sha256"])
    (output / "editor.json").write_text(json.dumps(manifest, indent=2) + "\n")
    metadata = {"editor": manifest, "plugin": approved, "harness": os.environ["GITHUB_SHA"],
                "combination": combination(manifest, approved, os.environ["GITHUB_SHA"])}
    (output / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    with open(os.environ["GITHUB_OUTPUT"], "a") as stream:
        stream.write(f"editor_tag=v{manifest['version']}\nplugin_version={approved['tag'][1:]}\nsource_commit={approved['commit']}\n")


def upsert_issue(marker, title, body):
    if not re.fullmatch(r"[a-z0-9:.-]+", marker):
        raise ValueError("Invalid issue marker")
    footer = f"<!-- cac-automation:{marker} -->"
    existing = None
    page = 1
    while True:
        issues = api(f"/repos/{REPOSITORY}/issues?state=all&per_page=100&page={page}")
        existing = next((i for i in issues if not i.get("pull_request") and footer in (i.get("body") or "")
                         and i.get("user", {}).get("login") == "github-actions[bot]"), None)
        if existing or len(issues) < 100:
            break
        page += 1
    content = {"title": title, "body": body.rstrip() + "\n\n" + footer}
    if existing:
        if existing["body"] != content["body"] or existing["title"] != title:
            return api(f"/repos/{REPOSITORY}/issues/{existing['number']}", method="PATCH", body=content)
        return existing
    return api(f"/repos/{REPOSITORY}/issues", method="POST", body=content)


def report(directory):
    metadata = json.loads((directory / "metadata.json").read_text())
    manifest = validate_manifest(metadata["editor"])
    results = sorted(directory.glob("result-*.json"))
    expected = {"windows-2025", "ubuntu-24.04", "simulation"}
    rows, seen = [], set()
    prerequisites = json.loads(os.environ.get("PREREQUISITES", "{}"))
    successful = all(value == "success" for value in prerequisites.values())
    for path in results:
        item = json.loads(path.read_text())
        name = item["platform"]
        if name not in expected or name in seen:
            raise ValueError("Unexpected or duplicate result")
        seen.add(name)
        passed = item.get("passed") is True
        successful &= passed
        rows.append(f"| {name} | {'Passed' if passed else 'Failed / incomplete'} | {item.get('baseline', 'Not needed')} |")
    for missing in sorted(expected - seen):
        successful = False
        rows.append(f"| {missing} | Missing result | Unknown |")
    run = f"https://github.com/{REPOSITORY}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
    state = "Passed automated coverage" if successful else "Investigation required"
    body = (f"**{state}** for Desktop Editors v{manifest['version']}.\n\n"
            f"Plugin: `{metadata['plugin']['tag']}`; SHA-256 `{metadata['plugin']['sha256']}`.\n"
            f"Harness: `{metadata['harness']}`. [Run and reports]({run}).\n\n"
            "| Test | Result | Approved editor control |\n| --- | --- | --- |\n" + "\n".join(rows) +
            "\n\nWindows covers installation, background startup, preflight, removal and reinstallation. "
            "Linux adds a software-token signing test. These checks do not validate a physical CAC or reader. "
            "A failed test alone does not establish an adapter defect; inspect its stage and baseline control.\n\n"
            f"Source/package prerequisites: `{json.dumps(prerequisites, sort_keys=True)}`.\n\n"
            "The published plugin and approved editor pin are unchanged.")
    upsert_issue("editor:" + str(manifest["releaseId"]), f"Compatibility: ONLYOFFICE v{manifest['version']}", body)
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as stream:
        stream.write(body + "\n")
    if not successful:
        raise SystemExit("Compatibility coverage did not pass")


def result(output, platform, steps):
    statuses = json.loads(steps)
    required = ["runtime", "editor"] if platform != "simulation" else ["signing"]
    passed = all(statuses.get(name, {}).get("outcome") == "success" for name in required)
    baseline = statuses.get("baseline", {}).get("outcome", "skipped")
    value = {"platform": platform, "passed": passed, "baseline": baseline,
             "runnerImage": os.environ.get("ImageVersion", "container"),
             "steps": {name: item.get("outcome") for name, item in statuses.items()}}
    output.mkdir(parents=True, exist_ok=True)
    (output / f"result-{platform}.json").write_text(json.dumps(value, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare_parser = sub.add_parser("prepare")
    prepare_parser.add_argument("--tag", default="")
    prepare_parser.add_argument("--output", type=Path, required=True)
    report_parser = sub.add_parser("report")
    report_parser.add_argument("directory", type=Path)
    result_parser = sub.add_parser("result")
    result_parser.add_argument("directory", type=Path)
    result_parser.add_argument("platform", choices=["windows-2025", "ubuntu-24.04", "simulation"])
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.tag, args.output)
    elif args.command == "report":
        report(args.directory)
    else:
        result(args.directory, args.platform, os.environ["TEST_STEPS"])
