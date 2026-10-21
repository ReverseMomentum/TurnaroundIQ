"""Campaign panels: each Drop 01 back print lifted off its flat and re-printed in
orange ink under a spiked halo, in the same screen-print finish as the hero.
Run from ftd/: python3 scripts/art_campaign.py
"""

import numpy as np
from PIL import Image, ImageFilter

import art_flats
from art_lib import rays, render, save_ink, screenprint, svg_doc

W, H = 900, 1200

# panel name -> (product, halo centre y as a fraction of H, print width as a fraction of W,
#                part of the back view to lift as fractions (left, top, right, bottom))
WHOLE = (0, 0, 1, 1)
PANELS = {
    "campaign-never-enough": ("never-enough-zip-hoodie", 0.44, 0.86, WHOLE),
    # the two shoulder crosses only, not the sleeve print
    "campaign-crossbone": ("crossbone-zip-hoodie", 0.46, 0.9, (0.18, 0.12, 0.93, 0.6)),
    "campaign-cross": ("cross-zip-hoodie", 0.46, 0.5, WHOLE),
}


def lift_print(product, part):
    """White print on the back view of the black flat, as a 0..1 tone crop."""
    src, alpha = art_flats.sheet(product, "black")
    l, t, r, b = art_flats.PRODUCTS[product]["boxes"]["back"]
    fl, ft, fr, fb = part
    box = (round(l + fl * (r - l)), round(t + ft * (b - t)), round(l + fr * (r - l)), round(t + fb * (b - t)))
    lum = np.asarray(src.crop(box).convert("L"), np.float32) / 255
    inside = np.asarray(alpha.crop(box), np.float32) / 255
    ink = np.clip((lum - 0.55) / 0.35, 0, 1) * inside
    ys, xs = np.nonzero(ink > 0.5)
    return ink[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def panel(name, product, cy, width, part, seed):
    art = lift_print(product, part)
    scale = W * width / art.shape[1]
    if art.shape[0] * scale > H * 0.62:
        scale = H * 0.62 / art.shape[0]
    pw, ph = round(art.shape[1] * scale), round(art.shape[0] * scale)
    pr = np.asarray(Image.fromarray((art * 255).astype(np.uint8)).resize((pw, ph), Image.LANCZOS), np.float32) / 255

    # halo behind, in thinner, greyer ink so it dissolves into grain
    n = 31
    items = [(-180 + k * (180 / (n - 1)) * 2, (150 if k % 2 else 300) + (k % 3) * 30, 1.6, 0.8) for k in range(n)]
    halo = render(name + "-halo", svg_doc(W, H, rays(W / 2, H * cy, 170, items)), W, H)

    tone = halo * 0.85
    x, y = (W - pw) // 2, round(H * cy - ph / 2)
    canvas = np.zeros((H, W), np.float32)
    canvas[y:y + ph, x:x + pw] = pr
    # keep a dark margin around the print so it reads cleanly over the rays
    clear = np.asarray(Image.fromarray((canvas * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(15))
                       .filter(ImageFilter.GaussianBlur(4)), np.float32) / 255
    tone = np.maximum(tone * (1 - clear), canvas)
    ink, big = screenprint(tone, seed=seed, grain=0.12, clump=0.16, dropout=0.08, scratches=30)
    save_ink(name, ink, big)


def main():
    for i, (name, (product, cy, width, part)) in enumerate(PANELS.items()):
        panel(name, product, cy, width, part, seed=61 + i)


if __name__ == "__main__":
    main()
