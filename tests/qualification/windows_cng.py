"""Exercise the shipped CNG bridge with an ephemeral Windows software key."""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from asn1crypto import cms
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from common import hosted, record, extract, REPORT
from signing import bridge_call, CardSigner, sign_bytes
from card_selection import choose_certificate
from test_signature_core import SignatureTests
from pyhanko.pdf_utils.reader import PdfFileReader

hosted()
package=Path(os.environ["PROBE_INPUT"])/"CAC-PDF-Signer.plugin"
ps=["pwsh","-NoProfile","-NonInteractive","-Command"]
thumbprint=None
try:
    certificate=json.loads(subprocess.check_output(ps+[
        "$ErrorActionPreference='Stop'; Import-Module Microsoft.PowerShell.Security; $c=New-SelfSignedCertificate -Type Custom -Subject 'CN=SOFTWARE.TEST.0000000000,OU=DoD,O=Synthetic feasibility test' "
        "-CertStoreLocation Cert:\\CurrentUser\\My -Provider 'Microsoft Software Key Storage Provider' "
        "-KeyAlgorithm RSA -KeyLength 2048 -HashAlgorithm SHA256 -KeyExportPolicy NonExportable "
        "-KeyUsage DigitalSignature,NonRepudiation -NotAfter (Get-Date).AddDays(1); "
        "@{thumbprint=$c.Thumbprint;certificate=[Convert]::ToBase64String($c.RawData)}|ConvertTo-Json -Compress"
    ],text=True,timeout=60))
    thumbprint=certificate["thumbprint"]
    with tempfile.TemporaryDirectory(prefix="cac-cng-probe-") as temp:
        work=Path(temp)
        extracted=extract(package,work/"Example User \u00e9")
        candidates=list((extracted/"native").rglob("pdfsign-bridge.exe"))
        assert len(candidates)==1, "Packaged bridge missing or ambiguous"
        bridge=candidates[0]
        listed=bridge_call(bridge,{"cmd":"listCertificates"})["certificates"]
        info=next(x for x in listed if x["thumbprint"].lower()==thumbprint.lower())
        content=b"Synthetic CNG bridge feasibility"
        reply=bridge_call(bridge,{"cmd":"signDigest","thumbprint":thumbprint,
                                 "digest":base64.b64encode(hashlib.sha256(content).digest()).decode()})
        public=x509.load_der_x509_certificate(base64.b64decode(info["certificate"])).public_key()
        public.verify(base64.b64decode(reply["signature"]),content,padding.PKCS1v15(),hashes.SHA256())
        try:
            choose_certificate([info])
        except ValueError:
            software_rejected=True
        else:
            raise AssertionError("Production card selection accepted a software certificate")
        fixture=SignatureTests
        fixture.setUpClass()
        signed=sign_bytes(fixture.pdf,CardSigner(info,bridge),{"field":"First"})
        reader=PdfFileReader(io.BytesIO(signed))
        signature=reader.embedded_signatures[0]
        ranges=list(signature.sig_object["/ByteRange"])
        content_bytes=b"".join(signed[ranges[i]:ranges[i]+ranges[i+1]] for i in (0,2))
        signed_data=cms.ContentInfo.load(bytes(signature.sig_object["/Contents"])).dump()
        (work/"signature.der").write_bytes(signed_data)
        (work/"content.bin").write_bytes(content_bytes)
        openssl=shutil.which("openssl")
        if not openssl:
            raise RuntimeError("Independent OpenSSL verifier unavailable")
        command=[openssl,"cms","-verify","-binary","-inform","DER","-in",str(work/"signature.der"),
                 "-content",str(work/"content.bin"),"-noverify","-out",str(work/"verified.bin")]
        verified=subprocess.run(command,capture_output=True,text=True,timeout=30)
        assert verified.returncode==0, verified.stderr
        (work/"content.bin").write_bytes(content_bytes+b"changed")
        assert subprocess.run(command,capture_output=True,timeout=30).returncode!=0
        assert signed.startswith(fixture.pdf)
        record("windows-cng",status="passed",packagedBridge=True,independentVerifier="OpenSSL CMS",
               softwareCertificateRejectedByCardSelection=software_rejected,tamperRejected=True,
               scope="Real CNG software provider and shipped bridge; production PDF source. Physical reader and PIN dialog untested.")
except Exception as error:
    record("windows-cng",status="failed",error=str(error))
    raise
finally:
    if thumbprint:
        subprocess.run(ps+["Import-Module Microsoft.PowerShell.Security; Remove-Item -LiteralPath ('Cert:\\CurrentUser\\My\\' + '"+thumbprint+"') -DeleteKey -ErrorAction Stop"],
                       check=True,timeout=30)
