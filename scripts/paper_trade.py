"""
Paper trading CLI.

    python -u scripts/paper_trade.py summary --user dev_user
    python -u scripts/paper_trade.py list --user dev_user
    python -u scripts/paper_trade.py bankroll --user dev_user --amount 1000
    python -u scripts/paper_trade.py auto-settle --user dev_user
    python -u scripts/paper_trade.py settle --user dev_user --id 3 --result fta
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api import tracked as store


def main():
    p = argparse.ArgumentParser(description="TurnaroundIQ paper trading")
    p.add_argument("--user", default="dev_user", help="app_user_id / Bearer token id")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("summary")
    sub.add_parser("list")
    b = sub.add_parser("bankroll")
    b.add_argument("--amount", type=float, required=True)
    b.add_argument("--stake", type=float, default=None)
    s = sub.add_parser("settle")
    s.add_argument("--id", type=int, required=True)
    s.add_argument("--result", required=True, help="fta|no_fta|void")
    sub.add_parser("auto-settle")

    args = p.parse_args()
    uid = args.user

    if args.cmd == "summary":
        print(json.dumps(store.summary(uid), indent=2))
    elif args.cmd == "list":
        print(json.dumps(store.list_tracked(uid, limit=30), indent=2))
    elif args.cmd == "bankroll":
        out = store.save_paper_settings(
            uid, starting_bankroll=args.amount, default_stake=args.stake
        )
        print(json.dumps(out, indent=2))
    elif args.cmd == "settle":
        bet = store.settle_tracked(uid, args.id, result=args.result)
        print(json.dumps(bet, indent=2))
    elif args.cmd == "auto-settle":
        n = store.auto_settle_from_results(uid)
        print(json.dumps({"settled": n, "summary": store.summary(uid)}, indent=2))


if __name__ == "__main__":
    main()
