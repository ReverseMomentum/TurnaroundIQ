"""Hero artwork: anatomical skull and shoulders under a spiked solar halo."""

import random

from art_lib import mirror_x, rays

W, H = 1200, 1500
CX = 600


def g(v):
    v = int(255 * v)
    return f"rgb({v},{v},{v})"


def both(path, fill, extra=""):
    return f"<path d='{path}' fill='{fill}' {extra}/><path d='{mirror_x(path, CX)}' fill='{fill}' {extra}/>"


def both_stroke(path, stroke, width, extra=""):
    a = f"fill='none' stroke='{stroke}' stroke-width='{width}' stroke-linecap='round' {extra}"
    return f"<path d='{path}' {a}/><path d='{mirror_x(path, CX)}' {a}/>"


DEFS = f"""
<radialGradient id='cran' cx='0.5' cy='0.32' r='0.62'>
  <stop offset='0' stop-color='{g(1)}'/><stop offset='0.55' stop-color='{g(0.93)}'/>
  <stop offset='0.85' stop-color='{g(0.62)}'/><stop offset='1' stop-color='{g(0.38)}'/>
</radialGradient>
<radialGradient id='sock' cx='0.5' cy='0.42' r='0.6'>
  <stop offset='0' stop-color='#000'/><stop offset='0.62' stop-color='#000'/>
  <stop offset='0.86' stop-color='{g(0.32)}'/><stop offset='1' stop-color='{g(0.62)}'/>
</radialGradient>
<radialGradient id='halo' cx='0.5' cy='0.5' r='0.5'>
  <stop offset='0.3' stop-color='{g(0.0)}'/><stop offset='0.62' stop-color='{g(0.0)}'/>
  <stop offset='1' stop-color='{g(0.0)}'/>
</radialGradient>
<linearGradient id='fadeBody' x1='0' y1='0' x2='0' y2='1'>
  <stop offset='0' stop-color='#fff'/><stop offset='0.62' stop-color='#fff'/>
  <stop offset='0.86' stop-color='{g(0.45)}'/><stop offset='1' stop-color='#000'/>
</linearGradient>
<linearGradient id='flesh' x1='0' y1='0' x2='0' y2='1'>
  <stop offset='0' stop-color='{g(0.9)}'/><stop offset='1' stop-color='{g(0.68)}'/>
</linearGradient>
<radialGradient id='delt' cx='0.45' cy='0.32' r='0.7'>
  <stop offset='0' stop-color='{g(0.97)}'/><stop offset='0.6' stop-color='{g(0.8)}'/>
  <stop offset='1' stop-color='{g(0.3)}'/>
</radialGradient>
<filter id='soft' x='-20%' y='-20%' width='140%' height='140%'><feGaussianBlur stdDeviation='7'/></filter>
<filter id='soft2' x='-20%' y='-20%' width='140%' height='140%'><feGaussianBlur stdDeviation='3'/></filter>
<mask id='bodyMask'><rect width='{W}' height='{H}' fill='url(#fadeBody)'/></mask>
"""


def halo():
    r = random.Random(7)
    items = []
    # long thorns at the cardinal-ish angles, short ones between; upper 230 degrees only
    n = 23
    for i in range(n):
        ang = -205 + i * (230 / (n - 1))
        major = i % 2 == 0
        dist = abs(ang + 90)  # 0 at vertical
        if major:
            ln = 300 + 170 * max(0, 1 - dist / 120) + r.uniform(-30, 30)
            hw = 4.4
        else:
            ln = 140 + 60 * max(0, 1 - dist / 120) + r.uniform(-20, 20)
            hw = 3.2
        items.append((ang + r.uniform(-1.5, 1.5), ln, hw, 1.0 if major else 0.9))
    # the crown: a forged band the spikes grow out of
    band = (
        f"<path d='M392,430 C410,310 500,262 600,262 C700,262 790,310 808,430' fill='none' "
        f"stroke='{g(0.86)}' stroke-width='22'/>"
    )
    return rays(CX, 470, 205, items) + band


def body():
    parts = []
    # trapezius and shoulder mass
    parts.append(
        f"<path d='M520,700 C500,800 420,880 300,915 C215,940 150,990 120,1080 L80,1500 L1120,1500 "
        f"L1080,1080 C1050,990 985,940 900,915 C780,880 700,800 680,700 Z' fill='url(#flesh)'/>"
    )
    # torso shadow under the collarbones
    parts.append(f"<path d='M330,960 C450,990 750,990 870,960 L880,1500 L320,1500 Z' fill='{g(0.42)}' filter='url(#soft)'/>")
    # deltoids
    parts.append(both("M110,1010 C140,930 250,905 330,935 C380,960 395,1060 370,1170 C345,1270 250,1330 150,1330 "
                      "C95,1250 80,1110 110,1010 Z", "url(#delt)"))
    # pectoral masses, wasted
    parts.append(both("M360,985 C450,975 560,985 588,1000 L588,1170 C520,1200 430,1195 372,1160 C350,1100 345,1030 360,985 Z",
                      g(0.72)))
    # muscle fibres on pecs and deltoids
    r = random.Random(3)
    fib = []
    for i in range(26):
        y = 995 + i * 7
        fib.append(f"M{372 + r.uniform(-4, 4):.0f},{y + 40:.0f} C430,{y - 5:.0f} 520,{y - 8:.0f} 586,{y - 2:.0f}")
    for i in range(18):
        x = 140 + i * 12
        fib.append(f"M{x},{960 + abs(i - 9) * 6} C{x - 10},1080 {x - 6},1200 {x + 18},{1290 - abs(i - 9) * 4}")
    for p in fib:
        parts.append(both_stroke(p, g(0.25), 2.2, "opacity='0.8'"))
    # sternum
    parts.append(f"<path d='M572,950 C585,940 615,940 628,950 L622,1010 C640,1030 634,1260 616,1330 L584,1330 "
                 f"C566,1260 560,1030 578,1010 Z' fill='{g(0.95)}'/>")
    # ribs: exposed through the wasting flesh
    for i in range(6):
        y0 = 1004 + i * 50
        sp = 1 + i * 0.12
        p = (f"M592,{y0} C560,{y0 + 6} {505 - i * 6},{y0 + 22 * sp:.0f} {440 - i * 10},{y0 + 58 * sp:.0f} "
             f"C{405 - i * 10},{y0 + 80 * sp:.0f} {385 - i * 8},{y0 + 110 * sp:.0f} {378 - i * 6},{y0 + 140 * sp:.0f}")
        parts.append(both_stroke(p, g(0.0), 30 - i))
        parts.append(both_stroke(p, g(0.96), 19 - i))
        # costal cartilage, a duller grey where rib meets sternum
        parts.append(both_stroke(f"M592,{y0} C575,{y0 + 3} 560,{y0 + 9} 545,{y0 + 16}", g(0.7), 17 - i))
    # collarbones
    clav = "M584,935 C520,925 460,955 390,935 C345,922 300,925 258,955"
    parts.append(both_stroke(clav, g(0.0), 40))
    parts.append(both_stroke(clav, g(1.0), 27))
    parts.append(both_stroke("M560,930 C510,925 470,946 400,930", g(0.55), 5))
    # acromion knuckle
    parts.append(both("M236,935 C250,912 290,910 300,930 C305,952 280,972 255,970 C238,965 228,950 236,935 Z", g(1)))
    return f"<g mask='url(#bodyMask)'>{''.join(parts)}</g>"


def neck():
    parts = []
    # sternocleidomastoid cords, behind the jaw to the sternum
    scm = "M492,650 C510,740 545,850 575,945"
    parts.append(both_stroke(scm, g(0.0), 58))
    parts.append(both_stroke(scm, g(0.72), 44))
    for off in (-14, -5, 5, 14):
        p = f"M{492 + off},650 C{510 + off},740 {545 + off},850 {575 + off * 0.4:.0f},945"
        parts.append(both_stroke(p, g(0.3), 2.4))
    # cervical column
    parts.append(f"<rect x='566' y='760' width='68' height='190' fill='{g(0.12)}'/>")
    for i in range(5):
        y = 780 + i * 34
        parts.append(f"<path d='M562,{y} C575,{y - 6} 625,{y - 6} 638,{y} L642,{y + 20} C625,{y + 27} 575,{y + 27} 558,{y + 20} Z' "
                     f"fill='{g(0.9)}'/>")
        parts.append(both(f"M560,{y + 6} L536,{y + 2} C530,{y + 8} 532,{y + 16} 540,{y + 18} L560,{y + 16} Z", g(0.75)))
    return "".join(parts)


def skull():
    parts = []
    outline = (
        "M455,470 C440,400 448,330 498,292 C543,258 657,258 702,292 C752,330 760,400 745,470 "
        "L762,518 C768,545 754,568 728,578 L716,600 C718,650 714,682 704,704 "
        "C684,740 646,768 600,774 C554,768 516,740 496,704 C486,682 482,650 484,600 "
        "L472,578 C448,566 435,545 440,520 Z"
    )
    parts.append(f"<path d='{outline}' fill='#000' stroke='#000' stroke-width='14'/>")
    parts.append(f"<path d='{outline}' fill='url(#cran)'/>")
    # temporal hollows and the gap behind the cheekbones
    parts.append(both("M452,470 C470,480 488,520 482,575 C474,570 450,555 445,520 Z", g(0.15), "filter='url(#soft2)'"))
    parts.append(both("M482,585 C500,590 520,615 528,650 C530,690 515,708 500,712 C488,690 482,640 482,585 Z",
                      g(0.05), "filter='url(#soft2)'"))
    # cheekbone highlight
    parts.append(both("M446,522 C470,515 510,535 540,552 C520,565 480,572 458,560 Z", g(1)))
    # brow ridge
    parts.append(both("M480,445 C510,425 560,422 592,440 L590,452 C560,440 515,442 486,460 Z", g(1)))
    # orbits
    orbit = "M490,472 C496,440 545,432 580,448 C594,456 596,482 588,506 C578,536 542,548 512,537 C490,527 482,498 490,472 Z"
    parts.append(both(orbit, "url(#sock)"))
    parts.append(both("M505,470 C515,455 550,452 570,462", "none", f"stroke='{g(0.3)}' stroke-width='3'"))
    # glabella and nasal bones
    parts.append(f"<path d='M588,440 C596,470 604,470 612,440 L620,500 C612,520 588,520 580,500 Z' fill='{g(0.96)}'/>")
    # nasal aperture
    parts.append(f"<path d='M600,525 C588,532 568,566 566,596 C565,616 584,626 600,612 C616,626 635,616 634,596 "
                 f"C632,566 612,532 600,525 Z' fill='#000'/>")
    parts.append(f"<path d='M600,560 L604,612 L596,612 Z' fill='{g(0.55)}'/>")
    parts.append(f"<path d='M570,600 C560,596 552,610 560,616' fill='none' stroke='{g(0.15)}' stroke-width='4'/>")
    parts.append(f"<path d='M630,600 C640,596 648,610 640,616' fill='none' stroke='{g(0.15)}' stroke-width='4'/>")
    # maxilla shading
    parts.append(both("M520,600 C540,610 560,628 562,640 L520,642 C512,630 512,612 520,600 Z", g(0.45), "filter='url(#soft2)'"))
    # teeth
    parts.append(f"<path d='M528,636 C560,630 640,630 672,636 L668,706 C630,716 570,716 532,706 Z' fill='#000'/>")
    widths = [13, 13, 14, 15, 16, 16, 15, 14, 13, 13]
    x = 600 - sum(widths) / 2
    for i, wd in enumerate(widths):
        c = abs(i - 4.5)
        top = 640 - (4.5 - c) * 1.2
        h = 34 - c * 2.2
        parts.append(f"<path d='M{x + 1.5:.1f},{top:.1f} L{x + wd - 1.5:.1f},{top:.1f} L{x + wd - 2.5:.1f},{top + h:.1f} "
                     f"C{x + wd * 0.7:.1f},{top + h + 4:.1f} {x + wd * 0.3:.1f},{top + h + 4:.1f} {x + 2.5:.1f},{top + h:.1f} Z' "
                     f"fill='{g(0.97 - c * 0.06)}'/>")
        lt = 676 - c * 0.4
        lh = 27 - c * 2
        parts.append(f"<path d='M{x + 2.5:.1f},{lt + 3:.1f} C{x + wd * 0.3:.1f},{lt - 1:.1f} {x + wd * 0.7:.1f},{lt - 1:.1f} "
                     f"{x + wd - 2.5:.1f},{lt + 3:.1f} L{x + wd - 2:.1f},{lt + lh:.1f} L{x + 2:.1f},{lt + lh:.1f} Z' "
                     f"fill='{g(0.9 - c * 0.07)}'/>")
        x += wd
    # tooth roots under the gum line
    for i in range(9):
        xx = 535 + i * 16.5
        parts.append(f"<path d='M{xx:.0f},606 L{xx + 2:.0f},632' stroke='{g(0.55)}' stroke-width='2'/>")
    # chin and mental foramina
    parts.append(f"<path d='M565,732 C582,748 618,748 635,732 C628,756 572,756 565,732 Z' fill='{g(1)}'/>")
    parts.append(both("M552,722 C556,718 562,722 560,727 C556,731 550,727 552,722 Z", g(0.05)))
    # sutures and cracks
    parts.append(f"<path d='M478,350 C510,340 530,356 552,342 C575,330 590,350 610,338 C632,326 650,348 675,338 "
                 f"C695,330 712,344 724,352' fill='none' stroke='{g(0.1)}' stroke-width='3.5'/>")
    parts.append(f"<path d='M600,262 L596,300 L606,318 L598,338' fill='none' stroke='{g(0.1)}' stroke-width='3'/>")
    parts.append(f"<path d='M650,290 L640,330 L655,360 L644,395 L652,420' fill='none' stroke='{g(0.08)}' stroke-width='3.5'/>")
    parts.append(f"<path d='M520,300 L532,320 L526,350' fill='none' stroke='{g(0.08)}' stroke-width='2.5'/>")
    parts.append(f"<path d='M700,440 L716,470 L708,500' fill='none' stroke='{g(0.08)}' stroke-width='3'/>")
    # missing bone chip at the left temple
    parts.append(f"<path d='M468,392 L490,380 L497,404 L482,418 L466,410 Z' fill='{g(0.04)}'/>")
    return "".join(parts)


def build():
    body_svg = halo() + body() + neck() + skull()
    return W, H, DEFS, body_svg
