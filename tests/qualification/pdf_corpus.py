"""Small synthetic corpus with independent verification and rendered controls."""
import io
import json
import random
import subprocess
import tempfile
from pathlib import Path
from PIL import Image, ImageChops, ImageDraw
from common import ROOT, REPORT, hosted, record
from test_signature_core import SignatureTests
from pyhanko.pdf_utils import generic
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign import fields
from reportlab.pdfgen import canvas
from signature_layout import signature_layout, text_width, ASCENT, DESCENT
from signing import sign_bytes
from visible_signature import certificate_details

hosted()


def document(width, height, rotation):
    stream = io.BytesIO()
    page = canvas.Canvas(stream, pagesize=(612, 792))
    page.setAuthor("Synthetic feasibility fixture")
    page.drawString(54, 730, "Synthetic document: no official business")
    page.save()
    writer = IncrementalPdfFileWriter(io.BytesIO(stream.getvalue()))
    fields.append_signature_field(writer, fields.SigFieldSpec("First", box=(54, 365, 54+width, 365+height)))
    fields.append_signature_field(writer, fields.SigFieldSpec("Second", box=(54, 160, 424, 250)))
    ref, _ = writer.find_page_for_modification(0)
    ref.get_object()[generic.pdf_name("/Rotate")] = generic.NumberObject(rotation)
    writer.mark_update(ref)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def verify(path, count=1):
    result = subprocess.run(["pdfsig", "-nocert", str(path)], capture_output=True, text=True, timeout=30)
    return result.returncode == 0 and result.stdout.count("Signature is Valid") == count


def render(path):
    output = path.with_suffix("")
    subprocess.run(["pdftoppm", "-f", "1", "-singlefile", "-r", "72", "-png", str(path), str(output)],
                   check=True, capture_output=True, timeout=30)
    with Image.open(output.with_suffix(".png")) as image:
        return image.convert("RGB")


def bounds(width, height, rotation):
    x0, y0, x1, y1 = 54, 792-365-height, 54+width, 792-365
    return {0:(x0,y0,x1,y1),90:(792-y1,x0,792-y0,x1),
            180:(612-x1,792-y1,612-x0,792-y0),270:(y0,612-x1,y1,612-x0)}[rotation]


def appearance_check(before, after, box):
    changed = ImageChops.difference(before, after).convert("L").point(lambda p: 255 if p > 20 else 0)
    assert changed.getbbox(), "No visible appearance"
    x0,y0,x1,y1 = box
    assert changed.crop(box).getbbox(), "Signature block is blank"
    ImageDraw.Draw(changed).rectangle((x0-2,y0-2,x1+2,y1+2), fill=0)
    assert changed.getbbox() is None, "Appearance changed pixels outside the selected block"


failures, successes, negative = [], [], []
with tempfile.TemporaryDirectory(prefix="cac-pdf-feasibility-") as temp:
    work = Path(temp)
    for index, name in enumerate(("Alex Example", "José Muñoz", "Αλέξης Example", "陳 小明")):
        fixture = type("CorpusSigner", (SignatureTests,), {"common_name":name})
        fixture.setUpClass()
        for shape, (width,height) in enumerate(((370,98),(460,24),(90,180),(120,120))):
            rotation = (index+shape)%4*90
            label = f"{index}-{shape}-{rotation}"
            try:
                original = document(width,height,rotation)
                signed = sign_bytes(original, fixture.signer, {"field":"First"})
                assert signed.startswith(original)
                unsigned_path, signed_path = work/(label+"-before.pdf"), work/(label+"-signed.pdf")
                unsigned_path.write_bytes(original)
                signed_path.write_bytes(signed)
                assert verify(signed_path), "Independent signature verification failed"
                text = subprocess.check_output(["pdftotext", "-layout", str(signed_path), "-"], timeout=30).decode()
                expected = certificate_details(fixture.cert)["name"]
                assert "".join(expected.split()) in "".join(text.split()), "Certificate name not recoverable"
                before, after = render(unsigned_path), render(signed_path)
                box = bounds(width,height,rotation)
                appearance_check(before,after,box)
                if label == "0-0-0":
                    after.save(REPORT/"appearance-reference.png")
                    broken = after.copy()
                    ImageDraw.Draw(broken).rectangle((5,5,20,20), fill="black")
                    try:
                        appearance_check(before,broken,box)
                    except AssertionError:
                        negative.append("out-of-bounds rendering detected")
                    else:
                        raise AssertionError("Rendering oracle missed injected damage")
                    try:
                        appearance_check(before,before,box)
                    except AssertionError:
                        negative.append("missing appearance detected")
                    else:
                        raise AssertionError("Rendering oracle missed missing signature")
                    tampered = bytearray(signed)
                    tampered[7] = ord("4") if tampered[7] != ord("4") else ord("5")
                    bad = work/"tampered.pdf"
                    bad.write_bytes(tampered)
                    assert not verify(bad), "Verifier accepted altered signed bytes"
                    negative.append("signed-byte tampering detected")
                    twice = sign_bytes(signed,fixture.signer,{"field":"Second"})
                    second = work/"two-signatures.pdf"
                    second.write_bytes(twice)
                    assert verify(second,2), "Existing signature not preserved"
                    negative.append("two independently valid signatures")
                successes.append(label)
            except Exception as error:
                failures.append({"case":label,"error":str(error)})
    fixture = SignatureTests
    fixture.setUpClass()
    for label, data, field in (("malformed",b"%PDF-broken","First"),
                               ("missing-field",fixture.pdf,"Absent")):
        try:
            sign_bytes(data,fixture.signer,{"field":field})
        except Exception:
            negative.append(label+" rejected")
        else:
            failures.append({"case":label,"error":"Unexpected acceptance"})

rng = random.Random(20260923)
for i in range(1000):
    width, height = rng.uniform(20,500), rng.uniform(12,250)
    blocks = signature_layout(width,height,"Alexandra Example","Digitally signed by Alexandra Example\nDate: 2026-09-23 10:00:00 -0500")
    for block in blocks:
        for j,line in enumerate(block.lines):
            baseline=block.first_baseline-j*block.leading
            assert block.x+text_width(line,block.font_size) <= width+1e-6
            assert baseline-DESCENT*block.font_size >= -1e-6
            assert baseline+ASCENT*block.font_size <= height+1e-6
record("pdf",status="failed" if failures else "passed",corpusPasses=successes,failures=failures,
       generatedLayoutCases=1000,negativeControls=negative,
       scope="Production source signing; Poppler signature and raster checks. Synthetic certificates only.",
       limits=["No physical card","No recipient trust/revocation claim","Reference image needs human aesthetic approval"])
if failures:
    raise SystemExit(1)
