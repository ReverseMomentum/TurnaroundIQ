"""
Plain-terminal progress for collector scripts.

Works on a phone SSH session: one updating bar, plus a log line
when a step finishes. No extra packages.
"""

import sys
import time


def _fmt_seconds(seconds):
    seconds = max(0, int(seconds))
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h{minutes:02d}m"
    if minutes:
        return f"{minutes}m{secs:02d}s"
    return f"{secs}s"


class ProgressBar:
    def __init__(self, total, label="Progress"):
        self.total = max(int(total), 1)
        self.label = label
        self.current = 0
        self.started = time.time()
        self._last_draw = 0.0
        self.draw(force=True)

    def update(self, current=None, detail=""):
        if current is None:
            self.current += 1
        else:
            self.current = current
        now = time.time()
        if now - self._last_draw < 0.15 and self.current < self.total:
            return
        self.draw(detail=detail, force=True)

    def draw(self, detail="", force=False):
        if force:
            self._last_draw = time.time()
        ratio = min(self.current / self.total, 1.0)
        width = 28
        filled = int(width * ratio)
        bar = "#" * filled + "-" * (width - filled)
        elapsed = time.time() - self.started
        if ratio > 0:
            remaining = elapsed * (1 - ratio) / ratio
        else:
            remaining = 0
        detail = (detail or "")[:42]
        line = (
            f"\r{self.label} [{bar}] {int(ratio * 100):3d}% "
            f"{self.current}/{self.total} "
            f"eta {_fmt_seconds(remaining)}"
        )
        if detail:
            line += f"  {detail}"
        sys.stdout.write(line[:118])
        sys.stdout.flush()

    def finish(self, detail="done"):
        self.current = self.total
        self.draw(detail=detail, force=True)
        sys.stdout.write("\n")
        sys.stdout.flush()


def step(message):
    print(f"\n>> {message}", flush=True)


def ok(message):
    print(f"   + {message}", flush=True)


def warn(message):
    print(f"   ! {message}", flush=True)
