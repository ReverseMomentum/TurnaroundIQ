"""Builds the Drop 01 sample tech packs: techpack/<code>_<name>.pdf

    python3 scripts/build_techpack.py

Data lives in techpack/spec.py. The flats come from art/flats/<slug>-black.png;
callouts and measurement lines are drawn over them in sheet pixel coordinates.
"""

import html
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "techpack"))
sys.path.insert(0, str(ROOT / "scripts"))

import art_flats  # noqa: E402
import spec  # noqa: E402

OUT = ROOT / "techpack"
BUILD = ROOT / "art" / "_build" / "techpack"

# Feature callouts and points of measure, in flat-sheet pixel coordinates.
# Both hoodies share one sheet template; the pants have their own.
CALLOUTS = {
    "hoodie": {
        "front": [(560, 185, "Two-piece hood, self-lined, centre seam"), (455, 262, "Zip top stop at neck"),
                  (455, 720, "Full-length zip, metal, single slider"), (210, 498, "Dropped shoulder, topstitched"),
                  (360, 650, "Split pouch pocket, bar-tacked ends"), (95, 700, "Balloon sleeve, gathered into cuff"),
                  (193, 985, "Rib cuff"), (560, 772, "Rib hem, body gathered in (blouson)"), (700, 330, "Chest print P1 (FTD wordmark)")],
        "back": [(1357, 262, "Hood centre seam"), (1357, 560, "Back print area (see artwork page)")],
    },
    "pants": {
        "front": [(300, 108, "Stacked double waistband, elastic"), (352, 152, "Drawcord exits at CF"),
                  (215, 182, "Slanted side pocket"), (162, 560, "Curved outseam (barrel leg)"),
                  (250, 712, "Clean hem, twin-needle"), (262, 356, "Front print (see artwork page)")],
        "back": [(850, 192, "Rear welt pocket (×2)"), (912, 320, "Centre back seam"), (995, 260, "Back print (see artwork page)")],
    },
}
POM_LINES = {
    "hoodie": {
        "front": [("A", 400, 255, 400, 805), ("B", 215, 610, 805, 610), ("E", 297, 798, 629, 798),
                  ("H", 792, 488, 742, 995), ("J", 55, 760, 276, 760), ("K", 161, 994, 226, 994)],
        "back": [("C", 1040, 470, 1690, 470), ("O", 1357, 195, 1357, 352)],
    },
    "pants": {
        "front": [("A", 257, 106, 444, 106), ("C", 188, 300, 511, 300), ("D", 353, 98, 353, 352),
                  ("F", 175, 388, 330, 388), ("G", 158, 540, 319, 540), ("H", 167, 708, 332, 708),
                  ("I", 342, 364, 332, 706)],
        "back": [("E", 912, 96, 912, 415)],
    },
}

# where along each measurement line its letter sits (default: the middle)
LABEL_AT = {("pants", "A"): 0.25, ("pants", "D"): 0.6, ("pants", "I"): 0.35}

CSS = """
@page { size: A4 landscape; margin: 0; }
* { box-sizing: border-box; }
body { margin: 0; font-family: 'Plex', monospace; font-size: 8.6pt; color: #111; background: #fff; }
.page { width: 297mm; height: 210mm; padding: 11mm 13mm 9mm; position: relative; page-break-after: always; overflow: hidden; }
.page:last-child { page-break-after: auto; }
header.bar { display: flex; align-items: center; justify-content: space-between; border-bottom: 0.6mm solid #111; padding-bottom: 2.5mm; margin-bottom: 5mm; }
header.bar .l { display: flex; align-items: center; gap: 4mm; }
header.bar svg { height: 9mm; width: auto; }
header.bar h1 { font: 600 15pt 'Barlow', sans-serif; letter-spacing: .06em; text-transform: uppercase; margin: 0; }
header.bar .meta { font-size: 7.6pt; text-align: right; line-height: 1.5; color: #333; }
h2 { font: 600 11.5pt 'Barlow', sans-serif; letter-spacing: .12em; text-transform: uppercase; margin: 0 0 3mm; }
h3 { font: 600 9.5pt 'Barlow', sans-serif; letter-spacing: .1em; text-transform: uppercase; margin: 4mm 0 2mm; }
table { width: 100%; border-collapse: collapse; }
th, td { border: 0.25mm solid #999; padding: 1.4mm 2mm; text-align: left; vertical-align: top; }
th { background: #eee; font: 600 8pt 'Barlow', sans-serif; letter-spacing: .08em; text-transform: uppercase; }
td.num, th.num { text-align: center; white-space: nowrap; }
td.sample, th.sample { background: #fff3cf; font-weight: 600; }
.tag { display: inline-block; padding: .2mm 1.4mm; border: .25mm solid; font: 600 7pt 'Barlow', sans-serif; letter-spacing: .08em; white-space: nowrap; }
.tag.PROPOSED { color: #8a5a00; border-color: #c9952b; background: #fff6e0; }
.tag.TBC { color: #9b1c1c; border-color: #d46a6a; background: #fdecec; }
.tag.CONFIRMED { color: #1d6b2f; border-color: #57a56a; background: #eaf6ec; }
.flats { display: flex; gap: 6mm; align-items: flex-start; }
.flat { flex: 1; text-align: center; }
.flat .fimg { position: relative; display: inline-block; }
.flat img { display: block; max-width: 100%; max-height: var(--fh, 120mm); width: auto; height: auto; }
.flat svg.ov { position: absolute; inset: 0; width: 100%; height: 100%; }
.flat .cap { font: 600 8pt 'Barlow', sans-serif; letter-spacing: .14em; text-transform: uppercase; text-align: center; margin-top: 1mm; }
.cols { display: flex; gap: 7mm; }
.cols > * { flex: 1; }
ol.callouts { margin: 0; padding-left: 0; list-style: none; columns: 2; column-gap: 6mm; }
ol.callouts li { margin-bottom: 1.6mm; display: flex; gap: 2mm; break-inside: avoid; }
ol.callouts b { display: inline-grid; place-items: center; width: 4.6mm; height: 4.6mm; border-radius: 50%; background: #b23a1e; color: #fff; font-size: 7pt; flex: none; }
ul { margin: 0; padding-left: 4mm; } li { margin-bottom: 1mm; }
.cover { display: grid; grid-template-columns: 1.15fr 1fr; gap: 9mm; }
.kv td:first-child { width: 38%; font: 600 8pt 'Barlow', sans-serif; letter-spacing: .08em; text-transform: uppercase; background: #f6f6f6; }
.note { font-size: 7.6pt; color: #444; margin-top: 2.5mm; line-height: 1.45; }
.legend { display: flex; gap: 3mm; align-items: center; flex-wrap: wrap; margin-top: 3mm; font-size: 7.6pt; }
.foot { position: absolute; left: 13mm; right: 13mm; bottom: 5mm; display: flex; justify-content: space-between; font-size: 6.8pt; color: #777; }
.sign td { height: 11mm; }
.steps li { margin-bottom: 1.8mm; }
"""


def esc(s):
    return html.escape(str(s))


def tag(status):
    return f'<span class="tag {status}">{status}</span>'


def logo_svg():
    src = (ROOT / "src" / "components" / "logoPath.js").read_text()
    vb = re.search(r'LOGO_VIEWBOX = "([^"]+)"', src).group(1)
    d = re.search(r'LOGO_PATH =\s*"([^"]+)"', src).group(1)
    return f'<svg viewBox="{vb}"><path d="{d}" fill="#111" fill-rule="evenodd"/></svg>'


def crop_views(style):
    """Save the front and back of the black flat sheet; return {view: (path, box)}."""
    from PIL import Image

    BUILD.mkdir(parents=True, exist_ok=True)
    sheet = Image.open(art_flats.FLATS / f"{style['slug']}-black.png").convert("RGB")
    out = {}
    for view, box in art_flats.PRODUCTS[style["slug"]]["boxes"].items():
        path = BUILD / f"{style['slug']}-{view}.png"
        sheet.crop(box).save(path)
        out[view] = (path, box)
    return out


def overlay(view, box, block, callouts=True, poms=True, start=1):
    """SVG drawn in sheet coordinates over a cropped view."""
    l, t, r, b = box
    k = (r - l) / 840  # marker scale: sized for the 840 px hoodie view
    parts = [f'<svg class="ov" viewBox="{l} {t} {r - l} {b - t}" preserveAspectRatio="xMidYMid meet">',
             '<defs><marker id="ar" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="9" markerHeight="9" orient="auto-start-reverse">'
             '<path d="M0,1 L10,5 L0,9 z" fill="#1f5fbf"/></marker></defs>']
    if poms:
        for code, x1, y1, x2, y2 in POM_LINES[block].get(view, []):
            parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#1f5fbf" stroke-width="{4.5 * k:.1f}" '
                         f'marker-start="url(#ar)" marker-end="url(#ar)"/>')
            f = LABEL_AT.get((block, code), 0.5)
            mx, my = x1 + (x2 - x1) * f, y1 + (y2 - y1) * f
            parts.append(f'<circle cx="{mx}" cy="{my}" r="{24 * k:.1f}" fill="#1f5fbf" stroke="#fff" stroke-width="{3 * k:.1f}"/>'
                         f'<text x="{mx}" y="{my + 10 * k:.1f}" text-anchor="middle" font-size="{29 * k:.1f}" font-family="Barlow" '
                         f'font-weight="600" fill="#fff">{code}</text>')
    n = start
    if callouts:
        for x, y, _ in CALLOUTS[block].get(view, []):
            parts.append(f'<circle cx="{x}" cy="{y}" r="{17 * k:.1f}" fill="#b23a1e" stroke="#fff" stroke-width="{3 * k:.1f}"/>'
                         f'<text x="{x}" y="{y + 7 * k:.1f}" text-anchor="middle" font-size="{20 * k:.1f}" font-family="Barlow" '
                         f'font-weight="600" fill="#fff">{n}</text>')
            n += 1
    parts.append("</svg>")
    return "".join(parts)


def flats_block(views, block, callouts=True, poms=False, height="120mm"):
    cells = []
    n = 1
    for view in ("front", "back"):
        path, box = views[view]
        cells.append(f'<div class="flat"><div class="fimg"><img src="file://{path}">{overlay(view, box, block, callouts, poms, n)}</div>'
                     f'<div class="cap">{view}</div></div>')
        n += len(CALLOUTS[block].get(view, []))
    return f'<div class="flats" style="--fh:{height}">{"".join(cells)}</div>'


def page(style, title, body, n, total):
    return f"""<section class="page">
<header class="bar"><div class="l">{logo_svg()}<h1>{esc(title)}</h1></div>
<div class="meta">{esc(style['code'])} · {esc(style['name'])}<br>Drop 01 · {esc(style['colour'])} · Sample size {spec.SAMPLE_SIZE} · {spec.VERSION} · {spec.DATE}</div></header>
{body}
<div class="foot"><span>FTD — Forsaken To Decay · Confidential: for sampling only</span><span>Page {n} / {total}</span></div>
</section>"""


def build(style):
    block = style["block"]
    views = crop_views(style)
    pom = spec.HOODIE_POM if block == "hoodie" else spec.PANTS_POM
    features = spec.HOODIE_FEATURES if block == "hoodie" else spec.PANTS_FEATURES
    bom = spec.HOODIE_BOM if block == "hoodie" else spec.PANTS_BOM
    construction = spec.HOODIE_CONSTRUCTION if block == "hoodie" else spec.PANTS_CONSTRUCTION
    shared = ("Same pattern as FTD-D01-HD01 / HD02 (one hoodie block, two print versions)."
              if block == "hoodie" else "Fabric matched to the Drop 01 zip hoodies.")
    pages = []

    # 1 cover
    rows = [("Style code", style["code"]), ("Style name", style["name"]), ("Collection", "Drop 01"),
            ("Colour", style["colour"]), ("Sample type", "First (proto / fit) sample"),
            ("Sample size", spec.SAMPLE_SIZE), ("Size range", " · ".join(spec.SIZES)),
            ("Quantity", "1 sample, plus a print strike-off on the sample fabric"),
            ("Brand contact", spec.BRAND["contact"] or "—"), ("Version / date", f"{spec.VERSION} · {spec.DATE}")]
    kv = "".join(f"<tr><td>{esc(k)}</td><td>{esc(v)}</td></tr>" for k, v in rows)
    feats = "".join(f"<li>{esc(f)}</li>" for f in features)
    pages.append(("Sample request", f"""<div class="cover"><div>
<div class="flats" style="gap:3mm">{''.join(f'<div class="flat"><img src="file://{views[v][0]}"></div>' for v in ('front','back'))}</div>
<p class="note" style="font-size:8.4pt;color:#111">{esc(style['summary'])}</p>
<h3>Key features</h3><ul>{feats}</ul></div>
<div><table class="kv">{kv}</table>
<h3>Important: print before sewing</h3>
<p class="note" style="color:#111;font-size:8.2pt">Please screen print the panels listed on the "Cut panels" page while they are
<b>cut but not yet sewn</b>, then sew the sample. Please send a photo of the strike-off for approval before printing the panels.
{esc(shared)}</p>
<div class="legend">Value status: {tag('CONFIRMED')} decided {tag('PROPOSED')} starting point, please advise {tag('TBC')} answer needed</div>
</div></div>"""))

    # 2 flats + callouts
    items = []
    for view in ("front", "back"):
        items += [c[2] for c in CALLOUTS[block].get(view, [])]
    lis = "".join(f"<li><b>{i + 1}</b><span>{esc(t)}</span></li>" for i, t in enumerate(items))
    pages.append(("Flats & features", flats_block(views, block, True, False, "112mm") + f'<h3>Callouts</h3><ol class="callouts">{lis}</ol>'))

    # 3 points of measure: big flats, compact key; full method is in the chart
    key = "".join(f"<li><b>{c}</b>&nbsp; {esc(n)}</li>" for c, n, *_ in pom)
    pages.append(("Points of measure", flats_block(views, block, False, True, "122mm") +
                  f'''<p class="note">Blue lines show the main points of measure; every point, with how to measure it, is in the
measurement chart. Garment laid flat, unstretched unless noted.</p>
<ul style="columns:4;column-gap:6mm;list-style:none;padding:0;margin-top:2mm;font-size:7.8pt">{key}</ul>'''))

    # 4 measurement chart
    head = "".join(f"<th class='num{' sample' if s == spec.SAMPLE_SIZE else ''}'>{s}</th>" for s in spec.SIZES)
    mid = spec.SIZES.index(spec.SAMPLE_SIZE)

    def fmt(v):
        return f"{v:g}"

    body_rows = []
    for code, name, how, m, grade, tol in pom:
        cells = "".join(f"<td class='num{' sample' if i == mid else ''}'>{fmt(m + (i - mid) * grade)}</td>" for i in range(len(spec.SIZES)))
        body_rows.append(f"<tr><td class='num'><b>{code}</b></td><td>{esc(name)}</td><td>{esc(how)}</td>{cells}<td class='num'>±{fmt(tol)}</td><td class='num'>{fmt(grade)}</td></tr>")
    pages.append(("Measurement chart", f"""<table style="font-size:7.6pt"><tr><th class="num">Code</th><th>Point of measure</th><th>How to measure</th>{head}<th class="num">Tol.</th><th class="num">Grade</th></tr>
{''.join(body_rows)}</table>
<div class="legend">All values {tag('PROPOSED')} Centimetres, laid flat. Sample size {spec.SAMPLE_SIZE} highlighted.
Proportions follow the flats; please check the pattern against them and advise on any points that won't work.</div>"""))

    # 5 BOM
    bom_rows = "".join(f"<tr><td><b>{esc(c)}</b></td><td>{esc(s)}</td><td>{esc(p)}</td><td>{esc(col)}</td><td class='num'>{tag(st)}</td></tr>"
                       for c, s, p, col, st in bom)
    pages.append(("Materials & trims", f"""<table><tr><th style="width:15%">Component</th><th>Specification</th><th style="width:19%">Placement</th>
<th style="width:13%">Colour</th><th class="num" style="width:10%">Status</th></tr>{bom_rows}</table>
<p class="note">Please send fabric and rib swatches with your quote if possible, so FTD can test print on them before sampling.</p>"""))

    # 6 construction
    con = "".join(f"<tr><td style='width:17%'><b>{esc(a)}</b></td><td>{esc(b)}</td></tr>" for a, b in construction)
    pages.append(("Construction", f"""<table><tr><th>Area</th><th>Details {tag('PROPOSED')}</th></tr>{con}</table>
<p class="note">Stitch details follow the dashed topstitch lines on the flats. Where a different method is standard in your factory
for the same look, please suggest it.</p>"""))

    # 7 artwork & placement
    pr = "".join(f"<tr><td><b>{esc(n)}</b></td><td>{esc(sz)}</td><td>{esc(pl)}</td><td>{esc(pn)}</td></tr>" for n, sz, pl, pn in style["prints"])
    pages.append(("Artwork & print placement", flats_block(views, block, False, False, "74mm") + f"""
<table style="margin-top:3mm"><tr><th style="width:17%">Print</th><th style="width:17%">Approx. size cm (w × h)</th><th>Placement</th>
<th style="width:17%">Panels printed</th></tr>{pr}</table>
<p class="note"><b>Method:</b> {esc(spec.PRINT_METHOD)}</p>
<p class="note">Sizes are taken from the flats and are approximate for the first sample. FTD will make 1:1 placement guides on the
pattern pieces once the pattern is shared, so prints that cross seams line up.</p>"""))

    # 7b artwork files
    cards = []
    for code in style["artwork"]:
        art = spec.ARTWORK[code]
        img = OUT / "artwork" / f"{art['file']}_{art['size'].split(' ')[0]}cm_300dpi.png"
        note = f"<p class='note'>{esc(art['note'])}</p>" if art.get("note") else ""
        cards.append(f"""<div style="flex:1;border:.25mm solid #999;padding:4mm;display:flex;flex-direction:column;gap:2mm">
<div style="height:78mm;display:grid;place-items:center;background:#f4f4f4"><img src="file://{img}" style="max-width:100%;max-height:74mm"></div>
<h3 style="margin:1mm 0 0">{code} · {esc(art['name'])} {tag(art['status'])}</h3>
<table class="kv"><tr><td>Print size (w × h)</td><td>{esc(art['size'])} cm</td></tr>
<tr><td>Used on</td><td>{esc(art['used'])}</td></tr>
<tr><td>Files</td><td>{esc(art['file'])}.svg (vector)<br>{esc(img.name)}</td></tr></table>{note}</div>""")
    pages.append(("Artwork files", f"""<div style="display:flex;gap:6mm">{''.join(cards)}</div>
<p class="note">One colour: white ink on black. Files are supplied as vector SVG plus a 300 dpi PNG film positive at print size
(black = ink). Fine distressed detail in ART-03 is part of the design; please flag any lines too fine to hold on your mesh.
Drop 01 uses three screens in total: ART-01 and ART-03 are shared between styles.</p>"""))

    # 8 cut panels workflow
    pp = "".join(f"<li>{esc(p)}</li>" for p in style["printed_panels"])
    fp = "".join(f"<li>{esc(p)}</li>" for p in style["factory_panels"])
    pages.append(("Cut panels: print before sewing", f"""<div class="cols"><div>
<h2>Why</h2><p style="line-height:1.55">{esc(style['why'])} The panels are printed flat, then the garment is sewn.</p>
<h3>Panels printed before sewing</h3><ul>{pp}</ul>
<h3>Panels not printed</h3><ul>{fp}</ul></div>
<div><h2>Steps</h2><ol class="steps" style="padding-left:5mm">
<li>Make the sample pattern and mark the print positions on the pattern pieces from the artwork page.</li>
<li>Print a <b>strike-off</b> of each artwork on the sample fabric; send photos (and the swatch with the sample) for approval.</li>
<li>Once approved, cut the sample from pre-shrunk fabric and print the panels flat, matching prints across seams and the zip.</li>
<li>Cure and wash-test one printed offcut: no cracking or fading after 3 washes at 30°C.</li>
<li>Sew the sample to this pack and send it to FTD for fit and print approval.</li></ol>
<p class="note">If printing before sewing isn't possible for any panel, please tell us before quoting.</p></div></div>"""))

    # 9 labels, questions, approvals
    q = "".join(f"<li>{esc(x)}</li>" for x in spec.QUESTIONS)
    ln = "".join(f"<li>{esc(x)}</li>" for x in spec.LABEL_NOTES)
    pages.append(("Labels, questions & approval", f"""<div class="cols"><div>
<h2>Questions for the manufacturer</h2><ol style="padding-left:5mm">{q}</ol>
<h3>Labels</h3><ul>{ln}</ul></div>
<div><h2>Revision log</h2><table><tr><th>Version</th><th>Date</th><th>Change</th></tr>
<tr><td>{spec.VERSION}</td><td>{spec.DATE}</td><td>First issue for sample quote</td></tr><tr><td>&nbsp;</td><td></td><td></td></tr><tr><td>&nbsp;</td><td></td><td></td></tr></table>
<h3>Sample approval</h3><table class="sign"><tr><th>Stage</th><th>Date</th><th>Comments</th><th>Approved by</th></tr>
<tr><td>Fit sample</td><td></td><td></td><td></td></tr><tr><td>Print test</td><td></td><td></td><td></td></tr>
<tr><td>Pre-production</td><td></td><td></td><td></td></tr></table></div></div>"""))

    total = len(pages)
    body = "".join(page(style, t, b, i + 1, total) for i, (t, b) in enumerate(pages))
    fonts = ROOT / "node_modules" / "@fontsource"
    css = (f"@font-face{{font-family:Barlow;font-weight:600;src:url(file://{fonts}/barlow-condensed/files/barlow-condensed-latin-600-normal.woff2)}}"
           f"@font-face{{font-family:Plex;src:url(file://{fonts}/ibm-plex-mono/files/ibm-plex-mono-latin-400-normal.woff2)}}"
           f"@font-face{{font-family:Plex;font-weight:600;src:url(file://{fonts}/ibm-plex-mono/files/ibm-plex-mono-latin-500-normal.woff2)}}" + CSS)
    doc = f"<!doctype html><html><head><meta charset='utf-8'><style>{css}</style></head><body>{body}</body></html>"
    BUILD.mkdir(parents=True, exist_ok=True)
    html_path = BUILD / f"{style['code']}.html"
    html_path.write_text(doc)
    pdf = OUT / f"{style['code']}_{style['name'].replace(' ', '-')}.pdf"
    subprocess.run(["node", str(ROOT / "scripts" / "html-to-pdf.mjs"), str(html_path), str(pdf)], check=True, cwd=ROOT)
    print("  wrote", pdf.relative_to(ROOT))
    return pdf


if __name__ == "__main__":
    for s in spec.STYLES:
        build(s)
