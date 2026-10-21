"""FTD garment labels: print-ready artwork at actual size, plus an overview sheet.

    python3 scripts/build_labels.py

Writes techpack/labels/:
  FTD-LBL-01_neck-print_<size>.pdf / _300dpi.png   screen-printed tee neck label (film: black = ink)
  FTD-LBL-01_neck-print_all-sizes.pdf / .png         one screen with every size; tape off all but one
  FTD-LBL-02_woven-main.pdf                         woven main label (hoodies, joggers)
  FTD-LBL-03_care_<style>.pdf                       printed satin care labels
  FTD-LBL-04_size-tabs.pdf                          printed size tabs, one page per size
  FTD-LBL-05_woven-flag.pdf                         optional woven hem/sleeve flag
  FTD-labels-overview.pdf                           all of the above with specs, for suppliers

Care wording and compositions are PROPOSED; edit CARE and COMPOSITION below.
"""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "techpack" / "labels"
BUILD = ROOT / "art" / "_build" / "labels"
FONTS = ROOT / "node_modules" / "@fontsource"
SIZES = ["XS", "S", "M", "L", "XL", "XXL"]
BONE, INK = "#E6DCC9", "#0A0807"

CARE = [
    "Wash 30°C inside out",
    "Do not bleach",
    "Do not tumble dry",
    "Iron low, not on print",
    "Do not dry clean",
]
COMPOSITION = {
    "tee": ["100% COTTON"],
    "hoodie": ["Body 100% cotton", "Rib 95% cotton", "5% elastane"],
    "joggers": ["Body 100% cotton", "Rib 95% cotton", "5% elastane"],
}
CARE_STYLES = {
    "hoodies": ("hoodie", "Crossbone Zip Hoodie · Never Enough Zip Hoodie"),
    "joggers": ("joggers", "Crossbone Baggy Pants"),
}


def logo(fill):
    src = (ROOT / "src" / "components" / "logoPath.js").read_text()
    vb = re.search(r'LOGO_VIEWBOX = "([^"]+)"', src).group(1)
    d = re.search(r'LOGO_PATH =\s*"([^"]+)"', src).group(1)
    return f'<svg viewBox="{vb}" style="display:block;width:100%"><path d="{d}" fill="{fill}" fill-rule="evenodd"/></svg>'


def care_icons(c, size_mm=4.6, gap_mm=1.6):
    """ISO-style care symbols: wash 30, no bleach, no tumble, iron low, no dry clean."""
    s = f'stroke="{c}" stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round"'
    x = '<path d="M3,3 L21,21 M21,3 L3,21" ' + s + "/>"
    icons = [
        f'<path d="M2,7 L4.5,20 L19.5,20 L22,7" {s}/><path d="M2,7 q2.5,-3 5,0 q2.5,3 5,0 q2.5,-3 5,0 q2.5,3 5,0" {s}/>'
        f'<text x="12" y="17.2" text-anchor="middle" font-family="Barlow" font-weight="600" font-size="7.5" fill="{c}">30</text>',
        f'<path d="M2.5,20 L12,3.5 L21.5,20 Z" {s}/>{x}',
        f'<rect x="3" y="3" width="18" height="18" {s}/><circle cx="12" cy="12" r="6.5" {s}/>{x}',
        f'<path d="M3,18.5 L21,18.5 L21,13 C21,8.5 17,7 13,7 L8,7 C5.5,7 4,11 3,18.5 Z" {s}/><circle cx="13" cy="13.5" r="1.3" fill="{c}"/>',
        f'<circle cx="12" cy="12" r="9" {s}/>{x}',
    ]
    return "".join(f'<svg viewBox="0 0 24 24" style="width:{size_mm}mm;height:{size_mm}mm;margin-right:{gap_mm}mm">{i}</svg>' for i in icons)


BASE_CSS = f"""
@font-face{{font-family:Barlow;font-weight:600;src:url(file://{FONTS}/barlow-condensed/files/barlow-condensed-latin-600-normal.woff2)}}
@font-face{{font-family:Barlow;font-weight:500;src:url(file://{FONTS}/barlow-condensed/files/barlow-condensed-latin-500-normal.woff2)}}
@font-face{{font-family:Grenze;font-weight:600;src:url(file://{FONTS}/grenze/files/grenze-latin-600-normal.woff2)}}
* {{ box-sizing: border-box; margin: 0; }}
body {{ margin: 0; }}
.lbl {{ font-family: Barlow; text-transform: uppercase; display: flex; flex-direction: column; align-items: center; }}
.trk {{ letter-spacing: .22em; }}
"""


# ---------------------------------------------------------------- label bodies (mm)

def neck_print(size, ink=INK, bg="#fff"):
    """60 x 52 mm. size=None -> every size in a row (one screen, tape off the rest)."""
    if size:
        sz = f'<div style="font:600 11mm/1 Barlow;margin:1.2mm 0 .6mm">{size}</div>'
    else:
        cells = "".join(f'<span style="border:.3mm solid {ink};padding:.5mm 1.1mm;margin:0 .45mm">{s}</span>' for s in SIZES)
        sz = f'<div style="font:600 3.6mm/1 Barlow;margin:2.2mm 0 1.4mm;display:flex">{cells}</div>'
    return f"""<div class="lbl" style="width:60mm;height:52mm;padding:2.5mm 3mm;background:{bg};color:{ink}">
<div style="width:30mm">{logo(ink)}</div>
<div class="trk" style="font:600 2.3mm/1 Barlow;margin-top:1.4mm;letter-spacing:.3em">Forsaken to decay</div>
{sz}
<div class="trk" style="font:600 2.3mm/1.25 Barlow">100% cotton</div>
<div style="display:flex;margin-top:1.6mm">{care_icons(ink, 4.4, 1.3)}</div>
<div class="trk" style="font:500 1.9mm/1.3 Barlow;margin-top:1.2mm;text-align:center">Wash 30°C inside out · Iron on reverse</div>
</div>"""


def woven_main(thread=BONE, ground=INK):
    """50 x 20 mm visible, end-fold (+8 mm each end)."""
    fold = f"background:repeating-linear-gradient(90deg,{ground},{ground} .6mm,#000 .6mm,#000 1.2mm)"
    return f"""<div style="display:flex;width:66mm;height:20mm">
<div style="width:8mm;{fold};opacity:.55"></div>
<div class="lbl" style="width:50mm;height:20mm;background:{ground};color:{thread};justify-content:center">
<div style="width:27mm">{logo(thread)}</div>
<div class="trk" style="font:600 1.9mm/1 Barlow;margin-top:1.4mm;letter-spacing:.32em">Forsaken to decay</div></div>
<div style="width:8mm;{fold};opacity:.55"></div></div>"""


def care_label(kind, ink=BONE, bg=INK):
    """30 x 80 mm satin, top 10 mm is sewn into the seam."""
    comp = "".join(f"<div>{c}</div>" for c in COMPOSITION[kind])
    care = "".join(f"<div>{c}</div>" for c in CARE)
    return f"""<div class="lbl" style="width:30mm;height:80mm;background:{bg};color:{ink};padding:0 2.5mm 3mm">
<div style="width:100%;height:10mm;border-bottom:.2mm dashed {ink};opacity:.5;font:500 1.6mm/10mm Barlow;text-align:center;letter-spacing:.2em">SEAM</div>
<div style="width:16mm;margin-top:4mm">{logo(ink)}</div>
<div class="trk" style="font:600 1.6mm/1 Barlow;margin-top:1.2mm">Forsaken to decay</div>
<div style="font:600 2.1mm/1.45 Barlow;margin-top:4mm;text-align:center;letter-spacing:.12em">{comp}</div>
<div style="display:flex;margin-top:4mm;flex-wrap:wrap;justify-content:center;width:25mm">{care_icons(ink, 4, .9)}</div>
<div style="font:500 1.85mm/1.5 Barlow;margin-top:3mm;text-align:center;letter-spacing:.06em;white-space:nowrap">{care}</div>
<div class="trk" style="font:500 1.6mm/1.4 Barlow;margin-top:auto;text-align:center">FTD — Forsaken to Decay<br>[address / website]</div>
</div>"""


def size_tab(size, ink=BONE, bg=INK):
    """15 x 25 mm satin, folded in half to 15 x 12.5 mm; sewn under the main label."""
    return f"""<div class="lbl" style="width:15mm;height:25mm;background:{bg};color:{ink};justify-content:space-around">
<div style="font:600 5mm/1 Barlow">{size}</div><div style="width:100%;border-top:.2mm dashed {ink};opacity:.5"></div>
<div style="font:600 5mm/1 Barlow;transform:rotate(180deg)">{size}</div></div>"""


def woven_flag(thread=BONE, ground=INK):
    """15 x 30 mm loop, folded to 15 x 15 mm, sewn into a seam with the logo showing."""
    return f"""<div class="lbl" style="width:15mm;height:30mm;background:{ground};color:{thread};justify-content:space-around">
<div style="width:11mm">{logo(thread)}</div><div style="width:100%;border-top:.2mm dashed {thread};opacity:.45"></div>
<div style="width:11mm;transform:rotate(180deg)">{logo(thread)}</div></div>"""


# ---------------------------------------------------------------- rendering

def pdf(name, body, w_mm, h_mm, pages=None):
    """One label per page at actual size."""
    BUILD.mkdir(parents=True, exist_ok=True)
    pages = pages or [body]
    html = (f"<!doctype html><html><head><meta charset='utf-8'><style>{BASE_CSS}"
            f"@page{{size:{w_mm}mm {h_mm}mm;margin:0}} .pg{{width:{w_mm}mm;height:{h_mm}mm;page-break-after:always;overflow:hidden}}"
            f"</style></head><body>{''.join(f'<div class=pg>{p}</div>' for p in pages)}</body></html>")
    src = BUILD / f"{name}.html"
    src.write_text(html)
    subprocess.run(["node", str(ROOT / "scripts" / "label-pdf.mjs"), str(src), str(OUT / f"{name}.pdf")], check=True, cwd=ROOT)
    return src


def film(name, body, w_mm, h_mm):
    """300 dpi film positive (black = ink) for screen-printed labels."""
    w, h = round(w_mm / 25.4 * 300), round(h_mm / 25.4 * 300)
    zoom = w / (w_mm / 25.4 * 96)
    src = BUILD / f"{name}-film.html"
    src.write_text(f"<!doctype html><html><head><meta charset='utf-8'><style>{BASE_CSS} body{{zoom:{zoom}}}</style></head>"
                   f"<body>{body}</body></html>")
    png = OUT / f"{name}_300dpi.png"
    subprocess.run(["node", str(ROOT / "scripts" / "html-shot.mjs"), str(src), str(png), str(w), str(h)], check=True, cwd=ROOT)
    from PIL import Image

    Image.open(png).convert("L").save(png, dpi=(300, 300), optimize=True)


def overview():
    """A4 landscape sheet: every label at 1:1 on its garment colour, with specs."""
    def card(title, art, spec_rows, note=""):
        rows = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in spec_rows)
        return (f"<div class='card'><h3>{title}</h3><div class='art'>{art}</div><table>{rows}</table>"
                f"{f'<p class=note>{note}</p>' if note else ''}</div>")

    p1 = "".join([
        card("LBL-01 · T-shirt neck print", neck_print("M", BONE, INK),
             [("Method", "Screen print, white ink, inside back neck"), ("Size", "60 × 52 mm"),
              ("Position", "Centred, top edge 2 cm below neck seam"), ("Files", "Per size PDF + 300 dpi film; all-sizes film for one screen")],
             "Use a blank with a tear-away label. Tape off all sizes but one on the all-sizes screen."),
        card("LBL-02 · Woven main label", woven_main(),
             [("Type", "Damask woven, end-fold"), ("Size", "50 × 20 mm visible (66 mm before folding)"),
              ("Colours", "Bone thread on black ground"), ("Position", "Hoodie: CB neck, on neck tape. Joggers: CB inside waistband")],
             "Smallest text 1.9 mm: confirm your weaver can hold it at damask density."),
        card("LBL-05 · Woven flag (optional)", woven_flag(),
             [("Type", "Damask woven loop, folded"), ("Size", "15 × 30 mm (15 × 15 folded)"),
              ("Position", "Hoodie left hem rib seam; joggers right hip seam")],
             "The lower half is printed upside down on purpose: folded into a loop, both faces read the right way up."),
    ])
    p2 = "".join([
        card("LBL-03 · Care label, hoodies", care_label("hoodie"),
             [("Type", "Printed satin, black, white print"), ("Size", "30 × 80 mm (top 10 mm in seam)"),
              ("Position", "Left side seam, 8 cm above hem"), ("Used on", CARE_STYLES["hoodies"][1])]),
        card("LBL-03 · Care label, joggers", care_label("joggers"),
             [("Type", "Printed satin, black, white print"), ("Size", "30 × 80 mm (top 10 mm in seam)"),
              ("Position", "Inside left side seam, below waistband"), ("Used on", CARE_STYLES["joggers"][1])]),
        card("LBL-04 · Size tabs", "<div style='display:flex;gap:2mm'>" + "".join(size_tab(s) for s in ("S", "M", "L")) + "</div>",
             [("Type", "Printed satin, folded"), ("Size", "15 × 25 mm (15 × 12.5 folded)"),
              ("Position", "Sewn under the main label"), ("Sizes", " · ".join(SIZES))],
             "Lower half upside down on purpose (folded tab, size reads on both faces)."),
    ])
    css = BASE_CSS + """
@page{size:A4 landscape;margin:0}
.page{width:297mm;height:210mm;padding:12mm 13mm;page-break-after:always;font-family:Barlow;color:#111}
.page:last-child{page-break-after:auto}
header{display:flex;justify-content:space-between;align-items:flex-end;border-bottom:.6mm solid #111;padding-bottom:2.5mm;margin-bottom:6mm}
header h1{font:600 15pt Barlow;letter-spacing:.08em;text-transform:uppercase}
header span{font:500 8pt Barlow;letter-spacing:.06em;text-transform:uppercase;color:#555}
.grid{display:flex;gap:6mm;align-items:stretch}
.card{flex:1;border:.25mm solid #999;padding:4mm;display:flex;flex-direction:column;gap:3mm}
.card h3{font:600 9.5pt Barlow;letter-spacing:.1em;text-transform:uppercase}
.art{min-height:86mm;display:grid;place-items:center;background:#e9e6e1}
table{border-collapse:collapse;font:500 8pt Barlow;width:100%}
td{border:.25mm solid #bbb;padding:1.2mm 1.6mm;vertical-align:top}
td:first-child{width:28%;font-weight:600;text-transform:uppercase;letter-spacing:.06em;background:#f6f6f6}
.note{font:500 7.6pt Barlow;color:#444}
.foot{font:500 7.6pt Barlow;color:#555;margin-top:4mm;line-height:1.5}
"""
    foot = ("All artwork shown at actual size. Values marked in the tech packs as PROPOSED: compositions follow the proposed fabrics, "
            "and care wording is chosen to protect the prints (30°C inside out, no tumble dry). UK law requires the fibre "
            "composition on the garment; brand name and an address (on label or packaging) identify who is responsible. "
            "Replace [address / website] before ordering care labels.")
    html = (f"<!doctype html><html><head><meta charset='utf-8'><style>{css}</style></head><body>"
            f"<section class='page'><header><h1>FTD labels · Drop 01</h1><span>Print and woven labels · v0.1</span></header>"
            f"<div class='grid'>{p1}</div><p class='foot'>{foot}</p></section>"
            f"<section class='page'><header><h1>FTD labels · Drop 01</h1><span>Care and size labels · v0.1</span></header>"
            f"<div class='grid'>{p2}</div><p class='foot'>{foot}</p></section></body></html>")
    src = BUILD / "FTD-labels-overview.html"
    src.write_text(html)
    subprocess.run(["node", str(ROOT / "scripts" / "html-to-pdf.mjs"), str(src), str(OUT / "FTD-labels-overview.pdf")],
                   check=True, cwd=ROOT)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for s in SIZES:
        pdf(f"FTD-LBL-01_neck-print_{s}", neck_print(s), 60, 52)
        film(f"FTD-LBL-01_neck-print_{s}", neck_print(s), 60, 52)
    pdf("FTD-LBL-01_neck-print_all-sizes", neck_print(None), 60, 52)
    film("FTD-LBL-01_neck-print_all-sizes", neck_print(None), 60, 52)
    pdf("FTD-LBL-02_woven-main", woven_main(), 66, 20)
    for key, (kind, _) in CARE_STYLES.items():
        pdf(f"FTD-LBL-03_care_{key}", care_label(kind), 30, 80)
    pdf("FTD-LBL-04_size-tabs", None, 15, 25, pages=[size_tab(s) for s in SIZES])
    pdf("FTD-LBL-05_woven-flag", woven_flag(), 15, 30)
    overview()
    print("labels written to", OUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
