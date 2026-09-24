"""Synthetic ONLYOFFICE PDF form used by signing and handoff tests."""

import io
import zipfile

from pyhanko.pdf_utils import generic
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from reportlab.pdfgen import canvas


def form_pdf(page_text="Synthetic ONLYOFFICE form test"):
    source = io.BytesIO()
    page = canvas.Canvas(source, pagesize=(612, 792))
    page.drawString(54, 720, page_text)
    page.save()
    writer = IncrementalPdfFileWriter(io.BytesIO(source.getvalue()))
    page_ref, _ = writer.find_page_for_modification(0)
    action = writer.add_object(generic.DictionaryObject({
        generic.pdf_name("/S"): generic.pdf_name("/JavaScript"),
        generic.pdf_name("/JS"): generic.TextStringObject("event.target.buttonImportIcon();"),
    }))
    unsigned_appearance = b"q 0.9 0.9 0.9 rg 0 0 154 32 re f Q"
    appearance = writer.add_object(generic.StreamObject(
        dict_data={
            generic.pdf_name("/Type"): generic.pdf_name("/XObject"),
            generic.pdf_name("/Subtype"): generic.pdf_name("/Form"),
            generic.pdf_name("/BBox"): generic.ArrayObject([
                generic.NumberObject(n) for n in (0, 0, 154, 32)
            ]),
            generic.pdf_name("/Resources"): generic.DictionaryObject(),
        },
        stream_data=unsigned_appearance,
    ))
    box = generic.DictionaryObject({
        generic.pdf_name("/Type"): generic.pdf_name("/Annot"),
        generic.pdf_name("/Subtype"): generic.pdf_name("/Widget"),
        generic.pdf_name("/FT"): generic.pdf_name("/Btn"),
        generic.pdf_name("/Ff"): generic.NumberObject(65536),
        generic.pdf_name("/F"): generic.NumberObject(4),
        generic.pdf_name("/T"): generic.TextStringObject("Signature1_af_image"),
        generic.pdf_name("/P"): page_ref,
        generic.pdf_name("/Rect"): generic.ArrayObject([
            generic.NumberObject(n) for n in (70, 688, 224, 720)
        ]),
        generic.pdf_name("/A"): action,
        generic.pdf_name("/AP"): generic.DictionaryObject({
            generic.pdf_name("/N"): appearance,
        }),
    })
    box_ref = writer.add_object(box)
    second_box = generic.DictionaryObject(box)
    second_box[generic.pdf_name("/T")] = generic.TextStringObject("Signature2_af_image")
    second_box[generic.pdf_name("/Rect")] = generic.ArrayObject([
        generic.NumberObject(n) for n in (250, 688, 404, 720)
    ])
    second_ref = writer.add_object(second_box)
    image_box = generic.DictionaryObject(box)
    image_box[generic.pdf_name("/T")] = generic.TextStringObject("Image1_af_image")
    image_box[generic.pdf_name("/Rect")] = generic.ArrayObject([
        generic.NumberObject(n) for n in (70, 610, 224, 670)
    ])
    image_ref = writer.add_object(image_box)
    page_obj = page_ref.get_object()
    page_obj[generic.pdf_name("/Annots")] = generic.ArrayObject([
        box_ref, second_ref, image_ref
    ])
    writer.update_container(page_obj)
    writer.root[generic.pdf_name("/AcroForm")] = generic.DictionaryObject({
        generic.pdf_name("/Fields"): generic.ArrayObject([
            box_ref, second_ref, image_ref
        ]),
    })
    writer.update_root()
    package = io.BytesIO()
    with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", """
            <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
                <w:sdtPr><w:picture w:signature="1"/><w:formPr w:key="Signature1"/></w:sdtPr>
                <w:sdtPr><w:picture w:signature="1"/><w:formPr w:key="Signature1"/></w:sdtPr>
                <w:sdtPr><w:picture w:signature="1"/><w:formPr w:key="Signature2"/></w:sdtPr>
                <w:sdtPr><w:picture/><w:formPr w:key="Image1"/></w:sdtPr>
            </w:document>
        """)
    writer.add_object(generic.StreamObject(
        dict_data={
            generic.pdf_name("/Type"): generic.pdf_name("/MetaOForm"),
            generic.pdf_name("/ONLYOFFICEFORM"): generic.ArrayObject([
                generic.NumberObject(0), generic.NumberObject(0)
            ]),
        },
        stream_data=package.getvalue(),
    ))
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue(), unsigned_appearance
