"""Install and restart the real editor with a disposable profile."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
from common import ROOT, REPORT, hosted, record
sys.path.insert(0,str(ROOT/"tools"))
from automation import download, validate_manifest
from editor_ci import stop_windows_editor


def install():
    manifest=validate_manifest(json.loads((Path(os.environ["PROBE_INPUT"])/"editor.json").read_text()))
    pin=manifest["windows" if sys.platform=="win32" else "linux"]
    destination=Path(os.environ["RUNNER_TEMP"])/pin["file"]
    download(f"https://github.com/ONLYOFFICE/DesktopEditors/releases/download/v{manifest['version']}/{pin['file']}",destination,pin["sha256"])
    if sys.platform=="win32":
        subprocess.run([str(destination),"/VERYSILENT","/SP-","/SUPPRESSMSGBOXES","/NORESTART","/TASKS="],check=True,timeout=300)
    else:
        subprocess.run(["sudo","env","DEBIAN_FRONTEND=noninteractive","apt-get","install","-y",str(destination)],check=True,timeout=300)
    destination.unlink()


def check():
    if sys.platform=="win32":
        assert not ctypes.windll.shell32.IsUserAnAdmin(), "The GUI probe must run as a standard Windows user"
        editor=Path(os.environ["ProgramFiles"])/"ONLYOFFICE/DesktopEditors/DesktopEditors.exe"
    else:
        assert os.getuid()!=0
        editor=Path(shutil.which("onlyoffice-desktopeditors") or shutil.which("desktopeditors"))
    environment=dict(os.environ)
    with tempfile.TemporaryDirectory(prefix="cac-desktop-feasibility-") as temporary:
        work=Path(temporary)
        if sys.platform=="linux":
            profile=work/"Example User é"
            profile.mkdir()
            runtime=profile/"runtime"
            runtime.mkdir(mode=0o700)
            environment.update(HOME=str(profile),XDG_DATA_HOME=str(profile/".local/share"),
                XDG_CONFIG_HOME=str(profile/".config"),XDG_CACHE_HOME=str(profile/".cache"),
                XDG_RUNTIME_DIR=str(runtime),QT_QPA_PLATFORM="xcb",GDK_BACKEND="x11")
        record("desktop-account",status="passed",platform=sys.platform,ordinaryUser=True,
               profileHasSpace=" " in environment.get("USERPROFILE",environment.get("HOME","")),
               unicodeProfile=any(ord(x)>127 for x in environment.get("USERPROFILE",environment.get("HOME",""))))
        node=os.environ.get("PROBE_NODE","node")
        pdf=work/"fixture.pdf"
        subprocess.run([node,str(ROOT/"tests/editor_smoke.js"),"--fixture",str(pdf)],check=True,timeout=30)
        outcomes=[]
        for mode in ("install","restart"):
            with (work/(mode+".log")).open("wb") as log:
                options={"start_new_session":True} if sys.platform=="linux" else {"creationflags":subprocess.CREATE_NO_WINDOW}
                child=subprocess.Popen([str(editor),"--remote-debugging-port=9251",str(pdf)],cwd=editor.parent,
                                       env=environment,stdout=log,stderr=log,**options)
                try:
                    result=subprocess.run([node,str(ROOT/"tests/qualification/desktop.js"),mode,"9251",
                        str(Path(os.environ["PROBE_INPUT"])/"CAC-PDF-Signer.plugin"),str(REPORT)],timeout=300)
                    outcomes.append({"mode":mode,"exitCode":result.returncode})
                finally:
                    if sys.platform=="win32":
                        stop_windows_editor(editor.parent)
                    else:
                        try:os.killpg(child.pid,signal.SIGTERM)
                        except ProcessLookupError:pass
                    try:child.wait(timeout=15)
                    except subprocess.TimeoutExpired:child.kill();child.wait(timeout=10)
            if outcomes[-1]["exitCode"]:
                print((work/(mode+".log")).read_bytes()[-3000:].decode("utf-8","replace"))
                break
        record("desktop-summary",status="passed" if len(outcomes)==2 and all(x["exitCode"]==0 for x in outcomes) else "failed",
               phases=outcomes,closure="Forced process teardown; graceful-close coverage remains.",
               installationScope="Native install API and pointer interaction with Background plugins. Full Plugin Manager file selection remains separate.")
        if len(outcomes)!=2 or any(x["exitCode"] for x in outcomes):raise SystemExit(1)


if __name__=="__main__":
    hosted()
    parser=argparse.ArgumentParser()
    parser.add_argument("--install-only",action="store_true")
    parser.add_argument("--installed",action="store_true")
    args=parser.parse_args()
    if not args.installed:install()
    if not args.install_only:check()
