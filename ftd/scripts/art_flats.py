"""Product images from the supplied garment flats (art/flats/<product>-<colour>.png).

Each flat sheet holds a front and a back view on white. This cuts them out,
grades white to the brand bone colour, and stages each view on the charcoal
studio backdrop, plus close-up crops. Run from ftd/: python3 scripts/art_flats.py
"""

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from art_lib import BONE, OUT, ROOT, _blur_noise

FLATS = ROOT / "art" / "flats"
BG = np.array([21, 17, 14], dtype=np.float32)  # #15110E
W, H = 1000, 1100

# garment boxes on each sheet template (left, top, right, bottom), source pixels
HOODIE = {"front": (40, 116, 880, 1016), "back": (938, 116, 1778, 1016)}
PANTS = {"front": (145, 80, 556, 732), "back": (702, 80, 1113, 732)}

# Where sleeve print runs to the garment edge, a flood fill from the white border
# leaks into it, so those sheets get a morphological close. That also seals the
# narrow underarm gaps on the hoodie template, which are reopened here.
HOODIE_UNDERARM_GAPS = [(270, 730, 304, 806), (619, 730, 653, 806), (1167, 730, 1202, 806), (1516, 730, 1550, 806)]

# the pants crotch: the close seals it over, so it is seeded as background, and
# the narrow opening between the hems is reopened like the hoodie underarms
PANTS_CROTCH_SEEDS = [(348, 600), (906, 600)]
PANTS_CROTCH_GAPS = [(322, 640, 382, 736), (880, 640, 918, 736), (338, 350, 362, 380)]

# close-ups: (view, left, top, width) as fractions of that view's box; height follows the 10:11 frame
CHEST = ("front", 0.226, 0.204, 0.56)
PRODUCTS = {
    "crossbone-zip-hoodie": dict(
        boxes=HOODIE, close=True, gaps=HOODIE_UNDERARM_GAPS,
        details={"back-detail": ("back", 0.181, 0.116, 0.62), "chest-detail": CHEST,
                 "sleeve-detail": ("front", 0.667, 0.493, 0.357)},
    ),
    "never-enough-zip-hoodie": dict(
        boxes=HOODIE, close=False, gaps=[],
        details={"back-detail": ("back", 0.16, 0.08, 0.72), "chest-detail": CHEST},
    ),
    "cross-zip-hoodie": dict(
        boxes=HOODIE, close=False, gaps=[],
        details={"back-detail": ("back", 0.22, 0.2, 0.56), "chest-detail": CHEST},
    ),
    "crossbone-baggy-pants": dict(
        boxes=PANTS, close=True, gaps=PANTS_CROTCH_GAPS, seeds=PANTS_CROTCH_SEEDS,
        details={"front-detail": ("front", 0.012, 0.19, 0.62)},
    ),
}
COLOURS = ("black", "grey")


def cutout(img, close, gaps, seeds=()):
    """Alpha mask for the garment silhouettes on a sheet."""
    lum = img.convert("L")
    dark = lum.point(lambda v: 255 if v < 200 else 0)
    marker = dark
    if close:
        for _ in range(3):
            marker = marker.filter(ImageFilter.MaxFilter(9))  # ~12px
    else:
        marker = lum.point(lambda v: 0 if v > 200 else 255)
    marker = marker.copy()
    w, h = marker.size
    for seed in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1), *seeds):
        ImageDraw.floodfill(marker, seed, 128)
    solid = Image.fromarray(((np.asarray(marker) != 128) * 255).astype(np.uint8))
    if close:
        for _ in range(3):
            solid = solid.filter(ImageFilter.MinFilter(9))
    solid = np.array(solid)
    fabric = np.asarray(dark)
    for x0, y0, x1, y1 in gaps:
        solid[y0:y1, x0:x1] = fabric[y0:y1, x0:x1]
    # keep the true outline wherever the fabric itself defines it
    alpha = Image.fromarray(np.maximum(solid, fabric))
    return alpha.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.7))


def grade(rgb):
    """Pure white print -> bone, black -> warm washed black; greys follow in between."""
    a = np.asarray(rgb, dtype=np.float32) / 255
    lo = np.array([12, 10, 9], np.float32)
    return lo + (BONE - lo) * a


def backdrop(rng):
    yy, xx = np.mgrid[0:H, 0:W]
    pool = np.exp(-(((xx - W / 2) / (W * 0.55)) ** 2 + ((yy - H * 0.45) / (H * 0.6)) ** 2))
    return BG * (0.72 + 0.5 * pool[..., None]), _blur_noise((H, W), 0.7, rng)[..., None] * 3.0


def stage(img, alpha, seed):
    """Composite a cut-out view onto the studio backdrop, scaled to fit."""
    scale = min((W * 0.9) / img.width, (H * 0.86) / img.height)
    size = (round(img.width * scale), round(img.height * scale))
    img = img.resize(size, Image.LANCZOS).filter(ImageFilter.UnsharpMask(1.2, 60, 2))
    alpha = alpha.resize(size, Image.LANCZOS)
    x, y = (W - size[0]) // 2, (H - size[1]) // 2 + 10

    a = np.zeros((H, W), np.float32)
    a[y:y + size[1], x:x + size[0]] = np.asarray(alpha, np.float32) / 255
    g = np.zeros((H, W, 3), np.float32)
    g[y:y + size[1], x:x + size[0]] = grade(img)

    bg, knit = backdrop(np.random.default_rng(seed))
    shadow = np.asarray(Image.fromarray((a * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(26)), np.float32) / 255
    bg = bg * (1 - 0.55 * np.roll(shadow, 14, axis=0)[..., None])
    out = bg * (1 - a[..., None]) + g * a[..., None] + knit
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB")


def detail(src, alpha, box, seed):
    x, y, w = box
    h = round(w * 1.1)
    c = src.crop((x, y, x + w, y + h))
    a = alpha.crop((x, y, x + w, y + h))
    up = c.resize((W, H), Image.LANCZOS).filter(ImageFilter.UnsharpMask(1.6, 70, 2))
    am = np.asarray(a.resize((W, H), Image.LANCZOS), np.float32)[..., None] / 255
    bg, knit = backdrop(np.random.default_rng(seed))
    out = grade(up) * am + bg * (1 - am) + knit
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB")


def save(img, name):
    img.save(OUT / f"{name}.webp", "WEBP", quality=86, method=6)
    img.resize((400, 440), Image.LANCZOS).save(OUT / f"{name}-thumb.webp", "WEBP", quality=82, method=6)


def sheet(product, colour):
    """Load a flat sheet with its garment alpha."""
    cfg = PRODUCTS[product]
    src = Image.open(FLATS / f"{product}-{colour}.png").convert("RGB")
    return src, cutout(src, cfg["close"], cfg["gaps"], cfg.get("seeds", ()))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    seed = 30
    for product, cfg in PRODUCTS.items():
        for colour in COLOURS:
            src, alpha = sheet(product, colour)
            base = f"{product}-{colour}"
            for view, box in cfg["boxes"].items():
                seed += 1
                save(stage(src.crop(box), alpha.crop(box), seed), f"{base}-{view}")
            for name, (view, rx, ry, rw) in cfg["details"].items():
                l, t, r, b = cfg["boxes"][view]
                bw, bh = r - l, b - t
                seed += 1
                save(detail(src, alpha, (round(l + rx * bw), round(t + ry * bh), round(rw * bw)), seed), f"{base}-{name}")
            print("  wrote", base)


if __name__ == "__main__":
    main()
