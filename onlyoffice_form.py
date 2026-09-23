"""Convert an ONLYOFFICE signature image field into a PDF signature field."""

import io
import xml.etree.ElementTree as ET
import zipfile

from pyhanko.pdf_utils import generic
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.pdf_utils.writer import copy_into_new_writer
from pyhanko.sign import fields


_WORD = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_MAX_FORM_XML = 16 * 1024 * 1024


def _signature_form_keys(reader):
    refs = set()
    for revision in range(reader.xrefs.total_revisions):
        refs.update(reader.xrefs.explicit_refs_in_revision(revision))
    packages = []
    for ref in refs:
        obj = reader.get_object(ref)
        if (isinstance(obj, generic.StreamObject)
                and obj.get("/Type") == "/MetaOForm"
                and "/ONLYOFFICEFORM" in obj):
            packages.append(obj)
    if len(packages) != 1:
        raise ValueError("The ONLYOFFICE form metadata is missing or ambiguous.")
    try:
        with zipfile.ZipFile(io.BytesIO(packages[0].data)) as archive:
            info = archive.getinfo("word/document.xml")
            if info.file_size > _MAX_FORM_XML:
                raise ValueError("The ONLYOFFICE form metadata is too large.")
            with archive.open(info) as stream:
                xml = stream.read(_MAX_FORM_XML + 1)
                if len(xml) > _MAX_FORM_XML:
                    raise ValueError("The ONLYOFFICE form metadata is too large.")
                document = ET.fromstring(xml)
    except (KeyError, zipfile.BadZipFile, ET.ParseError) as exc:
        raise ValueError("The ONLYOFFICE form metadata is invalid.") from exc
    if document.tag != _WORD + "document":
        raise ValueError("The ONLYOFFICE form metadata is invalid.")
    keys = set()
    for properties in document.iter(_WORD + "sdtPr"):
        picture = properties.find(_WORD + "picture")
        if picture is None or picture.get(_WORD + "signature") != "1":
            continue
        form = properties.find(_WORD + "formPr")
        key = form.get(_WORD + "key") if form is not None else None
        if not key:
            raise ValueError("The ONLYOFFICE signature form metadata is ambiguous.")
        keys.add(key)
    return keys


def _is_empty_signature_button(value, widget):
    action = widget.get("/A")
    if isinstance(action, generic.IndirectObject):
        action = action.get_object()
    return (
        not value
        and widget.get("/Subtype") == "/Widget"
        and not widget.get("/Kids")
        and bool(int(widget.get("/Ff", 0)) & 65536)
        and isinstance(action, generic.DictionaryObject)
        and action.get("/S") == "/JavaScript"
        and str(action.get("/JS", "")).strip()
        == "event.target.buttonImportIcon();"
    )


def _convert_button(widget):
    widget[generic.pdf_name("/FT")] = generic.pdf_name("/Sig")
    for key in ("/A", "/AA", "/AP", "/AS", "/DA", "/Ff", "/H", "/I", "/MK", "/V"):
        widget.pop(key, None)


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
    signature_keys = _signature_form_keys(reader)
    if form_key not in signature_keys:
        raise ValueError("This is not an ONLYOFFICE signature box.")
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
    if not _is_empty_signature_button(value, ref.get_object()):
        raise ValueError("This is not an empty ONLYOFFICE signature box.")

    # ONLYOFFICE's embedded form package would otherwise hide the signed PDF
    # field when the saved copy is reopened. Copy the standard PDF objects.
    writer = copy_into_new_writer(reader)
    copied = list(fields.enumerate_fields_in(
        writer.root["/AcroForm"]["/Fields"],
        refs_seen=set(),
        target_field_type="/Btn",
    ))
    targets = [
        (field_name, field_ref.get_object())
        for field_name, field_value, field_ref in copied
        if field_name.endswith("_af_image")
        and field_name[:-9] in signature_keys
        and _is_empty_signature_button(field_value, field_ref.get_object())
    ]
    if sum(field_name == name for field_name, _ in targets) != 1:
        raise ValueError("The signature box did not survive PDF conversion.")
    for _, target in targets:
        _convert_button(target)
        writer.update_container(target)
    return writer, name
