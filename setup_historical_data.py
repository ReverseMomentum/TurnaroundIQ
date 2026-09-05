"""Shim — historical pipeline now lives at pipelines/historical/run.py"""
import runpy
from pathlib import Path

runpy.run_path(
    str(Path(__file__).resolve().parent / "pipelines" / "historical" / "run.py"),
    run_name="__main__",
)
