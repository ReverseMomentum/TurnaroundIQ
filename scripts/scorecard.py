#!/usr/bin/env python3
"""Predictions logged before kick-off vs results (see models/scorecard.py).

    venv/bin/python -u scripts/scorecard.py            # last 30 days
    venv/bin/python -u scripts/scorecard.py --days 90
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from models import scorecard  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    scorecard.report(ap.parse_args().days)


if __name__ == "__main__":
    main()
