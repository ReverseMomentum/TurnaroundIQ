"""Tileable textures used by the CSS: film grain and an ink-dropout mask for vector type."""

import math
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from art_lib import OUT, _blur_noise


def tile_blur(a, r):
    """Blur with wrap-around so the tile stays seamless."""
    h, w = a.shape
    big = np.tile(a, (3, 3))
    im = Image.fromarray(np.clip(big * 255, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(r))
    return np.asarray(im, dtype=np.float32)[h:2 * h, w:2 * w] / 255


def grain():
    rng = np.random.default_rng(3)
    n = rng.random((256, 256)).astype(np.float32)
    n = tile_blur(n, 0.5)
    n = (n - n.mean()) / n.std()
    a = np.clip(0.5 + n * 0.5, 0, 1)
    rgba = np.dstack([np.full_like(a, 230), np.full_like(a, 220), np.full_like(a, 201), a * 255]).astype(np.uint8)
    Image.fromarray(rgba, "RGBA").save(OUT / "grain.png", optimize=True)


def ink_mask():
    """White = keep ink. Specks, starved patches and scratches, seamless at 600px."""
    S = 600
    rng = np.random.default_rng(9)
    mid = tile_blur(rng.random((S, S)).astype(np.float32), 2.0)
    big = tile_blur(rng.random((S, S)).astype(np.float32), 22)
    mid = (mid - mid.mean()) / mid.std()
    big = (big - big.mean()) / big.std()
    holes = (mid * 0.6 + big * 0.5) < -1.55
    pin = rng.random((S, S)) < 0.01
    keep = ~(holes | pin)
    img = Image.fromarray((keep * 255).astype(np.uint8))
    d = ImageDraw.Draw(img)
    r = random.Random(4)
    for _ in range(26):
        x, y = r.uniform(0, S), r.uniform(0, S)
        a = r.uniform(-0.4, 0.4) + (math.pi / 2 if r.random() < 0.4 else 0)
        ln = r.uniform(40, 220)
        for ox in (-S, 0, S):
            for oy in (-S, 0, S):
                d.line([(x + ox, y + oy), (x + ox + math.cos(a) * ln, y + oy + math.sin(a) * ln)], fill=0, width=1)
    a = np.asarray(img, dtype=np.uint8)
    rgba = np.dstack([np.full_like(a, 255)] * 3 + [a])
    Image.fromarray(rgba, "RGBA").save(OUT / "ink-mask.png", optimize=True)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    grain()
    ink_mask()
    print("textures written")
