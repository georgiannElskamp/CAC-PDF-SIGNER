"""Resolve a published plugin with an immutable source and asset digest."""
import hashlib
import json
import re
import urllib.request

REPO = "georgiannElskamp/CAC-PDF-SIGNER"


def resolve(api, bootstrap):
    release = api(f"/repos/{REPO}/releases/latest")
    tag = release["tag_name"]
    if release["draft"] or release["prerelease"] or not re.fullmatch(r"v\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?", tag):
        raise ValueError("A stable published plugin is required")
    def asset(name):
        rows = [a for a in release["assets"] if a["name"] == name]
        url = f"https://github.com/{REPO}/releases/download/{tag}/{name}"
        if (len(rows) != 1 or rows[0]["browser_download_url"] != url
                or not re.fullmatch(r"sha256:[a-f0-9]{64}", rows[0].get("digest") or "")):
            raise ValueError("Missing or unverified release asset: " + name)
        return rows[0]
    plugin = asset("CAC-PDF-Signer.plugin")
    if tag == bootstrap["tag"]:
        approved = dict(bootstrap)
    else:
        evidence = asset("release-evidence.json")
        with urllib.request.urlopen(evidence["browser_download_url"], timeout=40) as response:
            raw = response.read(65537)
        if len(raw) > 65536 or "sha256:" + hashlib.sha256(raw).hexdigest() != evidence["digest"]:
            raise ValueError("Release evidence bytes changed")
        approved = json.loads(raw)
        if approved.get("schema") != 1:
            raise ValueError("Unknown release evidence schema")
    if (approved.get("tag") != tag or approved.get("file") != "CAC-PDF-Signer.plugin"
            or plugin["digest"] != "sha256:" + approved.get("sha256", "")
            or not re.fullmatch(r"[a-f0-9]{40}", approved.get("commit", ""))):
        raise ValueError("Published plugin and release evidence differ")
    ref = api(f"/repos/{REPO}/git/ref/tags/{tag}")["object"]
    if ref["type"] != "commit" or ref["sha"] != approved["commit"]:
        raise ValueError("Published source tag changed")
    compare = api(f"/repos/{REPO}/compare/{approved['commit']}...main")
    if compare["status"] not in {"identical", "ahead"}:
        raise ValueError("Published source is outside main history")
    return {key: approved[key] for key in ("tag", "file", "sha256", "commit")}
