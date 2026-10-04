#!/usr/bin/env python3
"""
How much history the model has for a team, and similar names it might be split across.

    venv/bin/python -u scripts/team_check.py "Bolton Wanderers Res" "Sheffield United U21"
"""
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from models import fta_path_model as pm  # noqa: E402
from team_normalizer import normalize_team  # noqa: E402


def main(names):
    matches = pm.load_matches()
    seen = defaultdict(lambda: {"n": 0, "up2": 0, "leagues": set(), "last": 0})
    for m in matches:
        for side, team in ((1, m["home"]), (2, m["away"])):
            s = seen[team]
            s["n"] += 1
            s["up2"] += int(m["sides"][side]["up2"])
            s["leagues"].add(m["league"])
            s["last"] = max(s["last"], m["day"])
    teams, _ = pm.current_state()
    for raw in names:
        norm = normalize_team(raw)
        s = seen.get(norm)
        st = teams.get(norm)
        print(f"\n{raw!r} -> stored as {norm!r}")
        if s:
            print(f"  matches {s['n']}, went 2 up {s['up2']}, last {date.fromordinal(s['last'])}, "
                  f"leagues {sorted(s['leagues'])}")
            if st is not None:
                print(f"  model weight now: {st.n:.1f} matches (recent games count more), 2-ups {st.up2:.1f}")
        else:
            print("  NO matches under this name")
        words = [w for w in norm.lower().replace("-", " ").split() if len(w) > 3 and w not in ("united", "city", "town", "wanderers")]
        key = words[0] if words else norm.lower().split()[0]
        similar = sorted((t for t in seen if key in t.lower() and t != norm), key=lambda t: -seen[t]["n"])[:8]
        for t in similar:
            v = seen[t]
            print(f"  similar: {t!r}: {v['n']} matches, last {date.fromordinal(v['last'])}, {sorted(v['leagues'])}")


if __name__ == "__main__":
    main(sys.argv[1:] or ["Bolton Wanderers Res", "Sheffield United U21"])
