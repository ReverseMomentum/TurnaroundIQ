"""
Minimal .env loader (no third-party dependency).

Reads KEY=VALUE lines from, in order:
  $TURNAROUNDIQ_ENV_FILE, /etc/turnaroundiq.env, <repo>/.env
Existing environment variables always win.
"""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
_loaded = False


def _candidates():
    explicit = os.environ.get("TURNAROUNDIQ_ENV_FILE")
    if explicit:
        yield Path(explicit)
    yield Path("/etc/turnaroundiq.env")
    yield ROOT / ".env"


def _parse(path):
    try:
        text = path.read_text()
    except OSError:
        return
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load():
    global _loaded
    if _loaded:
        return
    for path in _candidates():
        if path.is_file():
            _parse(path)
    _loaded = True
