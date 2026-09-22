"""Collect a trusted failed workflow's evidence for optional cloud diagnosis."""

import argparse
import json
from pathlib import Path
import re
import subprocess

from automation import api, REPOSITORY


def collect(run_id, output):
    if not re.fullmatch(r"[1-9][0-9]{0,19}", run_id):
        raise ValueError("Supply a numeric compatibility workflow run ID")
    run = api(f"/repos/{REPOSITORY}/actions/runs/{run_id}")
    if (run["path"] != ".github/workflows/compatibility-test.yml" or run["head_branch"] != "main"
            or run["event"] != "workflow_dispatch" or run["status"] != "completed" or run["conclusion"] != "failure"):
        raise ValueError("Diagnosis accepts only a completed failed compatibility run from main")
    comparison = api(f"/repos/{REPOSITORY}/compare/{run['head_sha']}...main")
    if comparison["status"] not in ("ahead", "identical"):
        raise ValueError("The failed source is not in the trusted main history")
    logs = subprocess.run(["gh", "run", "view", run_id, "--repo", REPOSITORY, "--log-failed"],
                          capture_output=True, text=True, encoding="utf-8", check=True, timeout=90).stdout
    logs = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", logs)
    output.mkdir(parents=True, exist_ok=True)
    (output / "run.json").write_text(json.dumps({key: run[key] for key in
        ("id", "html_url", "head_sha", "head_branch", "conclusion", "created_at")}, indent=2) + "\n")
    (output / "failed-checks.txt").write_text(logs[-160000:], encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_id")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    collect(args.run_id, args.output)
