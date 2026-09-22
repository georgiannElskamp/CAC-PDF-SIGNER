"""Install a pinned editor and test the release in a disposable GitHub runner."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import tempfile
import urllib.request


def check(package):
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted":
        raise RuntimeError("This installer is restricted to disposable GitHub-hosted runners.")
    if sys.platform not in ("win32", "linux") or platform.machine().lower() not in ("amd64", "x86_64"):
        raise RuntimeError("The editor installation test requires Windows or Linux x64.")
    root = Path(__file__).resolve().parents[1]
    config = json.loads((root / "tests/editor-installers.json").read_text())
    pin = config["windows" if sys.platform == "win32" else "linux"]
    version = json.loads((root / "plugin/config.json").read_text())["version"]
    with tempfile.TemporaryDirectory(prefix="cac-editor-") as temporary:
        work = Path(temporary)
        installer = work / pin["file"]
        url = f"https://github.com/ONLYOFFICE/DesktopEditors/releases/download/v{config['version']}/{pin['file']}"
        urllib.request.urlretrieve(url, installer)
        if hashlib.sha256(installer.read_bytes()).hexdigest() != pin["sha256"]:
            raise ValueError("The editor installer checksum differs from the pinned release.")
        environment = dict(os.environ)
        if sys.platform == "win32":
            subprocess.run([str(installer), "/VERYSILENT", "/SP-", "/SUPPRESSMSGBOXES", "/NORESTART", "/TASKS="], check=True, timeout=300)
            editor = Path(os.environ["ProgramFiles"]) / "ONLYOFFICE/DesktopEditors/DesktopEditors.exe"
        else:
            subprocess.run(["sudo", "env", "DEBIAN_FRONTEND=noninteractive", "apt-get", "install", "-y", str(installer)], check=True, timeout=300)
            editor = Path("/opt/onlyoffice/desktopeditors/DesktopEditors")
            profile = work / "Example User é" / "profile"
            profile.mkdir(parents=True)
            runtime = profile / "runtime"
            runtime.mkdir(mode=0o700)
            environment.update(HOME=str(profile), XDG_DATA_HOME=str(profile / ".local/share"),
                               XDG_CONFIG_HOME=str(profile / ".config"), XDG_CACHE_HOME=str(profile / ".cache"),
                               XDG_RUNTIME_DIR=str(runtime), QT_QPA_PLATFORM="xcb", GDK_BACKEND="x11")
        pdf = work / "installation-test.pdf"
        subprocess.run(["node", str(root / "tests/editor_smoke.js"), "--fixture", str(pdf)], check=True)
        with (work / "editor.log").open("wb") as log:
            options = {"start_new_session": True} if sys.platform == "linux" else {"creationflags": subprocess.CREATE_NO_WINDOW}
            child = subprocess.Popen([str(editor), "--remote-debugging-port=9251", str(pdf)],
                                     cwd=editor.parent, env=environment, stdout=log, stderr=log, **options)
            try:
                subprocess.run(["node", str(root / "tests/editor_smoke.js"), "--disposable-profile", "9251", str(package.resolve()), version],
                               check=True, timeout=360)
            except Exception:
                log.flush()
                print((work / "editor.log").read_bytes()[-8000:].decode("utf-8", "replace"), file=sys.stderr)
                raise
            finally:
                if sys.platform == "win32":
                    subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    try:
                        os.killpg(child.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                try:
                    child.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    if sys.platform == "linux":
                        os.killpg(child.pid, signal.SIGKILL)
                    else:
                        child.kill()
                    child.wait(timeout=10)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    check(parser.parse_args().package)
