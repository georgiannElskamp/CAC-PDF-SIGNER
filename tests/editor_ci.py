"""Install a pinned editor and test the release in a disposable GitHub runner."""

import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from automation import download, validate_manifest


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


def check(package, manifest=None, plugin_version=None, form_handoff=False):
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted":
        raise RuntimeError("This installer is restricted to disposable GitHub-hosted runners.")
    if sys.platform not in ("win32", "linux") or platform.machine().lower() not in ("amd64", "x86_64"):
        raise RuntimeError("The editor installation test requires Windows or Linux x64.")
    root = Path(__file__).resolve().parents[1]
    config = validate_manifest(json.loads((manifest or root / "tests/editor-installers.json").read_text()))
    pin = config["windows" if sys.platform == "win32" else "linux"]
    version = plugin_version or json.loads((root / "plugin/config.json").read_text())["version"]
    with tempfile.TemporaryDirectory(prefix="cac-editor-") as temporary:
        work = Path(temporary)
        installer = work / pin["file"]
        url = f"https://github.com/ONLYOFFICE/DesktopEditors/releases/download/v{config['version']}/{pin['file']}"
        download(url, installer, pin["sha256"])
        print(f"Editor v{config['version']}; installer SHA-256 {pin['sha256']}; plugin {version}", flush=True)
        environment = dict(os.environ)
        state = work / "state"
        environment["CAC_SIGNATURE_HOME"] = str(state)
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
        def run_session(document, port, script, arguments, label):
            log_path = work / f"editor-{label}.log"
            with log_path.open("wb") as log:
                options = {"start_new_session": True} if sys.platform == "linux" else {"creationflags": subprocess.CREATE_NO_WINDOW}
                child = subprocess.Popen([str(editor), f"--remote-debugging-port={port}", str(document)],
                                         cwd=editor.parent, env=environment, stdout=log, stderr=log, **options)
                try:
                    result = subprocess.run(["node", str(root / script), "--disposable-profile", str(port), *arguments],
                                            check=True, timeout=360, capture_output=True, text=True)
                    print(result.stdout, end="", flush=True)
                    return result.stdout
                except Exception as error:
                    log.flush()
                    if isinstance(error, subprocess.CalledProcessError):
                        print(error.stdout or "", error.stderr or "", file=sys.stderr)
                    print(log_path.read_bytes()[-8000:].decode("utf-8", "replace"), file=sys.stderr)
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

        run_session(pdf, 9251, "tests/editor_smoke.js", [str(package.resolve()), version, pdf.name], "standard")
        if form_handoff or tuple(map(int, version.split("."))) >= (0, 9, 0):
            from check_form_handoff import verify as verify_form_handoff

            form = work / "Example User é" / "form source.pdf"
            form.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root / "tests/fixtures/onlyoffice-form.pdf", form)
            report = run_session(form, 9252, "tests/form_editor_smoke.js",
                                 [str(package.resolve()), str(form), str(pdf), str(state), version], "form")
            result = next(json.loads(line) for line in report.splitlines() if line.startswith('{'))
            verify_form_handoff(result["recoveryPath"], result["prepared"], result["comparisonPath"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--plugin-version")
    parser.add_argument("--form-handoff", action="store_true")
    args = parser.parse_args()
    check(args.package, args.manifest, args.plugin_version, args.form_handoff)
