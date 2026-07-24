#!/usr/bin/env python3
"""Run a vision judge command against an existing blind tournament."""

import argparse
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from autonomous_paint.semantic_orchestrator import run_semantic_judge_command


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument(
        "--command",
        required=True,
        help="Command template containing {request} and {output}.",
    )
    parser.add_argument("--recognizability-threshold", type=float, default=7.0)
    parser.add_argument("--timeout", type=float, default=300.0)
    arguments = parser.parse_args()
    result = run_semantic_judge_command(
        arguments.run_dir,
        arguments.command,
        arguments.recognizability_threshold,
        arguments.timeout,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
