#!/usr/bin/env python3
"""
The Stables: load racecards (and optionally results) from a JSON file.

    venv/bin/python scripts/stables_import.py cards/2026-10-02.json

Format (every field except date, course, runner name and a price is optional):

{
  "timestamp": "2026-10-02T11:00:00Z",
  "races": [{
    "date": "2026-10-02", "time": "14:30", "course": "Ascot", "country": "GB",
    "name": "Class 3 Handicap", "distance": "1m", "race_class": "3", "going": "Good",
    "handicap": true, "race_type": "flat", "surface": "turf",
    "terms": [{"bookmaker": "Book A", "places": 5, "fraction": "1/5"}],
    "runners": [{
      "horse": "Horse Name", "number": 1, "draw": 4, "jockey": "J Smith",
      "trainer": "A Trainer", "age": 4, "weight": "9-7", "official_rating": 82,
      "odds": {"Book A": 6.0, "Book B": 5.5},
      "exchange": {"back": 6.4, "lay": 6.6, "volume": 1250},
      "features": {"speed_rating": 88, "days_since_run": 21},
      "non_runner": false
    }],
    "result": ["Winner Name", "Second Name", "Third Name"]
  }]
}

"terms" lists the extra-place offers to price; standard each-way terms are
used when it is missing. "result" (finishing order) feeds calibration.
Re-importing the same race updates it and adds a new price snapshot.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from racing import store  # noqa: E402


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    for path in sys.argv[1:]:
        card = json.loads(Path(path).read_text())
        print(path, store.import_card(card))


if __name__ == "__main__":
    main()
