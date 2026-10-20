"""Builds every artwork in public/art. Run from ftd/: python3 scripts/build_art.py [name ...]"""

import sys

import numpy as np
from PIL import Image, ImageFilter

from art_lib import BONE, OUT, _blur_noise, render, save_ink, screenprint, svg_doc

import art_garments
import art_flats
import art_hero
import art_scenes

INK_JOBS = {
    "hero-skull": (art_hero.build, dict(seed=11), (1200, 1500)),
    "cathedral": (art_scenes.cathedral, dict(seed=12, scratches=30), (1600, 760)),
    "campaign-hooded": (art_scenes.campaign_hooded, dict(seed=13), (900, 1200)),
    "campaign-relic": (art_scenes.campaign_relic, dict(seed=14), (900, 1200)),
    "campaign-sigil": (art_scenes.campaign_sigil, dict(seed=15), (900, 1200)),
}

GARMENTS = {
    "pants": (art_garments.pants, 23),
    "tee-heaven": (art_garments.tee_heaven, 24),
    "tee-decay": (art_garments.tee_decay, 25),
}

# close-ups cropped from a 3x garment render, in 1x coordinates (left, top, width).
# The zip hoodie's images come from the supplied flats instead (art_flats.py).
CROPS = {}

SCALE = 3
GARMENT_BG = np.array([21, 17, 14], dtype=np.float32)  # #15110E


def garment(name, fn, seed):
    w, h, defs, fab, prn, mask = fn()
    W, H = w * SCALE, h * SCALE
    fabric = render(name + "-fab", svg_doc(w, h, fab, defs, SCALE), W, H)
    printed = render(name + "-print", svg_doc(w, h, prn, defs, SCALE), W, H)
    clip = render(name + "-mask", svg_doc(w, h, mask, defs, SCALE), W, H)
    cover = (fabric > 0.012).astype(np.float32)  # garment silhouette incl. rib and hood
    cover = np.asarray(Image.fromarray((cover * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1)),
                       dtype=np.float32) / 255

    rng = np.random.default_rng(seed)
    knit = _blur_noise(fabric.shape, 0.7, rng) * 0.035 + _blur_noise(fabric.shape, 2, rng) * 0.02
    wash = _blur_noise(fabric.shape, 80, rng) * 0.03 + _blur_noise(fabric.shape, 22, rng) * 0.01
    t = np.clip(fabric + knit + wash, 0, 1)
    # washed-black dye: tone 0..1 -> deep warm black .. faded charcoal
    lo, hi = np.array([9, 8, 7], np.float32), np.array([112, 104, 96], np.float32)
    rgb = lo + (hi - lo) * (t[..., None] ** 1.25)

    ink, _ = screenprint(printed * clip, seed=seed, grain=0.05, clump=0.08, dropout=0.16, scratches=180, dust=0)
    shade = 0.55 + 0.9 * np.clip(fabric, 0, 1)[..., None]
    rgb = rgb * (1 - ink[..., None] * 0.94) + (BONE * 0.86 * shade) * ink[..., None] * 0.94

    # studio backdrop with a soft pool of light and a contact shadow
    yy, xx = np.mgrid[0:H, 0:W]
    pool = np.exp(-(((xx - W / 2) / (W * 0.55)) ** 2 + ((yy - H * 0.45) / (H * 0.6)) ** 2))
    bg = GARMENT_BG * (0.72 + 0.5 * pool[..., None])
    shadow = np.asarray(Image.fromarray((cover * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(28 * SCALE / 3)),
                        dtype=np.float32) / 255
    shadow = np.roll(shadow, 14, axis=0)
    bg = bg * (1 - 0.55 * shadow[..., None])
    grain = _blur_noise(fabric.shape, 0.6, rng)[..., None] * 2.2
    out = bg * (1 - cover[..., None]) + rgb * cover[..., None] + grain
    img = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB")
    return img


def main(names):
    OUT.mkdir(parents=True, exist_ok=True)
    for name, (fn, sp, size) in INK_JOBS.items():
        if names and name not in names:
            continue
        print(name)
        w, h, defs, body = fn()
        tone = render(name, svg_doc(w, h, body, defs), w, h)
        ink, big = screenprint(tone, **sp)
        save_ink(name, ink, big, size=size)

    for name, (fn, seed) in GARMENTS.items():
        if names and name not in names:
            continue
        print(name)
        big = garment(name, fn, seed)
        big.resize((1000, 1100), Image.LANCZOS).save(OUT / f"{name}.webp", "WEBP", quality=84, method=6)
        big.resize((400, 440), Image.LANCZOS).save(OUT / f"{name}-thumb.webp", "WEBP", quality=80, method=6)
        for crop, (src, (x, y, cw)) in CROPS.items():
            if src != name:
                continue
            ch = cw * 1.1
            c = big.crop((x * SCALE, y * SCALE, int((x + cw) * SCALE), int((y + ch) * SCALE)))
            c.resize((1000, 1100), Image.LANCZOS).save(OUT / f"{crop}.webp", "WEBP", quality=84, method=6)
            c.resize((400, 440), Image.LANCZOS).save(OUT / f"{crop}-thumb.webp", "WEBP", quality=80, method=6)
            print("  " + crop)


    if not names or any(n.startswith("hoodie") for n in names):
        print("hoodie (from supplied flats)")
        art_flats.main()


if __name__ == "__main__":
    main(sys.argv[1:])
