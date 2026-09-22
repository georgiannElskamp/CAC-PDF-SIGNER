"""Install a pinned editor and test the release in a disposable GitHub runner."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import sys
import tempfile
import urllib.request


def stop_windows_editor(directory):
    import _winapi

    # The launcher can exit before its editor and helper processes.
    root = Path(directory).resolve(strict=True)
    powershell = ["powershell", "-NoProfile", "-NonInteractive", "-Command"]
    inventory = subprocess.run(powershell + [
        "[Console]::OutputEncoding=[Text.UTF8Encoding]::new(); "
        "ConvertTo-Json -Compress -InputObject @(Get-CimInstance Win32_Process | "
        "Select-Object ProcessId,ParentProcessId,ExecutablePath)"
    ], check=True, timeout=30, capture_output=True, encoding="utf-8")
    processes = json.loads(inventory.stdout)
    identifiers = set()
    for process in processes:
        path = process.get("ExecutablePath")
        if not path:
            continue
        try:
            executable = Path(path).resolve(strict=True)
        except OSError:
            continue
        if root in executable.parents:
            identifiers.add(int(process["ProcessId"]))
    while True:
        descendants = {int(p["ProcessId"]) for p in processes if p["ParentProcessId"] in identifiers}
        if descendants.issubset(identifiers):
            break
        identifiers.update(descendants)
    handles = []
    try:
        for identifier in identifiers:
            try:
                handles.append(_winapi.OpenProcess(0x100001, False, identifier))  # SYNCHRONIZE | PROCESS_TERMINATE
            except OSError as error:
                if error.winerror != 87:  # Process already exited.
                    raise
        for handle in handles:
            if _winapi.WaitForSingleObject(handle, 0) != _winapi.WAIT_OBJECT_0:
                try:
                    _winapi.TerminateProcess(handle, 1)
                except OSError:
                    if _winapi.WaitForSingleObject(handle, 0) != _winapi.WAIT_OBJECT_0:
                        raise
        for handle in handles:
            if _winapi.WaitForSingleObject(handle, 15000) != _winapi.WAIT_OBJECT_0:
                raise TimeoutError("An editor test process did not stop.")
    finally:
        for handle in handles:
            _winapi.CloseHandle(handle)


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
            launcher = shutil.which("onlyoffice-desktopeditors") or shutil.which("desktopeditors")
            if not launcher:
                raise RuntimeError("The official ONLYOFFICE launcher was not installed.")
            editor = Path(launcher)
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
                    stop_windows_editor(editor.parent)
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
