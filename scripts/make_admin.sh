#!/usr/bin/env bash
# Make a signed-in account an admin (can edit The Stables' extra-place offers,
# sees Model Testing). Adds its user id to ADMIN_USER_IDS and restarts the API.
#   bash scripts/make_admin.sh you@example.com
# The account must have signed in at least once.
set -euo pipefail
cd "$(dirname "$0")/.."
EMAIL="${1:?usage: bash scripts/make_admin.sh you@example.com}"
UID_="$(venv/bin/python -c "import sys; from database import get_db; r = get_db().execute('SELECT id FROM users WHERE email = ?', (sys.argv[1].strip().lower(),)).fetchone(); print(r[0] if r else '')" "$EMAIL")"
[ -n "$UID_" ] || { echo "No account for $EMAIL: sign in to the app with it first"; exit 1; }
CURRENT="$(venv/bin/python -c "import env_loader, os; env_loader.load(); print(os.environ.get('ADMIN_USER_IDS', ''))")"
case ",$CURRENT," in *",$UID_,"*) echo "$EMAIL is already an admin ($UID_)"; exit 0;; esac
NEW="${CURRENT:+$CURRENT,}$UID_"
bash deploy/set_env.sh ADMIN_USER_IDS "$NEW"
bash scripts/restart_api.sh >/dev/null 2>&1 || true
echo "$EMAIL is now an admin ($UID_)"
