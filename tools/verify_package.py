"""Execute the shipped runtime from a clean, spaced installation path."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import zipfile

from _paths import ROOT

def verify(package, preflight=False):
    root = ROOT
    if sys.platform not in ("win32", "linux"):
        raise ValueError("Package verification supports Windows and Linux.")
    prefix = "native/" if sys.platform == "win32" else "native/linux-" + platform.machine() + "/"
    with tempfile.TemporaryDirectory(prefix="cac-package-") as temporary:
        install = Path(temporary) / "Example User é %PATH% (QA)" / "plugin"
        install.mkdir(parents=True)
        with zipfile.ZipFile(package) as archive:
            manifest = json.loads(archive.read(prefix + "manifest.json"))
            config = json.loads(archive.read("config.json"))
            if manifest["version"] != config["version"]:
                raise ValueError("The native worker and plugin versions differ.")
            for name, expected in manifest["files"].items():
                if name.startswith("/") or ".." in name.split("/") or "\\" in name or ":" in name:
                    raise ValueError("Invalid native file path.")
                data = archive.read(prefix + name)
                if hashlib.sha256(data).hexdigest() != expected:
                    raise ValueError("Native payload checksum failed.")
                target = install / prefix / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            (install / "launch-linux.sh").write_bytes(archive.read("launch-linux.sh"))
        if sys.platform == "win32":
            probe = "const {launchHost}=require('./tests/test_native.js'); process.stdout.write(JSON.stringify(launchHost(process.argv[1])));"
            launch = json.loads(subprocess.check_output(
                ["node", "-e", probe, "onlyoffice://plugin/" + (install / "native.html").as_uri()], cwd=root, encoding="utf-8"))
            command, environment = launch["command"], dict(os.environ, **launch["env"])
        else:
            command, environment = ["/bin/sh", str(install / "launch-linux.sh")], dict(os.environ)
        environment.update(LOCALAPPDATA=str(install.parent / "state"), XDG_DATA_HOME=str(install.parent / "state"))
        operation = "preflight" if preflight else "health"
        result = subprocess.run(command, env=environment, input=json.dumps({"op": operation}) + "\n",
                                capture_output=True, text=True, timeout=60,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            events = [json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")]
            healthy = events[-1]
        except (ValueError, IndexError) as exc:
            raise RuntimeError("The packaged worker did not return a health result: " + result.stderr[-2000:]) from exc
        if result.returncode or not healthy.get("ok") or healthy.get("version") != config["version"]:
            raise RuntimeError("Packaged worker failed: " + json.dumps(healthy))
        if preflight and (not healthy.get("desktopReady") or not healthy.get("recoveryWritable") or healthy.get("cardChecked") is not False):
            raise RuntimeError("The packaged worker did not complete desktop preflight.")
        print(f"PASS: {sys.platform} packaged runtime {config['version']} {operation}; {len(manifest['files'])} native files verified; spaced Unicode installation path.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("--preflight", action="store_true", help="Also check desktop libraries and recovery storage; requires a Linux display. Does not access a card.")
    args = parser.parse_args()
    verify(args.package, args.preflight)
