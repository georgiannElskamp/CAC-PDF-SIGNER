"""Prove that incomplete or mismatched evidence cannot qualify an artifact."""
import copy
import json
import os
from pathlib import Path
from common import hosted, record, sha, REPORT

hosted()
required = {"installation", "windows-signing", "linux-signing", "pdf", "lifecycle"}
expected = {"artifact": "a" * 64, "source": "b" * 40}
valid = [{"name": name, "status": "passed", **expected} for name in sorted(required)]


def qualify(rows):
    if len(rows) != len(required) or {x["name"] for x in rows} != required:
        raise ValueError("Missing or duplicate required evidence")
    if any(x.get("status") != "passed" or any(x.get(k) != v for k, v in expected.items()) for x in rows):
        raise ValueError("Failed, stale or mismatched evidence")
    return True


assert qualify(valid)
cases = {}
cases["missing"] = valid[:-1]
cases["duplicate"] = valid[:-1] + [valid[0]]
for key, value in (("status", "skipped"), ("status", "cancelled"), ("status", "failed"),
                   ("artifact", "c" * 64), ("source", "d" * 40)):
    rows = copy.deepcopy(valid)
    rows[0][key] = value
    cases[key + "-" + value[:8]] = rows
for name, rows in cases.items():
    try:
        qualify(rows)
    except ValueError:
        continue
    raise AssertionError("False qualification: " + name)
record("gate", status="passed", negativeControls=list(cases),
       scope="Prototype evidence policy, not an installed release gate")
