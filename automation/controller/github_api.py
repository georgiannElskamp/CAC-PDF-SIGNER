"""GitHub API access for the private maintenance controller."""
import base64
import json
import os
import urllib.error
import urllib.request

OWNER = "georgiannElskamp"
PUBLIC = OWNER + "/CAC-PDF-SIGNER"
PRIVATE = OWNER + "/cac-pdf-signer-automation"


def api(path, method="GET", body=None, credential="APP_TOKEN"):
    token = os.environ[credential]
    request = urllib.request.Request("https://api.github.com" + path, method=method,
        data=None if body is None else json.dumps(body).encode(), headers={
            "Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
            "Content-Type": "application/json", "X-GitHub-Api-Version": "2022-11-28"})
    with urllib.request.urlopen(request, timeout=40) as response:
        data = response.read()
        return json.loads(data) if data else None


def optional(path, **kwargs):
    try:
        return api(path, **kwargs)
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
        return None


def pages(path, key=None, **kwargs):
    rows = []
    for page in range(1, 31):
        result = api(path + ("&" if "?" in path else "?") + f"per_page=100&page={page}", **kwargs)
        batch = result[key] if key else result
        rows.extend(batch)
        if len(batch) < 100:
            return rows
    raise RuntimeError("Pagination limit reached; refusing incomplete evidence")


def text_file(path, ref):
    from urllib.parse import quote
    item = api(f"/repos/{PUBLIC}/contents/{path}?ref={quote(ref, safe='')}")
    return base64.b64decode(item["content"]).decode("utf-8")


class State:
    def __init__(self, filename="pipeline.json"):
        if filename not in {"pipeline.json", "monthly.json"}:
            raise ValueError("Unsupported state file")
        self.path = f"/repos/{PRIVATE}/contents/{filename}"
        item = optional(self.path + "?ref=state", credential="GH_TOKEN")
        self.sha = item["sha"] if item else None
        self.data = json.loads(base64.b64decode(item["content"])) if item else {"pulls": {}}

    def save(self):
        body = {"branch": "state", "message": "Record maintenance progress",
                "content": base64.b64encode((json.dumps(self.data, indent=2) + "\n").encode()).decode()}
        if self.sha:
            body["sha"] = self.sha
        result = api(self.path, "PUT", body, credential="GH_TOKEN")
        self.sha = result["content"]["sha"]
