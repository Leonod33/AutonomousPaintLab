#!/usr/bin/env python3
"""Concise dependency preflight for Paint entry points."""

from __future__ import annotations

import argparse
import importlib.util
import shutil


def ensure_runtime(recording: bool = False) -> None:
    missing: list[str] = []
    if importlib.util.find_spec("PIL") is None:
        missing.append("Pillow")
    if importlib.util.find_spec("pygame") is None:
        missing.append("PyGame 2.6.1")
    if recording and shutil.which("ffmpeg") is None:
        missing.append("FFmpeg")
    if missing:
        names = ", ".join(missing)
        raise SystemExit(
            f"Paint runtime is missing: {names}. "
            "Create an isolated environment and install requirements.txt; "
            "install FFmpeg separately when recording is requested."
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recording", action="store_true")
    arguments = parser.parse_args()
    ensure_runtime(arguments.recording)
    print("Paint runtime ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

