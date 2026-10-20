"""Product images from the supplied hoodie flats (art/hoodie-flats-source.png).

Cuts each flat off its white background, grades white to the brand bone colour,
and sets it on the same charcoal studio backdrop as the other garment images.
Run from ftd/: python3 scripts/art_flats.py
"""

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from art_lib import BONE, OUT, ROOT, _blur_noise

SRC = ROOT / "art" / "hoodie-flats-source.png"
BG = np.array([21, 17, 14], dtype=np.float32)  # #15110E
W, H = 1000, 1100

# garment boxes in the source image (left, top, right, bottom)
FRONT = (40, 117, 880, 1016)
BACK = (938, 117, 1778, 1016)

# close-ups, in source pixels: (left, top, width); height follows the 10:11 frame
# underarm gaps between sleeve and hem: narrow enough that the closing in cutout()
# seals them, so they are opened again explicitly (source pixels)
UNDERARM_GAPS = [(270, 730, 304, 806), (619, 730, 653, 806), (1167, 730, 1202, 806), (1516, 730, 1550, 806)]

CROPS = {
    "hoodie-detail-chest": ("front", (230, 300, 470)),
    "hoodie-detail-back": ("back", (1090, 220, 520)),
    "hoodie-detail-sleeve": ("front", (600, 560, 300)),
}


def cutout(img):
    """Alpha mask for the garment silhouette.

    Print touches the garment edge in places, so a plain flood fill from the white
    border leaks into it. Instead: grow the fabric (dark) mask until those gaps
    close, flood the background from the border, then shrink back by the same amount.
    """
    dark = img.convert("L").point(lambda v: 255 if v < 200 else 0)
    grown = dark
    for _ in range(3):
        grown = grown.filter(ImageFilter.MaxFilter(9))  # ~12px
    marker = grown.copy()
    w, h = marker.size
    for seed in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
        ImageDraw.floodfill(marker, seed, 128)
    solid = Image.fromarray(((np.asarray(marker) != 128) * 255).astype(np.uint8))
    for _ in range(3):
        solid = solid.filter(ImageFilter.MinFilter(9))
    solid = np.array(solid)
    fabric = np.asarray(dark)
    for x0, y0, x1, y1 in UNDERARM_GAPS:
        solid[y0:y1, x0:x1] = fabric[y0:y1, x0:x1]
    # keep the true outline wherever the fabric itself defines it
    alpha = Image.fromarray(np.maximum(solid, fabric))
    return alpha.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.7))


def grade(rgb):
    """Pure white print -> bone, flat black -> warm washed black."""
    a = np.asarray(rgb, dtype=np.float32) / 255
    lo = np.array([12, 10, 9], np.float32)
    return lo + (BONE - lo) * a


def stage(img, alpha, seed):
    """Composite a cut-out garment onto the studio backdrop, scaled to fit."""
    scale = min((W * 0.9) / img.width, (H * 0.86) / img.height)
    size = (round(img.width * scale), round(img.height * scale))
    img = img.resize(size, Image.LANCZOS).filter(ImageFilter.UnsharpMask(1.2, 60, 2))
    alpha = alpha.resize(size, Image.LANCZOS)
    x, y = (W - size[0]) // 2, (H - size[1]) // 2 + 10

    a = np.zeros((H, W), np.float32)
    a[y:y + size[1], x:x + size[0]] = np.asarray(alpha, np.float32) / 255
    g = np.zeros((H, W, 3), np.float32)
    g[y:y + size[1], x:x + size[0]] = grade(img)

    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:H, 0:W]
    pool = np.exp(-(((xx - W / 2) / (W * 0.55)) ** 2 + ((yy - H * 0.45) / (H * 0.6)) ** 2))
    bg = BG * (0.72 + 0.5 * pool[..., None])
    shadow = np.asarray(Image.fromarray((a * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(26)), np.float32) / 255
    bg = bg * (1 - 0.55 * np.roll(shadow, 14, axis=0)[..., None])
    knit = _blur_noise((H, W), 0.7, rng)[..., None] * 3.0
    out = bg * (1 - a[..., None]) + g * a[..., None] + knit
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB")


def detail(src, alpha, box, seed):
    x, y, w = box
    h = round(w * 1.1)
    c = src.crop((x, y, x + w, y + h))
    a = alpha.crop((x, y, x + w, y + h))
    up = c.resize((W, H), Image.LANCZOS).filter(ImageFilter.UnsharpMask(1.6, 70, 2))
    am = np.asarray(a.resize((W, H), Image.LANCZOS), np.float32)[..., None] / 255
    rng = np.random.default_rng(seed)
    knit = _blur_noise((H, W), 0.8, rng)[..., None] * 3.5
    out = grade(up) * am + BG * (1 - am) + knit
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB")


def save(img, name):
    img.save(OUT / f"{name}.webp", "WEBP", quality=86, method=6)
    img.resize((400, 440), Image.LANCZOS).save(OUT / f"{name}-thumb.webp", "WEBP", quality=82, method=6)
    print("  wrote", name)


def main():
    src = Image.open(SRC).convert("RGB")
    alpha = cutout(src)
    for name, box, seed in (("hoodie-front", FRONT, 31), ("hoodie-back", BACK, 32)):
        save(stage(src.crop(box), alpha.crop(box), seed), name)
    for i, (name, (_, box)) in enumerate(CROPS.items()):
        save(detail(src, alpha, box, 40 + i), name)


if __name__ == "__main__":
    main()
