"""Incremental PDF signing through the Windows CNG bridge."""

import asyncio
import base64
import hashlib
import io
import json
import ssl
import struct
import subprocess

from asn1crypto import x509
from cryptography import x509 as crypto_x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign import signers
from pyhanko.sign.validation import validate_pdf_signature
from pyhanko_certvalidator import ValidationContext
from pyhanko_certvalidator.registry import SimpleCertificateStore
from runtime_config import MAX_PDF
from visible_signature import signing_appearance


def bridge_call(bridge, request, timeout=180):
    payload = json.dumps(request).encode()
    proc = subprocess.run(
        [str(bridge)],
        input=struct.pack("<I", len(payload)) + payload,
        capture_output=True,
        timeout=timeout,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if proc.returncode or len(proc.stdout) < 4:
        raise RuntimeError("Windows signing bridge did not respond.")
    length = struct.unpack("<I", proc.stdout[:4])[0]
    if length > 1024 * 1024 or len(proc.stdout) != length + 4:
        raise RuntimeError("Invalid signing bridge response.")
    result = json.loads(proc.stdout[4:])
    if result.get("error"):
        raise RuntimeError(result["error"])
    return result


def certificates(bridge):
    from windows_csp import certificates as legacy_certificates

    modern = (
        bridge_call(bridge, {"cmd": "listCertificates"}, timeout=25).get("certificates")
        or []
    )
    known = {item["thumbprint"].lower() for item in modern}
    return modern + [item for item in legacy_certificates() if item["thumbprint"].lower() not in known]


class CardSigner(signers.Signer):
    def __init__(self, info, bridge):
        self.bridge = bridge
        cert_der = base64.b64decode(info["certificate"])
        cert = x509.Certificate.load(cert_der)
        registry = SimpleCertificateStore()
        # Build the certificate chain from the Windows CA stores.
        candidates = []
        for store in ("CA", "ROOT"):
            for data, encoding, _trust in ssl.enum_certificates(store):
                if encoding == "x509_asn":
                    try:
                        candidates.append(x509.Certificate.load(data))
                    except ValueError:
                        pass
        current = cert
        for _ in range(8):
            issuer = next((c for c in candidates if c.subject == current.issuer), None)
            if issuer is None or issuer.subject == current.subject:
                break
            registry.register(issuer)
            current = issuer
        super().__init__(signing_cert=cert, cert_registry=registry, embed_roots=False)
        self.thumbprint = info["thumbprint"]
        self.provider = info.get("provider", "cng")
        self.public_key = crypto_x509.load_der_x509_certificate(cert_der).public_key()

    async def async_sign_raw(self, data, digest_algorithm, dry_run=False):
        if digest_algorithm != "sha256":
            raise ValueError("This bridge supports SHA-256 only.")
        if dry_run:
            return bytes(512)
        digest = hashlib.sha256(data).digest()
        if self.provider == "csp":
            from windows_csp import sign_digest

            signature = await asyncio.to_thread(sign_digest, self.thumbprint, digest)
        else:
            result = await asyncio.to_thread(
                bridge_call,
                self.bridge,
                {"cmd": "signDigest", "thumbprint": self.thumbprint,
                 "digest": base64.b64encode(digest).decode()},
            )
            signature = base64.b64decode(result["signature"], validate=True)
        if isinstance(self.public_key, rsa.RSAPublicKey):
            self.public_key.verify(signature, data, padding.PKCS1v15(), hashes.SHA256())
        elif isinstance(self.public_key, ec.EllipticCurvePublicKey):
            self.public_key.verify(signature, data, ec.ECDSA(hashes.SHA256()))
        else:
            raise ValueError("Unsupported certificate key type.")
        return signature


def sign_bytes(pdf, signer, appearance=None):
    if len(pdf) > MAX_PDF or not pdf.startswith(b"%PDF-"):
        raise ValueError("Choose a PDF smaller than 40 MB.")
    original = io.BytesIO(pdf)
    writer = IncrementalPdfFileWriter(original, strict=True)
    if writer.prev.encrypted:
        raise ValueError(
            "Password-protected PDFs are not supported."
        )
    field_name, field_spec, existing_only, style, params = signing_appearance(
        writer.prev, signer.signing_cert, appearance
    )
    # The visible appearance is included in the cryptographic signature.
    result = signers.PdfSigner(
        signers.PdfSignatureMetadata(field_name=field_name, md_algorithm="sha256"),
        signer=signer,
        new_field_spec=field_spec,
        stamp_style=style,
    ).sign_pdf(
        writer,
        existing_fields_only=existing_only,
        appearance_text_params=params,
        bytes_reserved=65536,
    )
    signed = result.getvalue()
    if not signed.startswith(pdf):
        raise RuntimeError("Original PDF bytes were not preserved.")
    embedded = next(
        s
        for s in PdfFileReader(io.BytesIO(signed)).embedded_signatures
        if s.field_name == field_name
    )
    # This check establishes integrity, not official DoD trust or revocation status.
    status = validate_pdf_signature(
        embedded,
        signer_validation_context=ValidationContext(
            trust_roots=[signer.signing_cert], allow_fetching=False
        ),
    )
    if not status.intact or not status.valid:
        raise RuntimeError("The resulting PDF signature failed its integrity check.")
    return signed
