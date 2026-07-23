#!/usr/bin/env python3
"""Launch the human-operated Paint application."""

from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from preflight import ensure_runtime

ensure_runtime()

from autonomous_paint.app import PaintApplication


if __name__ == "__main__":
    PaintApplication(output_path=PROJECT / "human-painting.png").run_window()
