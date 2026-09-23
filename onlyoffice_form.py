"""Convert an ONLYOFFICE signature image field into a PDF signature field."""

import io

from pyhanko.pdf_utils import generic
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.pdf_utils.writer import copy_into_new_writer
from pyhanko.sign import fields


def prepare_signature(pdf, form_key):
    if not isinstance(form_key, str) or not form_key or len(form_key) > 200:
        raise ValueError("Choose an empty ONLYOFFICE signature box.")
    if b"/MetaOForm" not in pdf or b"/ONLYOFFICEFORM" not in pdf:
        raise ValueError("This is not a saved ONLYOFFICE PDF form.")
    reader = PdfFileReader(io.BytesIO(pdf), strict=True)
    if reader.encrypted:
        raise ValueError("Password-protected PDFs are not supported.")
    if reader.embedded_signatures:
        raise ValueError("An already signed PDF form cannot be converted safely.")
    name = form_key + "_af_image"
    try:
        matches = list(fields.enumerate_fields_in(
            reader.root["/AcroForm"]["/Fields"],
            with_name=name,
            refs_seen=set(),
            target_field_type="/Btn",
        ))
    except KeyError as exc:
        raise ValueError("The ONLYOFFICE signature box was not found.") from exc
    if len(matches) != 1:
        raise ValueError("The ONLYOFFICE signature box is missing or ambiguous.")
    _, value, ref = matches[0]
    widget = ref.get_object()
    action = widget.get("/A")
    if isinstance(action, generic.IndirectObject):
        action = action.get_object()
    if (
        value
        or widget.get("/Subtype") != "/Widget"
        or widget.get("/Kids")
        or not (int(widget.get("/Ff", 0)) & 65536)
        or not isinstance(action, generic.DictionaryObject)
        or action.get("/S") != "/JavaScript"
        or str(action.get("/JS", "")).strip() != "event.target.buttonImportIcon();"
    ):
        raise ValueError("This is not an empty ONLYOFFICE signature box.")

    # ONLYOFFICE's embedded form package would otherwise hide the signed PDF
    # field when the saved copy is reopened. Copy the standard PDF objects.
    writer = copy_into_new_writer(reader)
    copied = list(fields.enumerate_fields_in(
        writer.root["/AcroForm"]["/Fields"],
        with_name=name,
        refs_seen=set(),
        target_field_type="/Btn",
    ))
    if len(copied) != 1:
        raise ValueError("The signature box did not survive PDF conversion.")
    target = copied[0][2].get_object()
    target[generic.pdf_name("/FT")] = generic.pdf_name("/Sig")
    for key in ("/A", "/AA", "/AP", "/AS", "/DA", "/Ff", "/H", "/I", "/MK", "/V"):
        target.pop(key, None)
    writer.update_container(target)
    return writer, name
