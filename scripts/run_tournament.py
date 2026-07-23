#!/usr/bin/env python3
"""Run a blind screenshot-only tournament across several seeded art variants."""

import argparse
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from preflight import ensure_runtime

ensure_runtime(recording=True)

from autonomous_paint.tournament import run_variant_tournament


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prompt",
        default="a cheerful robot tending square flowers",
    )
    parser.add_argument("--seed", type=int, default=57)
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=PROJECT / "runs" / "robot-tournament",
    )
    parser.add_argument("--candidates", type=int, default=3)
    parser.add_argument("--action-budget", type=int, default=100)
    parser.add_argument("--review-budget", type=int, default=3)
    parser.add_argument("--references", type=Path)
    arguments = parser.parse_args()
    result = run_variant_tournament(
        arguments.prompt,
        arguments.seed,
        arguments.run_dir,
        arguments.candidates,
        arguments.action_budget,
        arguments.review_budget,
        arguments.references,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
