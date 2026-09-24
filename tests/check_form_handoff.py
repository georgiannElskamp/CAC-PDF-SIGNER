"""Verify the hosted form handoff against the editor's loaded PDF bytes."""

import io
from pathlib import Path

from pyhanko.pdf_utils import generic
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign import fields


def page_data(reader):
    pages = reader.root["/Pages"]
    assert pages["/Count"] == 1
    page = pages["/Kids"][0].get_object()
    content = page["/Contents"]
    streams = content if isinstance(content, generic.ArrayObject) else [content]
    return page["/MediaBox"], [stream.get_object().data for stream in streams]


def field(reader, name, kind):
    matches = list(fields.enumerate_fields_in(
        reader.root["/AcroForm"]["/Fields"],
        with_name=name, target_field_type=kind, refs_seen=set(),
    ))
    assert len(matches) == 1, (name, kind, matches)
    return matches[0][2].get_object()


def verify(recovery, prepared, comparison):
    recovery = PdfFileReader(io.BytesIO(Path(recovery).read_bytes()), strict=True)
    prepared = PdfFileReader(io.BytesIO(Path(prepared).read_bytes()), strict=True)
    comparison = PdfFileReader(io.BytesIO(Path(comparison).read_bytes()), strict=True)
    source_field = field(recovery, "Signature1_af_image", "/Btn")
    review_field = field(prepared, "Signature1_af_image", "/Sig")
    assert source_field["/Rect"] == review_field["/Rect"]
    assert page_data(recovery) == page_data(prepared)
    assert page_data(recovery) != page_data(comparison)
    assert not prepared.embedded_signatures
    print("PASS: review field and page content match the editor-loaded form.")


if __name__ == "__main__":
    import sys
    verify(*sys.argv[1:])
