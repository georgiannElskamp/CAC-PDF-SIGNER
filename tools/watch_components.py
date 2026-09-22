"""Track custom native pins separately from Dependabot's package ecosystems."""

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import urllib.request

from automation import ROOT, api, upsert_issue

REPOSITORIES = {"pcsc-lite": "LudovicRousseau/PCSC", "ccid": "LudovicRousseau/CCID"}


def components():
    result = []
    for item in json.loads((ROOT / "native_linux/sources.json").read_text()):
        match = re.fullmatch(r"(.+)-(\d[\d.]+)\.tar\.(?:gz|bz2|xz)", item["file"])
        name, version = match.groups()
        repo = REPOSITORIES.get(name)
        if item["url"].startswith("https://github.com/"):
            repo = "/".join(item["url"].split("/")[3:5])
        result.append({"name": name, "version": version, "sha256": item["sha256"], "url": item["url"], "repository": repo})
    python = json.loads((ROOT / "native_linux/runtime.json").read_text())["python"]
    result.extend([
        {"name": "CPython", "version": python["version"], "sha256": python["sha256"], "url": python["url"], "repository": "python/cpython"},
        {"name": "Windows bridge", "version": "0.1.0", "repository": "192d-Wing/pdf-sign",
         "sha256": "c65fde8bed039378f13ef663781bee2498e4418cb2361a4e94759e39ef5b4910",
         "url": "https://github.com/192d-Wing/pdf-sign/releases/download/v0.1.0/pdfsign-bridge_0.1.0_windows_amd64.zip"},
    ])
    return result


def inventory():
    result = []
    for filename in ("requirements-lock.txt", "requirements-linux.txt"):
        for line in (ROOT / filename).read_text().splitlines():
            match = re.fullmatch(r"([\w.-]+)==([\w.+-]+)", line)
            if match:
                name, version = match.groups()
                entry = {"type": "library", "name": name, "version": version,
                         "purl": f"pkg:pypi/{re.sub(r'[-_.]+', '-', name).lower()}@{version}"}
                if entry not in result:
                    result.append(entry)
    for item in components():
        result.append({"type": "library", "name": item["name"], "version": item["version"],
                       "hashes": [{"alg": "SHA-256", "content": item["sha256"]}],
                       "externalReferences": [{"type": "distribution", "url": item["url"]}]})
    # This records the upstream Python distribution inventory; its notice file describes scope.
    python = json.loads((ROOT / "licenses/linux-python-sources.json").read_text())
    for name, item in python["components"].items():
        result.append({"type": "library", "name": "python-distribution/" + name, "version": item["version"],
                       "hashes": [{"alg": "SHA-256", "content": item["sha256"]}],
                       "externalReferences": [{"type": "distribution", "url": item["url"]}]})
    for item in json.loads((ROOT / "fonts/manifest.json").read_text()):
        if item["file"].endswith((".ttf", ".otf")):
            result.append({"type": "file", "name": item["file"], "hashes": [{"alg": "SHA-256", "content": item["sha256"]}],
                           "externalReferences": [{"type": "distribution", "url": item["url"]}]})
    result.append({"type": "file", "name": "ONLYOFFICE plugin SDK", "hashes": [{"alg": "SHA-256", "content": hashlib.sha256((ROOT / "plugin/plugins.js").read_bytes()).hexdigest()}]})
    return {"bomFormat": "CycloneDX", "specVersion": "1.6", "version": 1, "components": result}


def numeric_tag(tag):
    match = re.fullmatch(r"(?:v|openssl-|R_)?(\d+)[._](\d+)[._](\d+)", tag)
    return tuple(map(int, match.groups())) if match else None


def watch(output):
    rows, errors = [], []
    for item in components():
        try:
            repo = item["repository"]
            # CPython publishes tags rather than GitHub Releases.
            if repo == "python/cpython":
                line = ".".join(item["version"].split(".")[:2])
                upstream = [{"tag_name": value["ref"].removeprefix("refs/tags/")}
                            for value in api(f"/repos/{repo}/git/matching-refs/tags/v{line}.")]
            else:
                upstream = api(f"/repos/{repo}/releases?per_page=100")
            versions = [numeric_tag(value["tag_name"]) for value in upstream if not value.get("prerelease") and not value.get("draft")]
            versions = [value for value in versions if value]
            pinned = tuple(map(int, item["version"].split(".")))
            # Stay on Python's and OpenSSL's existing maintenance lines.
            if item["name"] in ("CPython", "openssl"):
                versions = [value for value in versions if value[:2] == pinned[:2]]
            if not versions:
                raise ValueError("No matching stable upstream version")
            latest = max(versions)
            state = "Update available" if latest > pinned else "Current on tracked line"
            rows.append(f"| {item['name']} | {item['version']} | {'.'.join(map(str, latest))} | {state} |")
        except Exception as error:
            errors.append(item["name"] + ": " + str(error))
            rows.append(f"| {item['name']} | {item['version']} | Unknown | Check failed |")
    sdk_url = "https://onlyoffice.github.io/sdkjs-plugins/v1/plugins.js"
    try:
        with urllib.request.urlopen(sdk_url, timeout=60) as response:
            upstream = hashlib.sha256(response.read(5 * 1024 * 1024)).hexdigest()
        pinned = hashlib.sha256((ROOT / "plugin/plugins.js").read_bytes()).hexdigest()
        sdk_status = "unchanged" if upstream == pinned else "changed; review upstream before replacing"
    except Exception as error:
        sdk_status = "unknown"
        errors.append("SDK: " + str(error))
    advisories = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    for repo in ("openssl/openssl", "python/cpython", "OpenSC/OpenSC", "192d-Wing/pdf-sign"):
        try:
            for item in api(f"/repos/{repo}/security-advisories?per_page=100"):
                published = item.get("published_at")
                if published and datetime.fromisoformat(published.replace("Z", "+00:00")) >= cutoff:
                    advisories.append(f"- [{item['ghsa_id']}]({item['html_url']}) ({repo}); applicability requires review.")
        except Exception as error:
            errors.append(repo + " advisories: " + str(error))
    body = ("| Component | Pinned | Latest tracked | Status |\n| --- | --- | --- | --- |\n" + "\n".join(rows) +
            f"\n\nONLYOFFICE bootstrap SDK: {sdk_status}.\n\n"
            "Recent published repository advisories (90 days):\n" + ("\n".join(advisories) or "None returned by these repositories.") +
            "\n\nCoverage limits: this is a version watch and advisory feed, not an exhaustive vulnerability scan. "
            "Fonts, bundled Python subcomponents, Microsoft/GCC runtimes and the bridge's embedded Go libraries require manual advisory review. "
            "Python packages and Actions are tracked separately by Dependabot. Changes require rebuilt workers, notices and compatibility tests.")
    if errors:
        body += "\n\nIncomplete checks:\n" + "\n".join("- " + error for error in errors)
    output.mkdir(parents=True, exist_ok=True)
    (output / "components.cdx.json").write_text(json.dumps(inventory(), indent=2) + "\n")
    (output / "component-report.md").write_text(body + "\n")
    upsert_issue("components", "Bundled component watch", body)
    if errors:
        raise SystemExit("Some component checks were unavailable; see the report")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--inventory-only", action="store_true")
    args = parser.parse_args()
    if args.inventory_only:
        args.output.write_text(json.dumps(inventory(), indent=2) + "\n")
    else:
        watch(args.output)
