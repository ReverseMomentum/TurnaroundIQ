"""Artwork lifted from the supplied concept (art/hero-concept-source.jpg).

Each piece is cropped from the concept, its orange ink is lifted off the
scanned-paper background into an alpha channel so it sits directly on the page
black, and anything baked in that the site sets as live text is erased.
Run from ftd/: python3 scripts/art_concept.py
"""

import numpy as np
from PIL import Image

from art_lib import OUT, ROOT, RUST

SRC = ROOT / "art" / "hero-concept-source.jpg"

# floor/ceiling of the ink signal in the red channel
PAPER, INK = 34, 175  # paper grain peaks around 27, so 34 keeps the background fully clear
SCAN_ORANGE_R = 200  # red channel of the concept's printed orange at full ink
FEATHER = 40  # px fade at the crop edges so the image boundary never shows

# name -> crop (source pixels), regions to erase (crop-relative), edges to feather
PIECES = {
    # halo tip to the "FORSAKEN TO DECAY" line; the corner statements and stars are live text.
    # The top edge isn't feathered: the halo's tip runs close to it.
    "hero": dict(crop=(12, 0, 1278, 1272), erase=[(48, 135, 258, 430), (998, 135, 1243, 430)],
                 feather="lrb"),
    # the ruined cathedral and its two flanking crosses, under the waitlist box
    "cathedral": dict(crop=(12, 1700, 1278, 2168), erase=[], feather="lrtb"),
}


def ramp(n):
    return np.clip(np.minimum(np.arange(n), np.arange(n)[::-1]) / FEATHER, 0, 1)


def lift(name, crop, erase, feather):
    src = Image.open(SRC).convert("RGB").crop(crop)
    rgb = np.asarray(src, dtype=np.float32)
    ink = np.clip((rgb[..., 0] - PAPER) / (INK - PAPER), 0, 1)
    for x0, y0, x1, y1 in erase:
        ink[y0:y1, x0:x1] = 0
    h, w = ink.shape
    if "l" in feather or "r" in feather:
        ink *= ramp(w)[None, :]
    rows = ramp(h)
    if "t" not in feather:
        rows = np.where(np.arange(h) < h / 2, 1, rows)
    ink *= rows[:, None]
    # The scan is printed in orange. Keep its light/dark variation (un-premultiplied
    # brightness relative to that orange) and re-ink it in the brand rust.
    lit = np.clip(rgb[..., 0] / np.maximum(ink, 1e-3), 0, 255)
    shade = np.clip(lit / SCAN_ORANGE_R, 0.7, 1.2)[..., None]
    colour = np.clip(RUST * shade, 0, 255)
    out = np.dstack([colour, ink * 255]).astype(np.uint8)
    OUT.mkdir(parents=True, exist_ok=True)
    Image.fromarray(out, "RGBA").save(OUT / f"{name}.webp", "WEBP", quality=88, method=6)
    print(f"  wrote public/art/{name}.webp", src.size)


def main():
    for name, cfg in PIECES.items():
        lift(name, **cfg)


if __name__ == "__main__":
    main()
