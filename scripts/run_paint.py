#!/usr/bin/env python3
"""Launch the human-operated Paint application."""

import argparse
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from preflight import ensure_runtime

ensure_runtime()

from autonomous_paint.app import PaintApplication


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT / "human-painting.png",
    )
    parser.add_argument(
        "--action-budget", "--actions", dest="action_budget", type=int, default=100
    )
    parser.add_argument(
        "--review-budget", "--revisions", dest="review_budget", type=int, default=3
    )
    parser.add_argument("--revision-actions", dest="revision_budget", type=int, default=3)
    arguments = parser.parse_args()
    PaintApplication(
        output_path=arguments.output,
        action_budget=arguments.action_budget,
        review_budget=arguments.review_budget,
        revision_budget=arguments.revision_budget,
    ).run_window()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
