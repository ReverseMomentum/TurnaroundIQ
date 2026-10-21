"""Builds every artwork in public/art. Run from ftd/: python3 scripts/build_art.py [name ...]

Names: hero, cathedral, flats (product images), campaign. No names builds all.
"""

import sys

from art_lib import render, save_ink, screenprint, svg_doc

import art_campaign
import art_flats
import art_hero_concept
import art_scenes

INK_JOBS = {
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

    if not names or "hero" in names:
        print("hero (from the supplied concept)")
        art_hero_concept.main()
    if not names or "flats" in names:
        print("product images (from supplied flats)")
        art_flats.main()
    if not names or "campaign" in names:
        print("campaign panels")
        art_campaign.main()


if __name__ == "__main__":
    main(sys.argv[1:])
