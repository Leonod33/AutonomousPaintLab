#!/usr/bin/env python3
"""Run the deterministic screenshot-only visible-UI agent."""

import argparse
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from preflight import ensure_runtime

ensure_runtime(recording=True)

from autonomous_paint.agents import run_screenshot_agent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prompt",
        default="a cheerful robot tending square flowers",
    )
    parser.add_argument("--seed", type=int, default=41)
    parser.add_argument("--run-dir", type=Path, default=PROJECT / "runs" / "pixel-robot")
    parser.add_argument(
        "--action-budget", "--actions", "--max-actions",
        dest="action_budget", type=int, default=100
    )
    parser.add_argument("--min-actions", type=int)
    parser.add_argument("--target-actions", type=int)
    parser.add_argument(
        "--detail-level",
        choices=("draft", "standard", "high", "ultra"),
        default="standard",
    )
    parser.add_argument(
        "--review-budget", "--revisions", dest="review_budget", type=int, default=3
    )
    parser.add_argument("--revision-actions", dest="revision_budget", type=int)
    parser.add_argument("--references", type=Path)
    arguments = parser.parse_args()
    result = run_screenshot_agent(
        arguments.prompt,
        arguments.seed,
        arguments.run_dir,
        action_budget=arguments.action_budget,
        review_budget=arguments.review_budget,
        reference_manifest=arguments.references,
        revision_budget=arguments.revision_budget,
        min_actions=arguments.min_actions,
        target_actions=arguments.target_actions,
        detail_level=arguments.detail_level,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
