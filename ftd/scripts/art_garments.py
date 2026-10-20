"""Garment flats for Drop 01 (pants, tees), drawn as shaded technical illustrations.

The zip hoodie uses the supplied flats (art_flats.py); hoodie_back() remains as
the silhouette for the "relic" campaign panel.

Each garment is rendered as two layers: the washed-black fabric (greyscale shading)
and the bone-white print (a mask). They are composited in build_art.py with knit
grain on the fabric and a cracked, worn finish on the print.
"""

import math
import re
from pathlib import Path

from art_lib import mirror_x

LOGO_FILE = Path(__file__).resolve().parent.parent / "src" / "components" / "logoPath.js"
_src = LOGO_FILE.read_text()
LOGO_D = re.search(r'LOGO_PATH =\s*"([^"]+)"', _src).group(1)
LOGO_VB = (450, 193, 2024, 982)


def g(v):
    v = max(0, min(255, int(255 * v)))
    return f"rgb({v},{v},{v})"


def logo(x, y, w, fill="#fff"):
    """FTD wordmark placed with its top-left at x,y and width w."""
    s = w / LOGO_VB[2]
    return (f"<g transform='translate({x},{y}) scale({s:.5f}) translate({-LOGO_VB[0]},{-LOGO_VB[1]})'>"
            f"<path d='{LOGO_D}' fill='{fill}' fill-rule='evenodd'/></g>")


def bone(x1, y1, x2, y2, t, fill="#fff"):
    """A femur: shaft with paired condyles at each end."""
    ang = math.atan2(y2 - y1, x2 - x1)
    nx, ny = -math.sin(ang), math.cos(ang)
    ux, uy = math.cos(ang), math.sin(ang)
    out = [f"<line x1='{x1}' y1='{y1}' x2='{x2}' y2='{y2}' stroke='{fill}' stroke-width='{t}' stroke-linecap='round'/>"]
    for (px, py, d) in ((x1, y1, 1), (x2, y2, -1)):
        for side in (-1, 1):
            cx = px + nx * side * t * 0.62 - ux * d * t * 0.15
            cy = py + ny * side * t * 0.62 - uy * d * t * 0.15
            out.append(f"<circle cx='{cx:.1f}' cy='{cy:.1f}' r='{t * 0.72:.1f}' fill='{fill}'/>")
    return "".join(out)


def crossbone(cx, cy, s, rot=0, fill="#fff", gap="#000"):
    """The FTD crossbone: a flared gothic cross over crossed femurs with thorned scrollwork.

    Drawn in a 200 x 320 box centred on cx,cy, scaled by s. `gap` cuts the
    separating lines so the motif keeps its engraved look when printed.
    """
    p = []
    # crossed femurs behind the cross
    p.append(bone(28, 70, 172, 262, 15, fill))
    p.append(bone(172, 70, 28, 262, 15, fill))
    # cross with flared, notched terminals
    cross = ("M92,8 L108,8 L118,0 L114,30 L108,40 L108,92 L156,92 L166,86 L196,82 L188,100 L196,118 "
             "L166,114 L156,108 L108,108 L108,272 L118,300 L104,296 L100,320 L96,296 L82,300 L92,272 "
             "L92,108 L44,108 L34,114 L4,118 L12,100 L4,82 L34,86 L44,92 L92,92 L92,40 L86,30 L82,0 Z")
    p.append(f"<path d='{cross}' fill='{gap}' stroke='{gap}' stroke-width='10' stroke-linejoin='round'/>")
    p.append(f"<path d='{cross}' fill='{fill}'/>")
    # ring at the crossing
    p.append(f"<circle cx='100' cy='100' r='30' fill='none' stroke='{gap}' stroke-width='13'/>")
    p.append(f"<circle cx='100' cy='100' r='30' fill='none' stroke='{fill}' stroke-width='6'/>")
    p.append(f"<path d='M100,82 L106,100 L100,118 L94,100 Z' fill='{gap}'/>")
    # scrollwork with thorns, mirrored
    scroll = "M92,150 C60,150 46,170 52,190 C58,208 80,206 80,192 C80,182 70,180 66,186"
    for d in (scroll, mirror_x(scroll, 100)):
        p.append(f"<path d='{d}' fill='none' stroke='{gap}' stroke-width='11' stroke-linecap='round'/>")
        p.append(f"<path d='{d}' fill='none' stroke='{fill}' stroke-width='5' stroke-linecap='round'/>")
    for ty in (140, 186, 232):
        for side in (-1, 1):
            x0 = 100 + side * 8
            p.append(f"<path d='M{x0},{ty} L{x0 + side * 18},{ty - 6} L{x0},{ty + 6} Z' fill='{fill}'/>")
    inner = "".join(p)
    return (f"<g transform='translate({cx},{cy}) rotate({rot}) scale({s}) translate(-100,-160)'>{inner}</g>")


# --------------------------------------------------------------------- hoodie

HOOD_DEFS = f"""
<linearGradient id='bodyShade' x1='0' y1='0' x2='1' y2='0'>
  <stop offset='0' stop-color='{g(0.22)}'/><stop offset='0.18' stop-color='{g(0.36)}'/>
  <stop offset='0.5' stop-color='{g(0.42)}'/><stop offset='0.82' stop-color='{g(0.34)}'/>
  <stop offset='1' stop-color='{g(0.2)}'/>
</linearGradient>
<linearGradient id='sleeveShade' x1='0' y1='0' x2='1' y2='0'>
  <stop offset='0' stop-color='{g(0.2)}'/><stop offset='0.45' stop-color='{g(0.38)}'/>
  <stop offset='1' stop-color='{g(0.26)}'/>
</linearGradient>
<linearGradient id='hoodIn' x1='0' y1='0' x2='0' y2='1'>
  <stop offset='0' stop-color='{g(0.08)}'/><stop offset='1' stop-color='{g(0.16)}'/>
</linearGradient>
<linearGradient id='rib' x1='0' y1='0' x2='0' y2='1'>
  <stop offset='0' stop-color='{g(0.26)}'/><stop offset='1' stop-color='{g(0.36)}'/>
</linearGradient>
<filter id='fold' x='-30%' y='-30%' width='160%' height='160%'><feGaussianBlur stdDeviation='9'/></filter>
<filter id='fold2' x='-30%' y='-30%' width='160%' height='160%'><feGaussianBlur stdDeviation='4'/></filter>
<pattern id='ribPat' width='9' height='10' patternUnits='userSpaceOnUse'>
  <rect width='9' height='10' fill='url(#rib)'/><rect width='2.4' height='10' fill='{g(0.16)}'/>
</pattern>
"""

# outline pieces (front view, 1000 x 1100)
SLEEVE_L = ("M300,300 C255,312 218,340 196,392 C170,470 150,600 132,720 C122,780 112,820 108,850 "
            "L222,868 C226,830 232,790 240,742 C252,660 268,560 290,470 Z")
CUFF_L = "M104,846 C112,852 214,868 224,862 L218,936 C196,948 120,940 100,926 Z"
BODY = ("M300,300 C360,280 410,262 440,250 C470,275 530,275 560,250 C590,262 640,280 700,300 "
        "C722,380 728,470 724,560 C722,680 730,780 736,858 L264,858 C270,780 278,680 276,560 "
        "C272,470 278,380 300,300 Z")
HEM = "M262,852 L738,852 L742,930 C600,946 400,946 258,930 Z"


def hoodie_back():
    fab, prn = [], []
    sl, cl = SLEEVE_L, CUFF_L
    sr, cr = mirror_x(sl, 500), mirror_x(cl, 500)
    edge = f"stroke='{g(0.05)}' stroke-width='5' stroke-linejoin='round'"
    for s in (sl, sr):
        fab.append(f"<path d='{s}' fill='url(#sleeveShade)' {edge}/>")
    for c in (cl, cr):
        fab.append(f"<path d='{c}' fill='url(#ribPat)' {edge}/>")
    back = BODY.replace("C470,275 530,275 560,250", "C470,262 530,262 560,250")
    fab.append(f"<path d='{back}' fill='url(#bodyShade)' {edge}/>")
    fab.append(f"<path d='{HEM}' fill='url(#ribPat)' {edge}/>")
    # hood lying flat down the back
    hood = ("M392,262 C372,210 380,150 420,128 C470,104 530,104 580,128 C620,150 628,210 608,262 "
            "C600,340 560,400 500,418 C440,400 400,340 392,262 Z")
    fab.append(f"<path d='{hood}' fill='{g(0.34)}' {edge}/>")
    fab.append(f"<path d='M500,112 L500,416' stroke='{g(0.12)}' stroke-width='4'/>")
    fab.append(f"<path d='M500,114 L500,414' stroke='{g(0.5)}' stroke-width='1.6' stroke-dasharray='5 5' transform='translate(7,0)'/>")
    fab.append(f"<path d='M404,330 C440,400 560,400 596,330' fill='none' stroke='{g(0.14)}' stroke-width='22' filter='url(#fold)'/>")
    folds = [
        ("M330,460 C350,560 344,680 356,820", 0.2, 26), ("M670,460 C650,560 656,680 644,820", 0.2, 26),
        ("M220,420 C200,520 186,640 172,790", 0.48, 18), ("M780,420 C800,520 814,640 828,790", 0.48, 18),
        ("M300,820 C380,836 430,840 470,842", 0.24, 18), ("M700,820 C620,836 570,840 530,842", 0.24, 18),
    ]
    for d, tone, wdt in folds:
        fab.append(f"<path d='{d}' fill='none' stroke='{g(tone)}' stroke-width='{wdt}' stroke-linecap='round' filter='url(#fold)'/>")
    seam = f"fill='none' stroke='{g(0.5)}' stroke-width='1.8' stroke-dasharray='5 5'"
    fab.append(f"<path d='M300,306 C282,380 276,470 290,476' {seam}/><path d='M700,306 C718,380 724,470 710,476' {seam}/>")
    fab.append(f"<path d='M268,846 L732,846' {seam}/>")
    # back print: large crossbone, wordmark at the neck
    prn.append(crossbone(500, 640, 1.18))
    prn.append(crossbone(224, 610, 0.88, rot=7.5))
    prn.append(crossbone(776, 610, 0.88, rot=-7.5))
    prn.append(f"<path d='{hood}' fill='#000'/>")
    prn.append(logo(452, 300, 96))
    fab_mask = f"<path d='{back}' fill='#fff'/><path d='{sl}' fill='#fff'/><path d='{sr}' fill='#fff'/><path d='{hood}' fill='#fff'/>"
    return 1000, 1100, HOOD_DEFS, "".join(fab), "".join(prn), fab_mask


# --------------------------------------------------------------------- pants

def pants():
    fab, prn = [], []
    edge = f"stroke='{g(0.05)}' stroke-width='5' stroke-linejoin='round'"
    leg = ("M300,190 L500,190 L500,300 C492,420 478,560 470,700 C464,800 462,880 466,930 "
           "L270,940 C262,860 258,760 262,640 C266,480 280,320 300,190 Z")
    legr = mirror_x(leg, 500)
    band = "M296,120 L704,120 L708,196 L292,196 Z"
    cuff = "M268,930 C330,944 410,944 468,926 L472,990 C410,1004 330,1004 266,992 Z"
    fab.append(f"<path d='{leg}' fill='url(#sleeveShade)' {edge}/><path d='{legr}' fill='url(#sleeveShade)' {edge}/>")
    fab.append(f"<path d='{cuff}' fill='url(#ribPat)' {edge}/><path d='{mirror_x(cuff, 500)}' fill='url(#ribPat)' {edge}/>")
    fab.append(f"<path d='{band}' fill='url(#ribPat)' {edge}/>")
    for d, tone, wdt in [
        ("M330,300 C320,500 310,700 300,900", 0.5, 18), ("M670,300 C680,500 690,700 700,900", 0.5, 18),
        ("M440,320 C450,500 440,700 436,900", 0.16, 22), ("M560,320 C550,500 560,700 564,900", 0.16, 22),
        ("M290,860 C340,890 400,890 460,870", 0.18, 16), ("M710,860 C660,890 600,890 540,870", 0.18, 16),
        ("M300,620 C350,640 400,640 460,610", 0.2, 12), ("M700,620 C650,640 600,640 540,610", 0.2, 12),
    ]:
        fab.append(f"<path d='{d}' fill='none' stroke='{g(tone)}' stroke-width='{wdt}' stroke-linecap='round' filter='url(#fold)'/>")
    seam = f"fill='none' stroke='{g(0.5)}' stroke-width='1.8' stroke-dasharray='5 5'"
    fab.append(f"<path d='M500,200 L500,300' {seam}/><path d='M330,206 C360,240 380,260 400,300' {seam}/>"
               f"<path d='M670,206 C640,240 620,260 600,300' {seam}/>")
    for x, c in ((480, -8), (520, 8)):
        fab.append(f"<path d='M{x},150 C{x + c},210 {x - c},250 {x + c},300' fill='none' stroke='{g(0.4)}' stroke-width='7' stroke-linecap='round'/>")
    for i, (y, s) in enumerate(((330, 0.62), (560, 0.72), (790, 0.62))):
        prn.append(crossbone(372 - i * 4, y, s, rot=-3))
        prn.append(crossbone(628 + i * 4, y, s, rot=3))
    fab_mask = f"<path d='{leg}' fill='#fff'/><path d='{legr}' fill='#fff'/>"
    return 1000, 1100, HOOD_DEFS, "".join(fab), "".join(prn), fab_mask


# --------------------------------------------------------------------- tees

TEE = ("M300,190 C350,176 410,162 440,150 C470,180 530,180 560,150 C590,162 650,176 700,190 "
       "L858,268 L800,452 L732,428 C732,580 736,740 742,880 L258,880 C264,740 268,580 268,428 "
       "L200,452 L142,268 Z")
COLLAR = "M440,150 C470,180 530,180 560,150 L574,160 C540,208 460,208 426,160 Z"


def _tee_base(fab):
    edge = f"stroke='{g(0.05)}' stroke-width='5' stroke-linejoin='round'"
    fab.append(f"<path d='{TEE}' fill='url(#bodyShade)' {edge}/>")
    fab.append(f"<path d='{COLLAR}' fill='url(#ribPat)' {edge}/>")
    for d, tone, wdt in [
        ("M330,440 C350,560 340,700 352,880", 0.2, 26), ("M670,440 C650,560 662,700 646,880", 0.2, 26),
        ("M290,210 C300,300 284,360 270,428", 0.18, 18), ("M710,210 C700,300 716,360 730,428", 0.18, 18),
        ("M210,300 C240,320 270,340 300,340", 0.5, 12), ("M790,300 C760,320 730,340 700,340", 0.5, 12),
    ]:
        fab.append(f"<path d='{d}' fill='none' stroke='{g(tone)}' stroke-width='{wdt}' stroke-linecap='round' filter='url(#fold)'/>")
    seam = f"fill='none' stroke='{g(0.5)}' stroke-width='1.8' stroke-dasharray='5 5'"
    fab.append(f"<path d='M290,196 C296,300 280,380 270,428' {seam}/><path d='M710,196 C704,300 720,380 730,428' {seam}/>"
               f"<path d='M262,862 L738,862' {seam}/>")


def tee_heaven():
    fab, prn = [], []
    _tee_base(fab)
    # halo sunburst behind a blackletter HEAVEN
    for i in range(28):
        a = math.radians(-180 + i * (360 / 28))
        r0, r1 = 74, 150 if i % 2 == 0 else 112
        prn.append(f"<line x1='{500 + math.cos(a) * r0:.0f}' y1='{470 + math.sin(a) * r0:.0f}' "
                   f"x2='{500 + math.cos(a) * r1:.0f}' y2='{470 + math.sin(a) * r1:.0f}' stroke='#fff' stroke-width='{6 if i % 2 == 0 else 4}'/>")
    prn.append("<circle cx='500' cy='470' r='60' fill='none' stroke='#fff' stroke-width='5'/>")
    prn.append(crossbone(500, 470, 0.3))
    prn.append("<text x='500' y='330' text-anchor='middle' font-family='Pirata One' font-size='132' fill='#fff' "
               "letter-spacing='2'>Heaven</text>")
    prn.append("<text x='500' y='660' text-anchor='middle' font-family='IBM Plex Mono' font-size='17' fill='#fff' "
               "letter-spacing='6'>YOU CAN'T RUN FROM IT</text>")
    prn.append(logo(470, 690, 60))
    return 1000, 1100, HOOD_DEFS, "".join(fab), "".join(prn), f"<path d='{TEE}' fill='#fff'/>"


def tee_decay():
    fab, prn = [], []
    _tee_base(fab)
    # thorn-wrapped sword running the full length
    prn.append("<path d='M494,300 L506,300 L510,820 L500,860 L490,820 Z' fill='#fff'/>")
    prn.append("<path d='M420,330 L580,330 L592,316 L590,344 L580,350 L420,350 L410,344 L408,316 Z' fill='#fff'/>")
    prn.append("<circle cx='500' cy='280' r='18' fill='#fff'/><rect x='492' y='296' width='16' height='34' fill='#fff'/>")
    vine = "M520,380 C470,410 470,440 520,470 C570,500 570,530 520,560 C470,590 470,620 520,650 C560,676 560,700 512,724"
    prn.append(f"<path d='{vine}' fill='none' stroke='#000' stroke-width='14'/><path d='{vine}' fill='none' stroke='#fff' stroke-width='5'/>")
    for y in range(392, 724, 26):
        side = 1 if (y // 26) % 2 else -1
        prn.append(f"<path d='M{500 + side * 40},{y} L{500 + side * 62},{y - 10} L{500 + side * 44},{y + 8} Z' fill='#fff'/>")
    prn.append(logo(444, 200, 112))
    prn.append("<text x='500' y='900' text-anchor='middle' font-family='IBM Plex Mono' font-size='16' fill='#fff' "
               "letter-spacing='9'>NOTHING LASTS</text>")
    return 1000, 1100, HOOD_DEFS, "".join(fab), "".join(prn), f"<path d='{TEE}' fill='#fff'/>"
