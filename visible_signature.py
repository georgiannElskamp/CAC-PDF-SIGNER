"""Certificate text and PDF signature appearances."""

import re
from dataclasses import dataclass

from pyhanko import stamp
from pyhanko.pdf_utils import generic
from pyhanko.pdf_utils.content import ResourceType
from pyhanko.pdf_utils.layout import BoxConstraints
from pyhanko.sign import fields
from signature_layout import encode_text, signature_layout


class PageTextStamp(stamp.TextStamp):
    def _render_inner_content(self):
        params = self.get_default_text_params()
        params.update(self.text_params or {})
        details = self.style.stamp_text % params
        unicode_text = None
        try:
            encode_text(params["name"] + details)
        except ValueError:
            from unicode_font import UnicodeText

            unicode_text = UnicodeText(self.writer, params["name"] + details)
        font_options = dict(measure=unicode_text.measure, metrics=unicode_text.metrics) if unicode_text else {}
        name, details = signature_layout(
            self.box.width,
            self.box.height,
            params["name"],
            details,
            **font_options,
        )
        if unicode_text:
            for index, engine in enumerate(unicode_text.engines):
                self.set_resource(ResourceType.FONT, generic.pdf_name(f"/SignatureFont{index}"), engine.as_resource())
            commands = [b"q 0 g"]
            for block in (name, details):
                for index, line in enumerate(block.lines):
                    commands.append(unicode_text.draw(line, block.font_size, block.x,
                                                     block.first_baseline - index * block.leading))
            commands.append(b"Q")
            return commands
        self.set_resource(
            ResourceType.FONT,
            generic.pdf_name("/SignatureFont"),
            generic.DictionaryObject(
                {
                    generic.pdf_name("/Type"): generic.pdf_name("/Font"),
                    generic.pdf_name("/Subtype"): generic.pdf_name("/Type1"),
                    generic.pdf_name("/BaseFont"): generic.pdf_name("/Helvetica"),
                    generic.pdf_name("/Encoding"): generic.pdf_name("/WinAnsiEncoding"),
                }
            ),
        )
        commands = [b"q 0 g"]
        for block in (name, details):
            commands.append(b"BT /SignatureFont %.6f Tf" % block.font_size)
            for index, line in enumerate(block.lines):
                # Literal PDF strings must escape certificate-supplied delimiters.
                value = (
                    encode_text(line)
                    .replace(b"\\", b"\\\\")
                    .replace(b"(", b"\\(")
                    .replace(b")", b"\\)")
                )
                commands.append(
                    b"1 0 0 1 %.6f %.6f Tm (%s) Tj"
                    % (block.x, block.first_baseline - index * block.leading, value)
                )
            commands.append(b"ET")
        commands.append(b"Q")
        return commands

    def as_form_xobject(self):
        obj = super().as_form_xobject()
        angle = self.style.page_rotation
        w, h = self.box.width, self.box.height
        matrix = {
            90: (0, 1, -1, 0, h, 0),
            180: (-1, 0, 0, -1, w, h),
            270: (0, -1, 1, 0, 0, w),
        }.get(angle)
        if matrix:
            obj[generic.pdf_name("/Matrix")] = generic.ArrayObject(
                [generic.FloatObject(n) for n in matrix]
            )
        return obj


@dataclass(frozen=True)
class PageTextStyle(stamp.TextStampStyle):
    page_rotation: int = 0

    def create_stamp(self, writer, box, text_params):
        if self.page_rotation in (90, 270):
            box = BoxConstraints(width=box.height, height=box.width)
        return PageTextStamp(
            writer=writer, style=self, box=box, text_params=text_params
        )


def certificate_details(cert):
    subject = cert.subject.native
    cn = str(subject.get("common_name", "")).strip()
    units = subject.get("organizational_unit_name", [])
    if isinstance(units, str):
        units = [units]
    is_dod = any(str(unit).upper() == "DOD" for unit in units)
    match = re.fullmatch(r"(.+)\.(\d{10})", cn) if is_dod else None
    dod_id = match[2] if match else ""
    name = cn
    if match:
        parts = match[1].split(".")
        # DoD common name order: surname.given.middle[.generation].EDIPI.
        if len(parts) >= 2:
            suffix = (
                parts[-1]
                if len(parts) > 2
                and parts[-1].upper() in ("JR", "SR", "II", "III", "IV", "V")
                else ""
            )
            middle = parts[2:-1] if suffix else parts[2:]
            name = " ".join([parts[1], *middle, parts[0], suffix]).strip()
    if subject.get("surname") and subject.get("given_name"):
        name = str(subject["given_name"]) + " " + str(subject["surname"])
    # Read rank from the certificate title.
    rank = str(subject.get("title", "")).strip()
    return {
        "name": name or "Certificate holder",
        "rank": rank,
        "dodId": dod_id,
        "rankSource": "certificate title" if rank else "not in certificate",
    }


def signature_text(details):
    rank = details["rank"]
    if len(rank) > 50 or any(ord(ch) < 32 for ch in rank):
        raise ValueError("Rank must be a single line of at most 50 characters.")
    # Keep certificate text in substitution values.
    template = "Digitally signed by %(name)s"
    params = {"name": details["name"]}
    if rank:
        template += "\nRank: %(rank)s"
        params["rank"] = rank
    template += "\nDate: %(ts)s"
    if details["dodId"]:
        template += "\nDoD ID: %(dod_id)s"
        params["dod_id"] = details["dodId"]
    return template, params


def signature_fields(reader):
    count = int(reader.root["/Pages"]["/Count"])
    if not 0 < count <= 2000:
        raise ValueError("PDF must contain between 1 and 2000 pages.")
    page_refs = {}
    annotation_pages = {}
    for i in range(count):
        ref, _resources = reader.find_page_for_modification(i)
        page_refs[(ref.idnum, ref.generation)] = i
        for annot in ref.get_object().get("/Annots", []):
            if hasattr(annot, "idnum"):
                annotation_pages[(annot.idnum, annot.generation)] = i
    result = []
    for name, value, ref in fields.enumerate_sig_fields(reader):
        obj = ref.get_object()
        kids = obj.get("/Kids", [])
        widget_ref = kids[0] if len(kids) == 1 else ref
        widget = widget_ref.get_object()
        page_ref = widget.raw_get("/P") if "/P" in widget else None
        page = (
            page_refs.get((page_ref.idnum, page_ref.generation))
            if hasattr(page_ref, "idnum")
            else None
        )
        if page is None and hasattr(widget_ref, "idnum"):
            page = annotation_pages.get((widget_ref.idnum, widget_ref.generation))
        rect = [float(x) for x in widget.get("/Rect", [0, 0, 0, 0])]
        visible = (
            len(rect) == 4 and abs(rect[2] - rect[0]) > 1 and abs(rect[3] - rect[1]) > 1
        )
        # Hidden annotations are not useful signature blocks.
        visible = visible and not (int(widget.get("/F", 0)) & 3)
        result.append(
            {
                "name": name,
                "filled": bool(value),
                "page": page,
                "rect": rect,
                "usable": visible and page is not None and len(kids) <= 1,
            }
        )
    return count, result


def signing_appearance(reader, cert, options):
    if not isinstance(options, dict) or not isinstance(options.get("field"), str):
        raise ValueError("Click an empty PDF signature field.")
    field_name = options["field"]
    _count, available = signature_fields(reader)
    selected = next((field for field in available if field["name"] == field_name), None)
    if not selected or selected["filled"]:
        raise ValueError(
            "Choose an existing empty signature field; signed fields cannot be overwritten."
        )
    if not selected["usable"]:
        raise ValueError("This signature field is invisible or unsupported.")
    page = selected["page"]
    template, params = signature_text(certificate_details(cert))
    page_ref, _ = reader.find_page_for_modification(page)
    page_dict = page_ref.get_object()
    rotation = 0
    for _ in range(32):
        if "/Rotate" in page_dict:
            rotation = int(page_dict["/Rotate"]) % 360
            break
        if "/Parent" not in page_dict:
            break
        page_dict = page_dict["/Parent"]
    if rotation not in (0, 90, 180, 270):
        raise ValueError("Unsupported page rotation.")
    style = PageTextStyle(
        page_rotation=rotation,
        stamp_text=template,
        timestamp_format="%Y-%m-%d %H:%M:%S %z",
        border_width=0,
        background=None,
    )
    return field_name, None, True, style, params
