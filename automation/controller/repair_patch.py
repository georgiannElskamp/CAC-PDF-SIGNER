"""Validate a bounded Codex patch without executing code in the controller."""
import hashlib
import json
import re
from pathlib import PurePosixPath
from pipeline_policy import PROTECTED


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate patch property")
        result[key] = value
    return result


def parse(body, sha, marker):
    matches = re.findall(r"<cac-repair-patch>\s*(.*?)\s*</cac-repair-patch>", body, re.S)
    if not matches:
        return None
    if len(matches) != 1 or len(matches[0].encode("utf-8")) > 50000:
        raise ValueError("Ambiguous or oversized repair patch")
    patch = json.loads(matches[0], object_pairs_hook=unique_object)
    if (not isinstance(patch, dict) or set(patch) != {"schema", "base", "request", "files"}
            or patch["schema"] != 1 or patch["base"] != sha or patch["request"] != marker):
        raise ValueError("Repair patch does not match this request and commit")
    if not isinstance(patch["files"], list) or not 1 <= len(patch["files"]) <= 5:
        raise ValueError("Repair must modify one to five existing text files")
    seen = set()
    for item in patch["files"]:
        if not isinstance(item, dict) or set(item) != {"path", "beforeSha256", "content"}:
            raise ValueError("Unsupported repair operation")
        path = item["path"]
        if (not isinstance(path, str) or not re.fullmatch(r"[A-Za-z0-9_./-]+", path)
                or path.startswith(("/", *PROTECTED)) or any(p in {"", ".", "..", ".git"} for p in path.split("/"))
                or path in seen or PurePosixPath(path).suffix not in {".py", ".js", ".json", ".html", ".css", ".md", ".txt", ".sh"}):
            raise ValueError("Repair path is outside automatic patch scope")
        if (not isinstance(item["beforeSha256"], str) or not re.fullmatch(r"[a-f0-9]{64}", item["beforeSha256"])
                or not isinstance(item["content"], str) or "\x00" in item["content"]):
            raise ValueError("Invalid text replacement")
        seen.add(path)
    return patch["files"]


def replacement(item, old, mode):
    if mode not in {"100644", "100755"} or hashlib.sha256(old.encode("utf-8")).hexdigest() != item["beforeSha256"]:
        raise ValueError("Original repair file or mode differs")
    if old == item["content"]:
        raise ValueError("Repair contains no change")
    return {"path": item["path"], "mode": mode, "type": "blob", "content": item["content"]}
