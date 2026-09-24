"""PDF and certificate fixtures for signing tests."""

import base64
import datetime
import io
import unittest

import signing
from asn1crypto import keys
from asn1crypto import x509 as asn1_x509
from card_selection import choose_certificate
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.pdf_utils import generic
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign import fields, signers
from pyhanko.sign.validation import validate_pdf_signature
from pyhanko_certvalidator import ValidationContext
from pyhanko_certvalidator.registry import SimpleCertificateStore
from reportlab.pdfgen import canvas
from visible_signature import certificate_details, signature_text
from form_fixture import form_pdf
from onlyoffice_form import prepare_signature


class SignatureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        document = io.BytesIO()
        page = canvas.Canvas(document, pagesize=(612, 792))
        page.setAuthor("Synthetic test")
        page.drawString(54, 720, "Software test only - no official business")
        page.save()
        writer = IncrementalPdfFileWriter(io.BytesIO(document.getvalue()))
        for name, box in [
            ("First", (54, 365, 424, 463)),
            ("Second", (54, 205, 424, 303)),
        ]:
            fields.append_signature_field(writer, fields.SigFieldSpec(name, box=box))
        buffer = io.BytesIO()
        writer.write(buffer)
        cls.pdf = buffer.getvalue()
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        now = datetime.datetime.now(datetime.timezone.utc)
        subject = x509.Name(
            [
                x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "DoD"),
                x509.NameAttribute(NameOID.COMMON_NAME, getattr(cls, "common_name", "EXAMPLE.ALEX.0000000000")),
            ]
        )
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=1))
            .not_valid_after(now + datetime.timedelta(days=1))
            .add_extension(
                x509.BasicConstraints(ca=False, path_length=None), critical=True
            )
            .add_extension(
                x509.KeyUsage(
                    True, True, False, False, False, False, False, False, False
                ),
                critical=True,
            )
            .sign(key, hashes.SHA256())
        )
        der = cert.public_bytes(serialization.Encoding.DER)
        cls.cert = asn1_x509.Certificate.load(der)
        cls.info = {
            "thumbprint": cert.fingerprint(hashes.SHA1()).hex(),
            "certificate": base64.b64encode(der).decode(),
        }
        cls.signer = signers.SimpleSigner(
            cls.cert,
            keys.PrivateKeyInfo.load(
                key.private_bytes(
                    serialization.Encoding.DER,
                    serialization.PrivateFormat.PKCS8,
                    serialization.NoEncryption(),
                )
            ),
            SimpleCertificateStore(),
        )

    def test_signature_preserves_bytes_and_fills_existing_field(self):
        signed = signing.sign_bytes(self.pdf, self.signer, {"field": "First"})
        reader = PdfFileReader(io.BytesIO(signed))
        (signature,) = reader.embedded_signatures
        status = validate_pdf_signature(
            signature,
            signer_validation_context=ValidationContext(
                trust_roots=[self.cert], allow_fetching=False
            ),
        )
        self.assertTrue(status.intact and status.valid)
        self.assertTrue(signed.startswith(self.pdf))
        self.assertEqual(signature.field_name, "First")
        self.assertEqual(len(list(fields.enumerate_sig_fields(reader))), 2)
        appearance = signature.sig_field["/AP"]["/N"].data
        self.assertIn(b"(ALEX)", appearance)
        self.assertIn(b"(EXAMPLE)", appearance)
        with self.assertRaises(ValueError):
            signing.sign_bytes(signed, self.signer, {"field": "First"})

    def test_rank_is_not_invented(self):
        details = certificate_details(self.cert)
        self.assertEqual(details["name"], "ALEX EXAMPLE")
        self.assertEqual(details["dodId"], "0000000000")
        self.assertNotIn("Rank:", signature_text(details)[0])

    def test_onlyoffice_form_box_becomes_valid_signature(self):
        pdf, unsigned_appearance = form_pdf("PDF LAYER ONLY - review before signing")
        writer, field = prepare_signature(pdf, "Signature1")
        prepared_stream = io.BytesIO()
        writer.write(prepared_stream)
        prepared = prepared_stream.getvalue()
        self.assertIn(b"PDF LAYER ONLY", PdfFileReader(io.BytesIO(prepared)).root[
            "/Pages"]["/Kids"][0].get_object()["/Contents"].data)
        signed = signing.sign_bytes(prepared, self.signer, {"field": field})
        self.assertTrue(signed.startswith(prepared))
        reader = PdfFileReader(io.BytesIO(signed))
        (signature,) = reader.embedded_signatures
        status = validate_pdf_signature(signature, signer_validation_context=ValidationContext(
            trust_roots=[self.cert], allow_fetching=False,
        ))
        self.assertTrue(status.intact and status.valid)
        self.assertEqual(signature.field_name, "Signature1_af_image")
        self.assertEqual([float(n) for n in signature.sig_field["/Rect"]], [70, 688, 224, 720])
        self.assertNotIn(b"/MetaOForm", signed)
        self.assertNotIn(b"/ONLYOFFICEFORM", signed)
        self.assertNotIn(b"word/document.xml", signed)
        self.assertNotIn("/A", signature.sig_field)
        signature_fields = list(fields.enumerate_sig_fields(reader))
        self.assertEqual(
            [field_name for field_name, _, _ in signature_fields],
            ["Signature1_af_image", "Signature2_af_image"],
        )
        self.assertIsNone(signature_fields[1][1])
        self.assertNotIn("/A", signature_fields[1][2].get_object())
        self.assertEqual(
            signature_fields[1][2].get_object()["/AP"]["/N"].data,
            unsigned_appearance,
        )
        self.assertNotEqual(signature.sig_field["/AP"]["/N"].data, unsigned_appearance)
        image_field = list(fields.enumerate_fields_in(
            reader.root["/AcroForm"]["/Fields"], with_name="Image1_af_image",
            refs_seen=set(), target_field_type="/Btn",
        ))
        self.assertEqual(len(image_field), 1)
        self.assertEqual(image_field[0][2].get_object()["/A"]["/S"], "/JavaScript")
        self.assertEqual(
            image_field[0][2].get_object()["/AP"]["/N"].data,
            unsigned_appearance,
        )
        twice_signed = signing.sign_bytes(signed, self.signer, {
            "field": "Signature2_af_image",
        })
        self.assertEqual(len(PdfFileReader(io.BytesIO(twice_signed)).embedded_signatures), 2)
        missing_appearance = IncrementalPdfFileWriter(io.BytesIO(pdf))
        second = next(ref.get_object() for field_name, _, ref in fields.enumerate_fields_in(
            missing_appearance.root["/AcroForm"]["/Fields"],
            with_name="Signature2_af_image", refs_seen=set(), target_field_type="/Btn",
        ) if field_name == "Signature2_af_image")
        second.pop("/AP")
        missing_appearance.update_container(second)
        broken_pdf = io.BytesIO()
        missing_appearance.write(broken_pdf)
        with self.assertRaisesRegex(ValueError, "no usable appearance"):
            signing.sign_bytes(broken_pdf.getvalue(), self.signer, {
                "kind": "onlyoffice-form", "field": "Signature1",
            })
        with self.assertRaisesRegex(ValueError, "not a saved ONLYOFFICE"):
            signing.sign_bytes(self.pdf, self.signer, {"kind": "onlyoffice-form", "field": "Signature1"})
        with self.assertRaisesRegex(ValueError, "not an ONLYOFFICE signature box"):
            signing.sign_bytes(pdf, self.signer, {"kind": "onlyoffice-form", "field": "Other"})
        with self.assertRaisesRegex(ValueError, "not an ONLYOFFICE signature box"):
            signing.sign_bytes(pdf, self.signer, {"kind": "onlyoffice-form", "field": "Image1"})

    def test_card_selection_is_mocked(self):
        self.assertIs(
            choose_certificate([self.info], reader_check=lambda _: True), self.info
        )
        with self.assertRaises(ValueError):
            choose_certificate([self.info], reader_check=lambda _: False)
        with self.assertRaises(ValueError):
            choose_certificate([self.info, self.info], reader_check=lambda _: True)
