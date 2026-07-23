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
    parser.add_argument("--action-budget", type=int, default=100)
    parser.add_argument("--review-budget", type=int, default=3)
    parser.add_argument("--references", type=Path)
    arguments = parser.parse_args()
    result = run_screenshot_agent(
        arguments.prompt,
        arguments.seed,
        arguments.run_dir,
        arguments.action_budget,
        arguments.review_budget,
        arguments.references,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
