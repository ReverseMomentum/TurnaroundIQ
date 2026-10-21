"""Hero artwork from the supplied concept (art/hero-concept-source.jpg).

Crops the skeletal figure, halo and FTD lettering, lifts the orange ink off the
scanned-paper background into an alpha channel so it sits directly on the page
black, and erases the corner statements and stars baked into the concept, since
the site sets those as live text. Run from ftd/: python3 scripts/art_hero_concept.py
"""

import numpy as np
from PIL import Image

from art_lib import ORANGE, OUT, ROOT

SRC = ROOT / "art" / "hero-concept-source.jpg"

# halo tip to the "FORSAKEN TO DECAY" line, full width (source pixels)
CROP = (12, 0, 1278, 1272)
# baked-in statements and stars (source pixels), set as HTML instead
ERASE = [(48, 135, 258, 430), (998, 135, 1243, 430)]
# floor/ceiling of the ink signal in the red channel
PAPER, INK = 34, 175  # paper grain peaks around 27, so 34 keeps the background fully clear
FEATHER = 40  # px fade at the crop edges so the image boundary never shows


def main():
    src = Image.open(SRC).convert("RGB").crop(CROP)
    rgb = np.asarray(src, dtype=np.float32)
    ink = np.clip((rgb[..., 0] - PAPER) / (INK - PAPER), 0, 1)
    for x0, y0, x1, y1 in ERASE:
        ink[y0:y1, x0:x1] = 0
    h, w = ink.shape
    ramp = lambda n: np.clip(np.minimum(np.arange(n), np.arange(n)[::-1]) / FEATHER, 0, 1)
    ink *= ramp(w)[None, :] * np.minimum(ramp(h), np.where(np.arange(h) < h / 2, 1, ramp(h)))[:, None]
    # un-premultiply the scan's own colour, then pull it halfway to the brand orange
    colour = np.clip(rgb / np.maximum(ink[..., None], 1e-3), 0, 255)
    colour = colour * 0.5 + ORANGE * 0.5
    out = np.dstack([colour, ink * 255]).astype(np.uint8)
    OUT.mkdir(parents=True, exist_ok=True)
    Image.fromarray(out, "RGBA").save(OUT / "hero.webp", "WEBP", quality=88, method=6)
    print("  wrote public/art/hero.webp", src.size)


if __name__ == "__main__":
    main()
