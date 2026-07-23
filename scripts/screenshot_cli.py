#!/usr/bin/env python3
"""Entry point for the strict model-vision screenshot interface."""

from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from preflight import ensure_runtime

ensure_runtime()

from autonomous_paint.screenshot_cli import main


if __name__ == "__main__":
    raise SystemExit(main())
