"""Embedded font fallback for certificate text outside WinAnsi."""

from functools import lru_cache
from pathlib import Path
import sys

from pyhanko.pdf_utils.font.opentype import GlyphAccumulatorFactory


class UnicodeText:
    def __init__(self, writer, text):
        root = Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "fonts"
        self.engines = []
        self.cmaps = []
        remaining = set(text) - {"\n", "\r"}
        for name in ("NotoSans-Regular.ttf", "NotoSansCJKsc-Regular.otf"):
            engine = GlyphAccumulatorFactory(str(root / name)).create_font_engine(writer)
            self.engines.append(engine)
            cmap = engine.tt.getBestCmap()
            self.cmaps.append(cmap)
            remaining = {ch for ch in remaining if ord(ch) not in cmap}
            if not remaining:
                break
        if remaining:
            codes = ", ".join(f"U+{ord(ch):04X}" for ch in sorted(remaining)[:8])
            raise ValueError("The bundled signature fonts do not support: " + codes)
        ascent = max(e.tt['hhea'].ascent / e.units_per_em for e in self.engines)
        descent = max(-e.tt['hhea'].descent / e.units_per_em for e in self.engines)
        self.metrics = (ascent, descent, max(1.22, ascent + descent + .03))
        self.measure = lru_cache(maxsize=1024)(self._measure)

    def runs(self, text):
        index, value = None, ""
        for ch in text:
            selected = next(i for i, cmap in enumerate(self.cmaps) if ord(ch) in cmap)
            if index is not None and selected != index:
                yield index, value
                value = ""
            index = selected
            value += ch
        if value:
            yield index, value

    def _measure(self, text, size=1):
        total = 0
        for index, run in self.runs(text):
            engine = self.engines[index]
            engine.font_size = 1
            total += abs(engine.shape(run).x_advance)
        return total * size

    def draw(self, text, size, x, y):
        commands = []
        for index, run in self.runs(text):
            engine = self.engines[index]
            engine.font_size = size
            shaped = engine.shape(run)
            commands.append(b"BT /SignatureFont%d %.6f Tf 1 0 0 1 %.6f %.6f Tm " % (index, size, x, y))
            commands.extend((shaped.graphics_ops, b" ET"))
            x += abs(shaped.x_advance) * size
        return b" ".join(commands)
