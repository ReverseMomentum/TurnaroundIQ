"""Shared helpers for the FTD artwork pipeline.

Artwork is drawn as greyscale SVG (white = full ink, black = bare paper), rasterised
with Chromium, then put through a screen-print pass: tones become stochastic ink
coverage, edges break up, and coarse dropout gives the worn, scanned-poster finish.
"""

import math
import re
import random
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "art" / "_build"
OUT = ROOT / "public" / "art"

ORANGE = np.array([216, 120, 43], dtype=np.float32)  # #D8782B
AMBER = np.array([185, 106, 43], dtype=np.float32)  # #B96A2B
BONE = np.array([230, 220, 201], dtype=np.float32)  # #E6DCC9


def mirror_x(path, cx):
    """Mirror an absolute-coordinate path (M/L/C/Q/Z, space separated pairs) around x=cx."""
    out = re.findall(r"[A-Za-z]|-?\d*\.?\d+", path)
    res, i = [], 0
    while i < len(out):
        t = out[i]
        if t.isalpha():
            res.append(t)
            i += 1
            continue
        x, y = float(out[i]), float(out[i + 1])
        res.append(f"{2 * cx - x:.1f},{y:.1f}")
        i += 2
    return " ".join(res)


def svg_doc(w, h, body, defs="", scale=1):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w * scale}" height="{h * scale}" viewBox="0 0 {w} {h}">'
        f"<defs>{defs}</defs><rect width='{w}' height='{h}' fill='#000'/>{body}</svg>"
    )


def render(name, svg, w, h):
    BUILD.mkdir(parents=True, exist_ok=True)
    src = BUILD / f"{name}.svg"
    png = BUILD / f"{name}.png"
    src.write_text(svg)
    subprocess.run(
        ["node", str(ROOT / "scripts" / "render-svg.mjs"), str(src), str(png), str(w), str(h)],
        check=True,
        cwd=ROOT,
    )
    return np.asarray(Image.open(png).convert("L"), dtype=np.float32) / 255.0


def _blur_noise(shape, radius, rng):
    n = Image.fromarray((rng.random(shape) * 255).astype(np.uint8))
    if radius:
        n = n.filter(ImageFilter.GaussianBlur(radius))
    a = np.asarray(n, dtype=np.float32) / 255.0
    a = (a - a.mean()) / (a.std() + 1e-6)  # normalise so every scale has equal weight
    return a


def screenprint(tone, seed=1, grain=0.16, clump=0.22, dropout=0.10, scratches=40, dust=0.00015):
    """Tone (0..1) -> ink coverage (0..1) with print imperfections."""
    rng = np.random.default_rng(seed)
    h, w = tone.shape
    fine = _blur_noise(tone.shape, 0.6, rng)
    mid = _blur_noise(tone.shape, 2.2, rng)
    big = _blur_noise(tone.shape, 18, rng)
    # stochastic threshold: mid tones dissolve into clumped grain
    thr = 0.5 + grain * fine + clump * mid + 0.06 * big
    t = np.clip(tone, 0, 1) ** 1.15
    ink = np.clip((t - thr) * 9 + 0.5, 0, 1) * np.clip(tone * 10 - 0.2, 0, 1)
    # sparse dust picked up off the screen
    dust = Image.fromarray(((rng.random(tone.shape) < dust) * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(3))
    ink = np.maximum(ink, np.asarray(dust, dtype=np.float32) / 255.0 * 0.85)
    # coarse ink starvation patches
    starve = np.clip((big * 0.5 + mid * 0.35 - (1.6 - dropout * 6)) * 3, 0, 1)
    ink *= 1 - starve
    # pinholes
    ink *= (rng.random(tone.shape) > 0.012 + 0.03 * np.clip(-big, 0, 1)).astype(np.float32)
    # fine scratches through the ink
    img = Image.new("L", (w, h), 0)
    from PIL import ImageDraw

    d = ImageDraw.Draw(img)
    r = random.Random(seed)
    for _ in range(scratches):
        x, y = r.uniform(0, w), r.uniform(0, h)
        ang = r.uniform(-0.5, 0.5) + (math.pi / 2 if r.random() < 0.5 else 0)
        ln = r.uniform(30, 260)
        d.line([(x, y), (x + math.cos(ang) * ln, y + math.sin(ang) * ln)], fill=255, width=r.choice([1, 1, 2]))
    ink *= 1 - np.asarray(img, dtype=np.float32) / 255.0 * 0.9
    return ink, big


def save_ink(name, ink, big, colour="orange", size=None, quality=86):
    """Save ink as an RGBA WebP (ink colour over transparency)."""
    h, w = ink.shape
    if colour == "orange":
        mix = np.clip(0.5 + big[..., None] * 0.35, 0, 1)
        rgb = ORANGE * mix + AMBER * (1 - mix)
    else:
        rgb = np.broadcast_to(BONE, (h, w, 3))
    rgba = np.dstack([rgb, ink * 255]).astype(np.uint8)
    im = Image.fromarray(rgba, "RGBA")
    if size:
        im = im.resize(size, Image.LANCZOS)
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.webp"
    im.save(path, "WEBP", quality=quality, method=6)
    print(f"  wrote {path.relative_to(ROOT)} {im.size}")
    return path


def rays(cx, cy, r0, items):
    """Spiked halo: items = [(angle_deg, length, base_halfwidth_deg, tone)]."""
    out = []
    for ang, ln, hw, tone in items:
        a = math.radians(ang)
        a1, a2 = math.radians(ang - hw), math.radians(ang + hw)
        tip = (cx + math.cos(a) * (r0 + ln), cy + math.sin(a) * (r0 + ln))
        b1 = (cx + math.cos(a1) * r0, cy + math.sin(a1) * r0)
        b2 = (cx + math.cos(a2) * r0, cy + math.sin(a2) * r0)
        # slightly concave sides so the spikes read as forged thorns rather than triangles
        m1 = (cx + math.cos(a - hw * 0.004) * (r0 + ln * 0.55), cy + math.sin(a - hw * 0.004) * (r0 + ln * 0.55))
        m2 = (cx + math.cos(a + hw * 0.004) * (r0 + ln * 0.55), cy + math.sin(a + hw * 0.004) * (r0 + ln * 0.55))
        g = int(255 * tone)
        out.append(
            f"<path d='M{b1[0]:.1f},{b1[1]:.1f} Q{m1[0]:.1f},{m1[1]:.1f} {tip[0]:.1f},{tip[1]:.1f} "
            f"Q{m2[0]:.1f},{m2[1]:.1f} {b2[0]:.1f},{b2[1]:.1f} Z' fill='rgb({g},{g},{g})'/>"
        )
    return "".join(out)
