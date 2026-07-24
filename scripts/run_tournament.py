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
from autonomous_paint.semantic_orchestrator import run_semantic_judge_command


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
    parser.add_argument(
        "--action-budget", "--actions", "--max-actions",
        dest="action_budget", type=int, default=100
    )
    parser.add_argument("--min-actions", type=int, default=35)
    parser.add_argument("--target-actions", type=int, default=70)
    parser.add_argument(
        "--detail-level",
        choices=("draft", "standard", "high", "ultra"),
        default="standard",
    )
    parser.add_argument(
        "--review-budget", "--revisions", dest="review_budget", type=int, default=3
    )
    parser.add_argument("--revision-actions", dest="revision_budget", type=int, default=10)
    parser.add_argument("--finalists", type=int, default=2)
    parser.add_argument("--references", type=Path)
    parser.add_argument(
        "--semantic-judge-command",
        help=(
            "Vision judge command template containing {request} and {output}; "
            "it runs after the deterministic tournament."
        ),
    )
    parser.add_argument(
        "--recognizability-threshold",
        type=float,
        default=7.0,
    )
    parser.add_argument(
        "--semantic-judge-timeout",
        type=float,
        default=300.0,
    )
    arguments = parser.parse_args()
    result = run_variant_tournament(
        arguments.prompt,
        arguments.seed,
        arguments.run_dir,
        candidate_count=arguments.candidates,
        action_budget=arguments.action_budget,
        review_budget=arguments.review_budget,
        reference_manifest=arguments.references,
        revision_budget=arguments.revision_budget,
        min_actions=arguments.min_actions,
        target_actions=arguments.target_actions,
        detail_level=arguments.detail_level,
        finalist_count=arguments.finalists,
    )
    if arguments.semantic_judge_command:
        result = run_semantic_judge_command(
            arguments.run_dir,
            arguments.semantic_judge_command,
            recognizability_threshold=arguments.recognizability_threshold,
            timeout_seconds=arguments.semantic_judge_timeout,
        )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
