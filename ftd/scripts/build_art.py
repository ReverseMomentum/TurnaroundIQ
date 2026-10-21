"""Builds every artwork in public/art. Run from ftd/: python3 scripts/build_art.py [name ...]

Names: concept (hero + cathedral), flats (product images), campaign. No names builds all.
"""

import sys

import art_campaign
import art_concept
import art_flats


def main(names):
    if not names or "concept" in names:
        print("hero and cathedral (from the supplied concept)")
        art_concept.main()
    if not names or "flats" in names:
        print("product images (from supplied flats)")
        art_flats.main()
    if not names or "campaign" in names:
        print("campaign panels")
        art_campaign.main()


if __name__ == "__main__":
    main(sys.argv[1:])
