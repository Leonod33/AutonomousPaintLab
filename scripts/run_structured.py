#!/usr/bin/env python3
"""Run the direct structured-control verification agent."""

import argparse
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from preflight import ensure_runtime

ensure_runtime(recording=True)

from autonomous_paint.agents import run_structured_control


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prompt",
        default="a lighthouse during a storm using four colours",
    )
    parser.add_argument("--seed", type=int, default=23)
    parser.add_argument("--run-dir", type=Path, default=PROJECT / "runs" / "structured-lighthouse")
    parser.add_argument("--references", type=Path)
    arguments = parser.parse_args()
    print(
        json.dumps(
            run_structured_control(
                arguments.prompt,
                arguments.seed,
                arguments.run_dir,
                reference_manifest=arguments.references,
            ),
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
