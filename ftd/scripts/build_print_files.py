"""Print-ready artwork from the supplied black-on-white art (art/print/*-source.*).

Each piece is cropped to its artwork, upscaled 3x, traced to a vector SVG, then
rendered as a 300 dpi black-on-white PNG at its print size (the film positive a
screen printer needs: black = ink). Output: techpack/artwork/.
Run from ftd/: python3 scripts/build_print_files.py
"""

import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "art" / "print"
OUT = ROOT / "techpack" / "artwork"
BUILD = ROOT / "art" / "_build" / "print"
DPI = 300

# name -> source file, print width in cm (height follows the artwork). Widths are
# PROPOSED, taken from the flats; techpack/spec.py carries the same numbers.
ART = {
    "FTD-ART-01_FTD-wordmark": ("ftd-wordmark-source.jpg", 45.0),
    "FTD-ART-02_Never-Enough": ("never-enough-source.png", 50.0),
    "FTD-ART-03_Crossbone-cross": ("crossbone-cross-source.png", 30.0),
    # T-shirt versions: own screens at T-shirt size
    "FTD-ART-01T_FTD-wordmark-tee": ("ftd-wordmark-source.jpg", 14.0),
    "FTD-ART-02T_Never-Enough-tee": ("never-enough-source.png", 38.0),
}


def flatten(path):
    im = Image.open(path)
    if im.mode in ("RGBA", "LA"):
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
        bg.alpha_composite(im.convert("RGBA"))
        im = bg
    return im.convert("L")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    BUILD.mkdir(parents=True, exist_ok=True)
    for name, (src, width_cm) in ART.items():
        g = flatten(SRC / src)
        a = np.asarray(g) < 128
        ys, xs = np.nonzero(a)
        pad = 12
        box = (max(xs.min() - pad, 0), max(ys.min() - pad, 0), xs.max() + pad, ys.max() + pad)
        crop = g.crop(box)
        up = crop.resize((crop.width * 3, crop.height * 3), Image.LANCZOS)
        bw = BUILD / f"{name}.png"
        up.point(lambda v: 0 if v < 128 else 255).save(bw)
        svg = OUT / f"{name}.svg"
        subprocess.run(["node", str(ROOT / "scripts" / "trace.mjs"), str(bw), str(svg), "6"], check=True, cwd=ROOT)
        # 300 dpi film positive at print size
        w = round(width_cm / 2.54 * DPI)
        h = round(w * crop.height / crop.width)
        page = BUILD / f"{name}-print.html"
        page.write_text(f"<html><body style='margin:0;background:#fff'>"
                        f"<img src='file://{svg}' style='width:{w}px;height:{h}px;display:block'></body></html>")
        png = OUT / f"{name}_{width_cm:g}cm_300dpi.png"
        subprocess.run(["node", str(ROOT / "scripts" / "html-shot.mjs"), str(page), str(png), str(w), str(h)],
                       check=True, cwd=ROOT)
        out = Image.open(png).convert("L")
        out.save(png, dpi=(DPI, DPI), optimize=True)
        print(f"  {name}: {width_cm:g} x {width_cm * h / w:.1f} cm, {w} x {h} px at {DPI} dpi")


if __name__ == "__main__":
    main()
