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
        "--action-budget", "--actions", "--max-actions",
        dest="action_budget", type=int, default=100
    )
    parser.add_argument("--min-actions", type=int, default=0)
    parser.add_argument("--target-actions", type=int)
    parser.add_argument(
        "--detail-level",
        choices=("draft", "standard", "high", "ultra"),
        default="standard",
    )
    parser.add_argument(
        "--review-budget", "--revisions", dest="review_budget", type=int, default=3
    )
    parser.add_argument("--revision-actions", dest="revision_budget", type=int, default=10)
    arguments = parser.parse_args()
    PaintApplication(
        output_path=arguments.output,
        action_budget=arguments.action_budget,
        review_budget=arguments.review_budget,
        revision_budget=arguments.revision_budget,
        minimum_actions=arguments.min_actions,
        target_actions=arguments.target_actions,
        detail_level=arguments.detail_level,
    ).run_window()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
