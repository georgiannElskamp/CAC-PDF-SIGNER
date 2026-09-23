"""Sign with the unchanged packaged Linux worker through a virtual CAC."""
import base64
import json
import os
from pathlib import Path
import signal
import subprocess
import time
from common import REPORT, hosted, record, extract, sha

hosted()
root=extract(Path("/input/CAC-PDF-Signer.plugin"),Path("/test/state/Example Plugin é"))
root.joinpath("native/linux-x86_64/cac-signer").chmod(0o755)
original_path=Path("/test/state/document.pdf")


def fixture():
    objects=[
        "<< /Type /Catalog /Pages 2 0 R /AcroForm << /Fields [5 0 R] /SigFlags 3 >> >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << >> /Contents 4 0 R /Annots [5 0 R] >>",
        "<< /Length 0 >>\nstream\n\nendstream",
        "<< /Type /Annot /Subtype /Widget /FT /Sig /T (InstallationTest) /Rect [54 365 424 463] /F 4 /P 3 0 R >>",
    ]
    pdf=b"%PDF-1.7\n"
    offsets=[0]
    for i,obj in enumerate(objects,1):
        offsets.append(len(pdf));pdf+=f"{i} 0 obj\n{obj}\nendobj\n".encode()
    xref=len(pdf)
    pdf+=f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode()
    pdf+=b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:])
    pdf+=f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    original_path.write_bytes(pdf)
    return pdf


def xdo(*args):
    return subprocess.check_output(["xdotool",*map(str,args)],text=True,stderr=subprocess.DEVNULL,timeout=15)


def wait_dialog(child,title):
    end=time.monotonic()+45
    while time.monotonic()<end:
        if child.poll() is not None:
            output,error=child.communicate()
            raise RuntimeError("Worker stopped before "+title+": "+output[-2500:]+error[-500:])
        try:
            ids=xdo("search","--onlyvisible","--name","^"+title+"$").strip().splitlines()
            if ids:return ids[0]
        except subprocess.CalledProcessError:pass
        time.sleep(.2)
    raise TimeoutError("No "+title+" dialog")


def focus(window):
    xdo("windowfocus","--sync",window)


def sign(number, expect_card=True):
    request={"op":"sign","pdf":base64.b64encode(original).decode(),"field":"InstallationTest",
             "sourcePath":str(original_path),"name":"document.pdf"}
    child=subprocess.Popen(["/bin/sh",str(root/"launch-linux.sh")],stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=os.environ)
    try:
        child.stdin.write(json.dumps(request)+"\n");child.stdin.flush()
        if not expect_card:
            output,error=child.communicate(timeout=40)
            events=[json.loads(line) for line in output.splitlines() if line.startswith("{")]
            assert child.returncode!=0 and "No eligible signing certificate" in events[-1].get("error",""), output[-2000:]+error[-500:]
            return {"noCardRejected":True}
        pin=wait_dialog(child,"CAC PIN")
        maps=Path(f"/proc/{child.pid}/maps").read_text()
        assert str(root/"native/linux-x86_64/_internal/opensc-pkcs11.so") in maps, "Bundled OpenSC was not loaded"
        assert "libsofthsm" not in maps, "Worker bypassed OpenSC with a direct software provider"
        focus(pin);xdo("type","--clearmodifiers","12345678");xdo("key","Return")
        save=wait_dialog(child,"Save signed PDF as")
        target=Path("/test/state")/f"signed virtual CAC {number}.pdf"
        focus(save);xdo("key","ctrl+l");time.sleep(.2);xdo("key","ctrl+a")
        xdo("type","--clearmodifiers",str(target));xdo("key","Return")
        output,error=child.communicate(timeout=45)
        events=[json.loads(line) for line in output.splitlines() if line.startswith("{")]
        assert child.returncode==0 and events[-1].get("saved"), output[-2000:]+error[-500:]
        verification=subprocess.check_output(["pdfsig","-nocert",str(target)],text=True,timeout=30)
        assert "Signature is Valid" in verification and "Total document signed" in verification
        assert target.read_bytes().startswith(original)
        subprocess.run(["pdftoppm","-f","1","-singlefile","-r","96","-png",str(target),str(REPORT/"virtual-preview")],
                       check=True,capture_output=True,timeout=30)
        return {"saved":True,"sha256":sha(target),"bundledOpenSC":True,"independentlyVerified":True}
    finally:
        if child.poll() is None:child.kill();child.communicate(timeout=10)


original=fixture()
results=[]
try:
    results.append(sign(1))
    os.kill(int(os.environ["PROBE_CARD_PID"]),signal.SIGUSR1)
    time.sleep(1)
    results.append(sign(2,False))
    os.kill(int(os.environ["PROBE_CARD_PID"]),signal.SIGUSR2)
    time.sleep(1)
    results.append(sign(3))
    record("virtual-card",status="passed",results=results,ordinaryUser=os.getuid()!=0,
           transport="Bundled OpenSC / system PCSC daemon / vpcd / libcacard",
           scope="Unchanged packaged worker, native PIN and Save As; no ONLYOFFICE field-click in this probe.",
           limits=["Physical USB/CCID bypassed","Bundled private daemon not positively exercised","Synthetic certificates only"])
except Exception as error:
    record("virtual-card",status="failed",results=results,error=str(error),
           scope="Virtual CAC feasibility; system PCSC daemon")
    raise
