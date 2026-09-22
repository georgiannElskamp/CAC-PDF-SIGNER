"""Locate the blank fixture page for an actual pointer click."""

from collections import Counter
import json
import sys

from PIL import Image

image = Image.open(sys.argv[1]).convert("RGB")
rows = []
for y in range(160, image.height - 30):
    runs, start = [], None
    for x in range(image.width):
        white = min(image.getpixel((x, y))) >= 250
        if white and start is None:
            start = x
        if start is not None and (not white or x == image.width - 1):
            end = x if not white else x + 1
            if 380 <= end - start <= 430:
                runs.append((start, end))
            start = None
    for pair in runs:
        rows.append((pair, y))
counts = Counter(pair for pair, _ in rows)
if not counts:
    raise RuntimeError("Cannot locate the 50-percent blank fixture page; UI harness needs review")
(left, right), count = counts.most_common(1)[0]
if count < 350:
    raise RuntimeError("Fixture page is obscured or clipped")
top = min(y for pair, y in rows if pair == (left, right))
width = right - left
print(json.dumps({"x": left + width * 239 / 612, "y": top + width * 378 / 612}))
