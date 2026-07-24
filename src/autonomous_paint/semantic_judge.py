"""Validate and apply prompt-aware model-vision tournament judgments."""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import shutil
from typing import Any

from .review import ReviewFinding
from .tournament import (
    CandidateEvaluation,
    CriterionScore,
    build_rubric,
    _render_montage,
)


def apply_semantic_judgments(
    run_dir: Path,
    judgment_path: Path,
) -> dict[str, str]:
    """Rerank a completed tournament using blind semantic screenshot judgments."""
    tournament_path = run_dir / "tournament.json"
    if not tournament_path.is_file():
        raise FileNotFoundError(f"tournament manifest does not exist: {tournament_path}")
    manifest = _read_object(tournament_path)
    judgment = _read_object(judgment_path)
    prompt = str(manifest["prompt"])
    rubric = build_rubric(prompt)
    threshold = float(judgment.get("recognizability_threshold", 7.0))
    if not 0.0 <= threshold <= 10.0:
        raise ValueError("recognizability threshold must be between zero and ten")

    original = {
        str(item["candidate_id"]): item
        for item in manifest.get("evaluations", [])
    }
    supplied = judgment.get("evaluations")
    if not isinstance(supplied, list) or not supplied:
        raise ValueError("semantic judgments require a non-empty evaluations array")
    labels = [str(item.get("candidate_id", "")) for item in supplied]
    if len(set(labels)) != len(labels) or any(label not in original for label in labels):
        raise ValueError("semantic evaluation labels must uniquely match all finalists")
    if set(labels) != set(original):
        raise ValueError("semantic evaluations must cover every finalist")

    penalties, similarities = _diversity_penalties(
        labels,
        judgment.get("pairwise_diversity"),
    )
    semantic_records: list[dict[str, Any]] = []
    evaluations: list[CandidateEvaluation] = []
    for item in supplied:
        label = str(item["candidate_id"])
        recognizable = bool(item["recognizable_without_prompt"])
        recognizability = float(item["recognizability_score"])
        if not 0.0 <= recognizability <= 10.0:
            raise ValueError(f"candidate {label} recognizability must be 0–10")
        criteria = _criteria(item, rubric, label)
        base_total = round(
            sum(score.score * score.weight / 10 for score in criteria),
            1,
        )
        eligible = recognizable and recognizability >= threshold
        adjusted = max(0.0, base_total - penalties[label])
        if not eligible:
            adjusted = min(adjusted, 49.9)
        adjusted = round(adjusted, 1)
        findings = [
            ReviewFinding.from_dict(value).to_dict()
            for value in item.get("findings", [])
        ]
        record = {
            "candidate_id": label,
            "screenshot": original[label]["screenshot"],
            "final_png": original[label]["final_png"],
            "recognizable_without_prompt": recognizable,
            "recognizability_score": recognizability,
            "recognizability_threshold": threshold,
            "recognizability_gate_passed": eligible,
            "semantic_summary": str(item["semantic_summary"]),
            "criteria": [asdict(score) for score in criteria],
            "base_total_score": base_total,
            "diversity_penalty": penalties[label],
            "total_score": adjusted,
            "findings": findings,
        }
        semantic_records.append(record)
        evaluations.append(
            CandidateEvaluation(
                label,
                str((run_dir / original[label]["screenshot"]).resolve()),
                str((run_dir / original[label]["final_png"]).resolve()),
                adjusted,
                criteria,
            )
        )

    ranked = sorted(
        evaluations,
        key=lambda candidate: (
            not next(
                record["recognizability_gate_passed"]
                for record in semantic_records
                if record["candidate_id"] == candidate.candidate_id
            ),
            -candidate.total_score,
            candidate.candidate_id,
        ),
    )
    winner = ranked[0]
    eligible_count = sum(
        bool(record["recognizability_gate_passed"])
        for record in semantic_records
    )
    if eligible_count == 0:
        decision = (
            f"No finalist passed the {threshold:.1f}/10 recognizability gate; "
            f"{winner.candidate_id} is retained only as the least-bad review candidate."
        )
    else:
        runner = ranked[1] if len(ranked) > 1 else None
        decision = (
            f"Candidate {winner.candidate_id} wins the semantic review at "
            f"{winner.total_score:.1f}/100"
            + (
                f", {winner.total_score - runner.total_score:.1f} points ahead "
                f"of {runner.candidate_id}."
                if runner is not None
                else "."
            )
        )

    shutil.copyfile(winner.final_png, run_dir / "winner.png")
    shutil.copyfile(winner.screenshot, run_dir / "winner_full_app.png")
    montage = _render_montage(
        run_dir / "semantic_tournament_montage.png",
        prompt,
        rubric,
        ranked,
        winner.candidate_id,
        decision,
    )
    report = _write_report(
        run_dir / "semantic_tournament_report.md",
        prompt,
        threshold,
        ranked,
        semantic_records,
        similarities,
        decision,
    )
    manifest.setdefault("deterministic_evaluations", manifest.get("evaluations", []))
    manifest["decision_source"] = "model_vision_semantic_judge"
    manifest["semantic_judge_input"] = "final_complete_application_screenshot_only"
    manifest["recognizability_threshold"] = threshold
    manifest["semantic_evaluations"] = semantic_records
    manifest["pairwise_diversity"] = similarities
    manifest["ranking"] = [item.candidate_id for item in ranked]
    manifest["winner"] = winner.candidate_id
    manifest["decision_summary"] = decision
    manifest["semantic_report"] = report.name
    manifest["semantic_montage"] = montage.name
    tournament_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {
        "winner": winner.candidate_id,
        "winner_png": str((run_dir / "winner.png").resolve()),
        "winner_full_app": str((run_dir / "winner_full_app.png").resolve()),
        "montage": str(montage.resolve()),
        "report": str(report.resolve()),
        "tournament_json": str(tournament_path.resolve()),
    }


def _criteria(
    evaluation: dict[str, Any],
    rubric: tuple[Any, ...],
    label: str,
) -> tuple[CriterionScore, ...]:
    supplied = evaluation.get("criteria")
    if not isinstance(supplied, list):
        raise ValueError(f"candidate {label} criteria must be an array")
    by_key = {str(item.get("key", "")): item for item in supplied}
    expected = {criterion.key for criterion in rubric}
    if set(by_key) != expected:
        raise ValueError(f"candidate {label} must score every rubric criterion once")
    scores: list[CriterionScore] = []
    for criterion in rubric:
        item = by_key[criterion.key]
        score = float(item["score"])
        evidence = str(item.get("evidence", "")).strip()
        if not 0.0 <= score <= 10.0:
            raise ValueError(f"candidate {label} criterion scores must be 0–10")
        if not evidence:
            raise ValueError(f"candidate {label} criterion evidence is required")
        scores.append(
            CriterionScore(
                criterion.key,
                criterion.label,
                criterion.weight,
                round(score, 1),
                evidence,
            )
        )
    return tuple(scores)


def _diversity_penalties(
    labels: list[str],
    supplied: object,
) -> tuple[dict[str, float], list[dict[str, Any]]]:
    if len(labels) == 1:
        return {labels[0]: 0.0}, []
    if not isinstance(supplied, list):
        raise ValueError("pairwise_diversity is required for multiple finalists")
    expected = {
        tuple(sorted((left, right)))
        for index, left in enumerate(labels)
        for right in labels[index + 1 :]
    }
    seen: set[tuple[str, str]] = set()
    totals = {label: [] for label in labels}
    normalized: list[dict[str, Any]] = []
    for item in supplied:
        left = str(item.get("candidate_a", ""))
        right = str(item.get("candidate_b", ""))
        pair = tuple(sorted((left, right)))
        if pair not in expected or pair in seen:
            raise ValueError("pairwise diversity contains an invalid or duplicate pair")
        similarity = float(item["visual_similarity"])
        if not 0.0 <= similarity <= 1.0:
            raise ValueError("visual similarity must be between zero and one")
        shared = [str(value) for value in item.get("shared_features", []) if str(value)]
        if not shared:
            raise ValueError("pairwise diversity requires visible shared features")
        seen.add(pair)
        totals[left].append(similarity)
        totals[right].append(similarity)
        normalized.append(
            {
                "candidate_a": left,
                "candidate_b": right,
                "visual_similarity": similarity,
                "shared_features": shared,
            }
        )
    if seen != expected:
        raise ValueError("pairwise diversity must cover every finalist pair")
    penalties = {
        label: round(
            min(12.0, max(0.0, sum(values) / len(values) - 0.55) * 20),
            1,
        )
        for label, values in totals.items()
    }
    return penalties, normalized


def _write_report(
    path: Path,
    prompt: str,
    threshold: float,
    ranked: list[CandidateEvaluation],
    records: list[dict[str, Any]],
    similarities: list[dict[str, Any]],
    decision: str,
) -> Path:
    records_by_id = {record["candidate_id"]: record for record in records}
    lines = [
        "# Semantic Tournament Report",
        "",
        f"**Prompt:** {prompt}",
        f"**Recognizability gate:** {threshold:.1f}/10 and recognizable without the prompt",
        "",
        decision,
        "",
        "| Rank | Candidate | Recognizability | Gate | Base | Variety penalty | Final |",
        "| ---: | :---: | ---: | :---: | ---: | ---: | ---: |",
    ]
    for rank, candidate in enumerate(ranked, start=1):
        record = records_by_id[candidate.candidate_id]
        lines.append(
            f"| {rank} | {candidate.candidate_id} | "
            f"{record['recognizability_score']:.1f} | "
            f"{'PASS' if record['recognizability_gate_passed'] else 'FAIL'} | "
            f"{record['base_total_score']:.1f} | "
            f"−{record['diversity_penalty']:.1f} | {candidate.total_score:.1f} |"
        )
    for candidate in ranked:
        record = records_by_id[candidate.candidate_id]
        lines.extend(
            [
                "",
                f"## Candidate {candidate.candidate_id}",
                "",
                record["semantic_summary"],
                "",
            ]
        )
        for finding in record["findings"]:
            lines.append(
                f"- **{finding['priority'].upper()} — {finding['area']}:** "
                f"{finding['issue']} Suggested correction: {finding['suggestion']}"
            )
    if similarities:
        lines.extend(["", "## Cross-candidate similarity", ""])
        for item in similarities:
            lines.append(
                f"- {item['candidate_a']} vs {item['candidate_b']}: "
                f"{item['visual_similarity']:.0%} similar — "
                + "; ".join(item["shared_features"])
            )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value
