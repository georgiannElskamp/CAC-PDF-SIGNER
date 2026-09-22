"""Measured, proportional text layout for a PDF signature's visible rectangle."""

import math
import re
from dataclasses import dataclass

from helvetica_metrics import WIDTHS

# Conservative Helvetica extents include accents as well as lowercase descenders.
ASCENT = 0.96
DESCENT = 0.23
LEADING = 1.22


def encode_text(value):
    """Encode text using the PDF font's WinAnsi character set."""
    try:
        return value.encode("cp1252")
    except UnicodeEncodeError as error:
        raise ValueError(
            "The signature font cannot display a character in this certificate."
        ) from error


def text_width(value, size=1):
    return sum(WIDTHS[code] for code in encode_text(value)) * size / 1000


def wrap_lines(paragraphs, width, size, break_hyphens=False, measure=text_width):
    """Wrap at word boundaries, with optional breaks at existing name hyphens."""
    lines = []
    for paragraph in paragraphs:
        line = ""
        # Keep a time and its UTC offset together. A surname may wrap after an
        # existing hyphen without adding one or altering the certificate text.
        words = re.findall(r"\d{2}:\d{2}:\d{2} [+-]\d{4}|\S+", paragraph)
        tokens = []
        for word in words:
            pieces = re.findall(r"[^-]+-?|[-]", word) if break_hyphens else [word]
            tokens.extend(
                (piece, " " if index == 0 else "") for index, piece in enumerate(pieces)
            )
        for word, separator in tokens:
            if measure(word, size) > width:
                return None
            candidate = (line + separator + word).lstrip()
            if line and measure(candidate, size) > width:
                lines.append(line)
                line = word
            else:
                line = candidate
        if line:
            lines.append(line)
    return tuple(lines)


@dataclass(frozen=True)
class TextBlock:
    lines: tuple[str, ...]
    font_size: float
    x: float
    first_baseline: float
    line_height: float = LEADING

    @property
    def leading(self):
        return self.font_size * self.line_height


def fit_text(paragraphs, x, y, width, height, break_hyphens=False, measure=text_width,
             metrics=(ASCENT, DESCENT, LEADING)):
    """Find the largest font that fits both measured width and wrapped height."""
    paragraphs = tuple(" ".join(value.split()) for value in paragraphs if value.strip())
    if not paragraphs:
        raise ValueError("The visible signature has no text.")
    ascent, descent, leading = metrics
    low, high = 0.0, height / (ascent + descent)
    for _ in range(32):
        size = (low + high) / 2
        lines = wrap_lines(paragraphs, width, size, break_hyphens, measure)
        occupied = (
            ((len(lines) - 1) * leading + ascent + descent) * size
            if lines
            else math.inf
        )
        if occupied <= height:
            low = size
        else:
            high = size
    # Leave a small numerical allowance for PDF decimal serialization.
    size = low * 0.999
    lines = wrap_lines(paragraphs, width, size, break_hyphens, measure)
    occupied = ((len(lines) - 1) * leading + ascent + descent) * size
    baseline = y + (height + occupied) / 2 - ascent * size
    return TextBlock(lines, size, x, baseline, leading)


def signature_layout(width, height, name, details, **font_options):
    if not all(math.isfinite(v) and v > 0 for v in (width, height)):
        raise ValueError("Invalid signature field dimensions.")
    padding = min(width, height) * 0.035
    gap = min(width, height) * 0.07
    inner_width, inner_height = width - 2 * padding, height - 2 * padding
    if width / height >= 1.45:
        name_width = (inner_width - gap) * 0.43
        name_box = (padding, padding, name_width, inner_height)
        detail_box = (
            padding + name_width + gap,
            padding,
            inner_width - gap - name_width,
            inner_height,
        )
    else:
        name_height = (inner_height - gap) * 0.34
        detail_height = inner_height - gap - name_height
        name_box = (padding, padding + detail_height + gap, inner_width, name_height)
        detail_box = (padding, padding, inner_width, detail_height)
    paragraphs = details.splitlines()
    if width / height >= 8:
        # Shallow fields need flowing details instead of many tiny fixed rows.
        date_index = next(
            (i for i, value in enumerate(paragraphs) if value.startswith("Date:")),
            len(paragraphs),
        )
        paragraphs = [
            "  ".join(paragraphs[:date_index]),
            "  ".join(paragraphs[date_index:]),
        ]
    return fit_text((name,), *name_box, break_hyphens=True, **font_options), fit_text(
        paragraphs, *detail_box, **font_options
    )
