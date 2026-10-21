"""Builds every artwork in public/art. Run from ftd/: python3 scripts/build_art.py [name ...]

Names: hero-skull, cathedral, flats (product images), campaign. No names builds all.
"""

import sys

from art_lib import render, save_ink, screenprint, svg_doc

import art_campaign
import art_flats
import art_hero
import art_scenes

INK_JOBS = {
    # hero: denser ink and almost no dust so the figure reads as one hard print
    "hero-skull": (art_hero.build, dict(seed=11, grain=0.11, clump=0.15, dust=0.00003), (1200, 1500)),
    "cathedral": (art_scenes.cathedral, dict(seed=12, scratches=30), (1600, 760)),
}


def main(names):
    for name, (fn, sp, size) in INK_JOBS.items():
        if names and name not in names:
            continue
        print(name)
        w, h, defs, body = fn()
        tone = render(name, svg_doc(w, h, body, defs), w, h)
        ink, big = screenprint(tone, **sp)
        save_ink(name, ink, big, size=size)

    if not names or "flats" in names:
        print("product images (from supplied flats)")
        art_flats.main()
    if not names or "campaign" in names:
        print("campaign panels")
        art_campaign.main()


if __name__ == "__main__":
    main(sys.argv[1:])
