#!/usr/bin/env python3
"""
The Stables: load a day's extra-place offers from a pasted list (format in
racing/offers_text.py) onto that day's races. Races must already be on the
server (the Betfair collector loads cards 12 hours ahead).

    venv/bin/python scripts/stables_offers.py data/offers/2026-10-05.txt
    venv/bin/python scripts/stables_offers.py offers.txt --date 2026-10-06

Same as "Paste a list" under Add extra-place offer in the app.
"""
import argparse
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from racing import offers_text  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file", type=Path)
    ap.add_argument("--date", help="YYYY-MM-DD (default: from the file name, else today)")
    a = ap.parse_args()
    m = re.search(r"\d{4}-\d{2}-\d{2}", a.file.name)
    day = a.date or (m.group(0) if m else date.today().isoformat())
    out = offers_text.apply(a.file.read_text(), day)
    print(f"{day}: {out['offers']} offers saved on {out['races']} races")
    if out["not_found"]:
        print("races not on the server yet (re-run after the next card refresh):", ", ".join(out["not_found"]))
    if out["not_understood"]:
        print("lines not understood:", out["not_understood"])


if __name__ == "__main__":
    main()
