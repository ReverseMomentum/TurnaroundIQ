"""Orange-ink scenes: the ruined cathedral and the three Drop 01 campaign panels."""

import math
import random

import art_garments as ag
import art_hero
from art_lib import mirror_x, rays


def g(v):
    v = max(0, min(255, int(255 * v)))
    return f"rgb({v},{v},{v})"


def lancet(x, ys, w, rect_h, fill, extra=""):
    """Pointed (equilateral) gothic arch opening, springing at ys, standing on ys + rect_h."""
    return (f"<path d='M{x},{ys + rect_h} L{x},{ys} A{w},{w} 0 0 1 {x + w / 2},{ys - w * 0.866:.1f} "
            f"A{w},{w} 0 0 1 {x + w},{ys} L{x + w},{ys + rect_h} Z' fill='{fill}' {extra}/>")


def archivolts(x, ys, w, n, step, tone):
    out = []
    for i in range(1, n + 1):
        xx, ww = x - i * step, w + 2 * i * step
        out.append(f"<path d='M{xx},{ys + 400} L{xx},{ys} A{ww},{ww} 0 0 1 {xx + ww / 2},{ys - ww * 0.866:.1f} "
                   f"A{ww},{ww} 0 0 1 {xx + ww},{ys} L{xx + ww},{ys + 400}' fill='none' "
                   f"stroke='{g(tone if i % 2 else tone * 0.45)}' stroke-width='{step * 0.8:.0f}'/>")
    return "".join(out)


def courses(x0, x1, y0, y1, gap, tone, rng):
    out = []
    y = y0
    while y < y1:
        out.append(f"<line x1='{x0}' y1='{y}' x2='{x1}' y2='{y + rng.uniform(-1, 1):.1f}' stroke='{g(tone)}' stroke-width='2'/>")
        y += gap
    return "".join(out)


def pinnacle(x, y, h, w, tone):
    return (f"<path d='M{x - w / 2},{y} L{x - w / 2},{y - h * 0.45} L{x},{y - h} L{x + w / 2},{y - h * 0.45} "
            f"L{x + w / 2},{y} Z' fill='{g(tone)}'/>"
            + "".join(f"<path d='M{x - w / 2 + 1},{y - h * (0.5 + k * 0.12):.0f} l-7,-4 l7,-2 Z' fill='{g(tone)}'/>"
                      f"<path d='M{x + w / 2 - 1},{y - h * (0.5 + k * 0.12):.0f} l7,-4 l-7,-2 Z' fill='{g(tone)}'/>"
                      for k in range(3)))


CATH_DEFS = f"""
<linearGradient id='stone' x1='0' y1='0' x2='0' y2='1'>
  <stop offset='0' stop-color='{g(0.95)}'/><stop offset='1' stop-color='{g(0.62)}'/>
</linearGradient>
<linearGradient id='stoneSide' x1='0' y1='0' x2='1' y2='0'>
  <stop offset='0' stop-color='{g(0.42)}'/><stop offset='1' stop-color='{g(0.8)}'/>
</linearGradient>
<radialGradient id='glow' cx='0.5' cy='0.5' r='0.5'>
  <stop offset='0' stop-color='{g(0.55)}'/><stop offset='1' stop-color='#000'/>
</radialGradient>
<linearGradient id='fadeUp' x1='0' y1='0' x2='0' y2='1'>
  <stop offset='0' stop-color='#fff'/><stop offset='0.8' stop-color='#fff'/><stop offset='1' stop-color='{g(0.3)}'/>
</linearGradient>
<mask id='cathMask'><rect width='1600' height='760' fill='url(#fadeUp)'/></mask>
<filter id='blur6'><feGaussianBlur stdDeviation='6'/></filter>
"""


def cathedral():
    rng = random.Random(5)
    W, H = 1600, 760
    p = []
    # side aisles, ruined: broken top edges
    for side in (0, 1):
        wall = ("M120,700 L120,420 L160,404 L190,430 L230,380 L270,396 L300,350 L340,372 L380,330 L430,346 L430,700 Z")
        d = wall if side == 0 else mirror_x(wall, 800)
        p.append(f"<path d='{d}' fill='url(#stoneSide)'/>")
    for x in (150, 230, 310):
        for xx in (x, 1600 - x - 50):
            p.append(lancet(xx, 470, 50, 150, "#000"))
            p.append(f"<line x1='{xx + 25}' y1='{430}' x2='{xx + 25}' y2='{620}' stroke='{g(0.5)}' stroke-width='3'/>")
    # flying buttresses
    for side in (1, -1):
        bx = 800 - side * 370
        fb = f"M{bx},430 Q{bx - side * 90},380 {bx - side * 190},300 L{bx - side * 196},316 Q{bx - side * 100},404 {bx - side * 6},450 Z"
        p.append(f"<path d='{fb}' fill='{g(0.7)}'/>")
        p.append(pinnacle(bx + side * 6, 440, 150, 22, 0.85))
    # towers
    for side in (0, 1):
        x0 = 440 if side == 0 else 1000
        p.append(f"<rect x='{x0}' y='150' width='160' height='550' fill='url(#stone)'/>")
        p.append(courses(x0, x0 + 160, 170, 700, 22, 0.35, rng))
        for k, (y, h) in enumerate(((260, 120), (440, 130))):
            p.append(lancet(x0 + 38, y, 36, h, "#000"))
            p.append(lancet(x0 + 86, y, 36, h, "#000"))
        # buttress strips
        p.append(f"<rect x='{x0}' y='150' width='14' height='550' fill='{g(0.45)}'/>")
        p.append(f"<rect x='{x0 + 146}' y='150' width='14' height='550' fill='{g(0.45)}'/>")
        for px in (x0 + 7, x0 + 153):
            p.append(pinnacle(px, 150, 90, 18, 0.9))
    # left spire intact, right spire broken off
    p.append("<path d='M450,150 L520,-10 L590,150 Z' fill='url(#stoneSide)'/>")
    for k in range(7):
        y = 140 - k * 22
        hw = 70 * (y + 10) / 160
        p.append(f"<path d='M{520 - hw:.0f},{y} l-10,-6 l12,-2 Z' fill='{g(0.85)}'/><path d='M{520 + hw:.0f},{y} l10,-6 l-12,-2 Z' fill='{g(0.85)}'/>")
    p.append("<path d='M1010,150 L1040,96 L1056,110 L1070,72 L1084,104 L1100,84 L1150,150 Z' fill='url(#stoneSide)'/>")
    # central facade and gable
    p.append("<path d='M600,700 L600,230 L700,150 L760,96 L800,60 L826,92 L846,84 L870,128 L1000,230 L1000,700 Z' fill='url(#stone)'/>")
    p.append(courses(600, 1000, 250, 700, 26, 0.32, rng))
    # rose window
    p.append("<circle cx='800' cy='236' r='70' fill='#000'/><circle cx='800' cy='236' r='70' fill='none' stroke='#fff' stroke-width='8'/>")
    for k in range(12):
        a = math.radians(k * 30)
        p.append(f"<line x1='800' y1='236' x2='{800 + math.cos(a) * 66:.1f}' y2='{236 + math.sin(a) * 66:.1f}' stroke='{g(0.9)}' stroke-width='5'/>")
        p.append(f"<circle cx='{800 + math.cos(a + 0.26) * 46:.1f}' cy='{236 + math.sin(a + 0.26) * 46:.1f}' r='9' fill='none' stroke='{g(0.8)}' stroke-width='3'/>")
    p.append("<circle cx='800' cy='236' r='16' fill='#fff'/>")
    # great portal with archivolts and an ember glow inside
    p.append(archivolts(720, 470, 160, 6, 11, 0.9))
    p.append(lancet(720, 470, 160, 230, "#000"))
    p.append("<ellipse cx='800' cy='600' rx='70' ry='110' fill='url(#glow)' filter='url(#blur6)'/>")
    p.append("<path d='M790,700 L790,520 L810,520 L810,700 Z M760,560 L840,560 L840,578 L760,578 Z' fill='#000'/>")
    # blind arcade over the portal
    for k in range(6):
        p.append(lancet(632 + k * 58, 370, 28, 40, g(0.12)))
    # cracks
    for (x, y) in ((640, 300), (960, 420), (1030, 330), (470, 560)):
        pts = [(x, y)]
        for _ in range(6):
            x, y = x + rng.uniform(-14, 14), y + rng.uniform(10, 26)
            pts.append((x, y))
        p.append("<polyline points='" + " ".join(f"{a:.0f},{b:.0f}" for a, b in pts) + f"' fill='none' stroke='{g(0.05)}' stroke-width='3'/>")
    building = f"<g mask='url(#cathMask)'>{''.join(p)}</g>"
    # rubble field
    rub = []
    for _ in range(260):
        x = rng.uniform(0, W)
        y = rng.uniform(640, 760) - 60 * math.exp(-((x - 800) / 420) ** 2) * rng.random()
        r = rng.uniform(6, 30)
        pts = [(x + math.cos(a) * r * rng.uniform(0.5, 1.2), y + math.sin(a) * r * rng.uniform(0.4, 0.9))
               for a in sorted(rng.uniform(0, 6.28) for _ in range(6))]
        rub.append("<polygon points='" + " ".join(f"{a:.0f},{b:.0f}" for a, b in pts) +
                   f"' fill='{g(rng.uniform(0.35, 0.95))}' stroke='#000' stroke-width='3'/>")
    # fallen column drums
    for (x, y, r) in ((300, 690, 34), (1290, 700, 30), (1180, 676, 22)):
        rub.append(f"<ellipse cx='{x}' cy='{y}' rx='{r * 1.6}' ry='{r}' fill='{g(0.8)}' stroke='#000' stroke-width='4'/>"
                   f"<ellipse cx='{x + r * 1.2}' cy='{y}' rx='{r * 0.4}' ry='{r}' fill='{g(0.45)}'/>")
    return W, H, CATH_DEFS, building + "".join(rub)


# ------------------------------------------------------------ campaign panels

PANEL_DEFS = ag.HOOD_DEFS + art_hero.DEFS + f"""
<radialGradient id='spot' cx='0.5' cy='0.35' r='0.6'>
  <stop offset='0' stop-color='{g(0.2)}'/><stop offset='1' stop-color='#000'/>
</radialGradient>
<linearGradient id='floor' x1='0' y1='0' x2='0' y2='1'>
  <stop offset='0' stop-color='#000'/><stop offset='1' stop-color='{g(0.34)}'/>
</linearGradient>
<radialGradient id='faceShadow' cx='0.5' cy='0.42' r='0.55'>
  <stop offset='0' stop-color='#000' stop-opacity='0'/><stop offset='0.62' stop-color='#000' stop-opacity='0.35'/>
  <stop offset='1' stop-color='#000' stop-opacity='0.95'/>
</radialGradient>
"""


def campaign_hooded():
    """Figure in the zip hoodie, hood up, skull face half lost to shadow."""
    W, H = 900, 1200
    p = [f"<rect width='{W}' height='{H}' fill='url(#spot)'/>"]
    # rays behind the figure
    p.append(rays(450, 420, 230, [(-180 + k * 15, 200 + (k % 2) * 150, 2.0, 0.85) for k in range(13)]))
    # body: an inked silhouette of the hoodie, worn
    p.append("<path d='M150,1200 C150,960 190,800 300,740 C350,712 400,700 450,700 C500,700 550,712 600,740 "
             "C710,800 750,960 750,1200 Z' fill='rgb(150,150,150)'/>")
    p.append("<path d='M300,740 C260,800 240,950 236,1200 L170,1200 C170,980 200,820 300,740 Z' fill='rgb(60,60,60)'/>")
    p.append("<path d='M600,740 C640,800 660,950 664,1200 L730,1200 C730,980 700,820 600,740 Z' fill='rgb(60,60,60)'/>")
    # hood up
    p.append("<path d='M262,770 C236,600 240,410 326,330 C386,276 514,276 574,330 C660,410 664,600 638,770 "
             "C580,722 520,702 450,702 C380,702 320,722 262,770 Z' fill='rgb(200,200,200)'/>")
    p.append("<path d='M300,700 C280,560 300,420 360,360' fill='none' stroke='rgb(90,90,90)' stroke-width='16' filter='url(#fold)'/>")
    p.append("<path d='M600,700 C620,560 600,420 540,360' fill='none' stroke='rgb(90,90,90)' stroke-width='16' filter='url(#fold)'/>")
    p.append("<path d='M326,704 C306,580 320,450 370,396 C410,356 490,356 530,396 C580,450 594,580 574,704 C540,744 360,744 326,704 Z' fill='#000'/>")
    # skull inside the hood, scaled from the hero skull
    p.append(f"<g transform='translate(450,560) scale(0.6) translate(-600,-525)'>{art_hero.skull()}</g>")
    p.append("<path d='M326,704 C306,580 320,450 370,396 C410,356 490,356 530,396 C580,450 594,580 574,704 C540,744 360,744 326,704 Z' fill='url(#faceShadow)'/>")
    # hood edge highlight
    p.append("<path d='M326,704 C306,580 320,450 370,396 C410,356 490,356 530,396 C580,450 594,580 574,704' fill='none' stroke='rgb(235,235,235)' stroke-width='14'/>")
    # zip and chest wordmark
    p.append("<rect x='444' y='740' width='12' height='460' fill='#000'/>")
    p.append(f"<g opacity='1'>{ag.logo(300, 820, 300, '#000')}</g>")
    p.append("<rect x='442' y='780' width='16' height='420' fill='rgb(150,150,150)' opacity='0'/>")
    p.append(ag.crossbone(205, 1060, 0.8, rot=8, fill='rgb(20,20,20)', gap='rgb(150,150,150)'))
    p.append(ag.crossbone(695, 1060, 0.8, rot=-8, fill='rgb(20,20,20)', gap='rgb(150,150,150)'))
    return W, H, PANEL_DEFS, "".join(p)


def campaign_relic():
    """The back print hung in a gothic window: the hoodie as a relic."""
    W, H = 900, 1200
    p = []
    # window frame
    p.append("<path d='M120,1200 L120,520 A660,660 0 0 1 450,30 A660,660 0 0 1 780,520 L780,1200 Z' fill='rgb(70,70,70)'/>")
    p.append("<path d='M170,1200 L170,540 A560,560 0 0 1 450,110 A560,560 0 0 1 730,540 L730,1200 Z' fill='rgb(18,18,18)'/>")
    # tracery bars
    for x in (310, 590):
        p.append(f"<rect x='{x - 6}' y='300' width='12' height='900' fill='rgb(90,90,90)'/>")
    p.append("<circle cx='450' cy='300' r='90' fill='none' stroke='rgb(90,90,90)' stroke-width='12'/>")
    # light through the window
    p.append("<path d='M200,140 L700,140 L900,1200 L0,1200 Z' fill='rgb(255,255,255)' opacity='0.08'/>")
    # the hoodie back, hung from a hook: a solid ink silhouette with the print knocked out
    w, h, d, fab_s, prn_s, mask_s = ag.hoodie_back()
    p.append("<line x1='450' y1='150' x2='450' y2='262' stroke='rgb(220,220,220)' stroke-width='5'/>")
    sil = (mask_s.replace("fill='#fff'", "fill='rgb(225,225,225)'")
           + f"<path d='{ag.HEM}' fill='rgb(190,190,190)'/>"
           + f"<path d='{ag.CUFF_L}' fill='rgb(190,190,190)'/><path d='{mirror_x(ag.CUFF_L, 500)}' fill='rgb(190,190,190)'/>")
    folds = "".join(f"<path d='{fd}' fill='none' stroke='rgb(120,120,120)' stroke-width='22' filter='url(#fold)'/>"
                    for fd in ("M330,460 C350,560 344,680 356,820", "M670,460 C650,560 656,680 644,820",
                               "M220,420 C200,520 186,640 172,790", "M780,420 C800,520 814,640 828,790"))
    knock = prn_s.replace("#fff", "@").replace("#000", "rgb(210,210,210)").replace("@", "#000")
    p.append(f"<g transform='translate(450,720) scale(0.8) translate(-500,-560)'>{sil}{folds}{knock}</g>")
    return W, H, PANEL_DEFS, "".join(p)


def campaign_sigil():
    """The crossbone as a monument: large sigil under a halo, flanked by thorns."""
    W, H = 900, 1200
    p = [f"<rect width='{W}' height='{H}' fill='url(#spot)' opacity='0.6'/>"]
    p.append(rays(450, 520, 250, [(-180 + k * 10, 120 + (k % 3) * 90, 2.6, 1) for k in range(37)]))
    p.append("<circle cx='450' cy='520' r='250' fill='#000'/>")
    p.append("<circle cx='450' cy='520' r='236' fill='none' stroke='#fff' stroke-width='6'/>")
    p.append("<circle cx='450' cy='520' r='222' fill='none' stroke='rgb(140,140,140)' stroke-width='2'/>")
    p.append(ag.crossbone(450, 560, 1.85))
    p.append("<text x='450' y='975' text-anchor='middle' font-family='Barlow Condensed' font-weight='600' font-size='96' letter-spacing='18' fill='#fff'>DROP 01</text>")
    p.append("<text x='450' y='1050' text-anchor='middle' font-family='IBM Plex Mono' font-size='22' letter-spacing='10' fill='rgb(200,200,200)'>FORSAKEN TO DECAY</text>")
    return W, H, PANEL_DEFS, "".join(p)
