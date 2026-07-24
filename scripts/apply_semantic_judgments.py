#!/usr/bin/env python3
"""Apply blind prompt-aware model-vision judgments to a completed tournament."""

import argparse
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from autonomous_paint.semantic_judge import apply_semantic_judgments


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--judgments", type=Path, required=True)
    arguments = parser.parse_args()
    result = apply_semantic_judgments(arguments.run_dir, arguments.judgments)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
