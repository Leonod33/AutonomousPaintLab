#!/usr/bin/env python3
"""Add one attributed web or local image to a Paint run's reference board."""

import argparse
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from preflight import ensure_runtime

ensure_runtime()

from autonomous_paint.references import prepare_reference


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--note", required=True)
    parser.add_argument("--search-query", default="")
    parser.add_argument("--rights-note", default="Visual research only; do not trace or reproduce exactly.")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--image-path", type=Path)
    source.add_argument("--image-url", default="")
    arguments = parser.parse_args()
    result = prepare_reference(
        arguments.run_dir,
        title=arguments.title,
        source_url=arguments.source_url,
        note=arguments.note,
        search_query=arguments.search_query,
        rights_note=arguments.rights_note,
        image_path=arguments.image_path,
        image_url=arguments.image_url,
    )
    print(json.dumps({"reference_manifest": str(result.resolve())}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
