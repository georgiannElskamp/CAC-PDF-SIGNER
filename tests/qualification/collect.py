"""Keep the outcome of every probe, including failures and missing reports."""
import json
import os
from pathlib import Path
import sys
root=Path(sys.argv[1])
reports=[]
for file in sorted(root.rglob("*.json")):
    try:
        data=json.loads(file.read_text(encoding="utf-8"))
    except ValueError:
        data={"status":"malformed","file":str(file.relative_to(root))}
    reports.append({"file":str(file.relative_to(root)),"result":data})
jobs=json.loads(os.environ["PROBE_JOBS"])
report={"purpose":"Automated candidate qualification; hardware and diagnostic limits remain explicit",
        "testCommit":os.environ["GITHUB_SHA"],"run":os.environ["GITHUB_RUN_ID"],
        "jobs":jobs,"reports":reports,
        "allRequiredJobsPassed":all(v["result"] == "success" for v in jobs.values())}
target=Path(sys.argv[2])
target.write_text(json.dumps(report,indent=2),encoding="utf-8")
print(json.dumps({"jobs":{k:v["result"] for k,v in jobs.items()},"reportCount":len(reports)}))
with open(os.environ["GITHUB_STEP_SUMMARY"],"a",encoding="utf-8") as out:
    out.write("## Candidate qualification\n\n")
    out.write("This report does not authorize publication. Failed, missing and diagnostic results remain visible.\n\n")
    for name,value in jobs.items():out.write(f"- {name}: {value['result']}\n")
