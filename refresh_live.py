"""Shim — live pipeline now lives at pipelines/live/run.py"""
import runpy
from pathlib import Path

runpy.run_path(
    str(Path(__file__).resolve().parent / "pipelines" / "live" / "run.py"),
    run_name="__main__",
)
