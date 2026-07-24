"""Run a blind external model-vision judge and apply its validated verdict."""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess
from typing import Any, Sequence

from .semantic_judge import apply_semantic_judgments
from .tournament import build_rubric


def prepare_blind_judge_request(
    run_dir: Path,
    recognizability_threshold: float = 7.0,
) -> Path:
    """Create a sanitized request containing no seeds, logs, or canvas state."""
    if not 0.0 <= recognizability_threshold <= 10.0:
        raise ValueError("recognizability threshold must be between zero and ten")
    manifest_path = run_dir / "tournament.json"
    manifest = _read_object(manifest_path)
    evaluations = manifest.get("evaluations")
    if not isinstance(evaluations, list) or not evaluations:
        raise ValueError("tournament manifest has no finalist evaluations")

    blind_dir = run_dir / "semantic_blind_inputs"
    blind_dir.mkdir(exist_ok=True)
    candidates: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in evaluations:
        label = str(item.get("candidate_id", ""))
        if not label or label in seen:
            raise ValueError("finalist labels must be non-empty and unique")
        source = (run_dir / str(item["screenshot"])).resolve()
        if not source.is_file() or run_dir.resolve() not in source.parents:
            raise ValueError(f"finalist {label} screenshot is missing or outside the run")
        destination = blind_dir / f"candidate-{label}.png"
        shutil.copyfile(source, destination)
        candidates.append(
            {
                "candidate_id": label,
                "screenshot": str(destination.resolve()),
                "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
            }
        )
        seen.add(label)

    prompt = str(manifest["prompt"])
    request = {
        "protocol_version": 1,
        "task": "blind_model_vision_tournament_judgment",
        "decision_input": "complete_application_screenshots_only",
        "prompt": prompt,
        "recognizability_threshold": recognizability_threshold,
        "rubric": [asdict(item) for item in build_rubric(prompt)],
        "candidates": candidates,
        "instructions": [
            "Inspect every supplied screenshot visually.",
            "Do not seek seeds, action logs, canvas state, plans, or review reports.",
            "Judge recognizability without relying on the prompt label alone.",
            "Score every rubric criterion from 0 to 10 and cite visible evidence.",
            "Compare every candidate pair for repeated silhouette, pose, framing, palette, and construction.",
            "Return only one JSON object matching output_schema.",
        ],
        "output_schema": _output_schema([item["candidate_id"] for item in candidates]),
    }
    request_path = run_dir / "semantic_judge_request.json"
    request_path.write_text(json.dumps(request, indent=2), encoding="utf-8")
    return request_path


def run_semantic_judge_command(
    run_dir: Path,
    command: str | Sequence[str],
    recognizability_threshold: float = 7.0,
    timeout_seconds: float = 300.0,
) -> dict[str, str]:
    """Invoke a vision judge command, validate its output, and update the tournament."""
    request_path = prepare_blind_judge_request(
        run_dir,
        recognizability_threshold,
    )
    judgment_path = run_dir / "semantic_judgments.json"
    tokens = shlex.split(command) if isinstance(command, str) else list(command)
    if not tokens:
        raise ValueError("semantic judge command must not be empty")
    placeholders = {
        "request": str(request_path.resolve()),
        "output": str(judgment_path.resolve()),
    }
    rendered = [token.format_map(placeholders) for token in tokens]
    if not any("{request}" in token for token in tokens):
        raise ValueError("semantic judge command must contain {request}")
    if not any("{output}" in token for token in tokens):
        raise ValueError("semantic judge command must contain {output}")

    completed = subprocess.run(
        rendered,
        cwd=run_dir,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    invocation = {
        "command": [Path(rendered[0]).name, *rendered[1:]],
        "returncode": completed.returncode,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
        "request": request_path.name,
        "output": judgment_path.name,
    }
    (run_dir / "semantic_judge_invocation.json").write_text(
        json.dumps(invocation, indent=2),
        encoding="utf-8",
    )
    if completed.returncode:
        raise RuntimeError(
            f"semantic judge command failed with exit code {completed.returncode}: "
            f"{completed.stderr.strip()}"
        )
    if not judgment_path.is_file():
        raise RuntimeError("semantic judge command did not create its output JSON")
    return apply_semantic_judgments(run_dir, judgment_path)


def _output_schema(labels: list[str]) -> dict[str, Any]:
    return {
        "recognizability_threshold": "number 0..10",
        "evaluations": {
            "required_candidate_ids": labels,
            "each": {
                "candidate_id": "neutral label",
                "recognizable_without_prompt": "boolean",
                "recognizability_score": "number 0..10",
                "semantic_summary": "visible assessment",
                "criteria": [
                    {
                        "key": "every rubric key exactly once",
                        "score": "number 0..10",
                        "evidence": "specific visible fact",
                    }
                ],
                "findings": [
                    {
                        "finding_id": "unique id",
                        "area": "named visible region",
                        "region": ["x", "y", "width", "height"],
                        "issue": "visible weakness",
                        "suggestion": "concrete correction",
                        "priority": "high|medium|low",
                        "confidence": "number 0..1",
                        "evidence": "specific visible fact",
                    }
                ],
            },
        },
        "pairwise_diversity": [
            {
                "candidate_a": "first neutral label",
                "candidate_b": "second neutral label",
                "visual_similarity": "number 0..1",
                "shared_features": ["specific visible similarities"],
            }
        ],
    }


def _read_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"tournament manifest does not exist: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value
