"""Strict screenshot-only interface for a genuine vision-capable agent."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from .references import load_reference_manifest
from .review import FindingVerification, ReviewFinding, SemanticAssessment
from .session import DecisionSummary, PaintRun, VisibleAction


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-file", type=Path, default=Path(".paint_session.private.json"))
    subparsers = parser.add_subparsers(dest="command", required=True)

    reset = subparsers.add_parser("reset")
    reset.add_argument("--run-dir", type=Path, required=True)
    reset.add_argument("--prompt", required=True)
    reset.add_argument("--seed", type=int, default=0)
    reset.add_argument(
        "--action-budget", "--actions", "--max-actions",
        dest="action_budget", type=int, default=100
    )
    reset.add_argument("--min-actions", type=int)
    reset.add_argument("--target-actions", type=int)
    reset.add_argument(
        "--detail-level",
        choices=("draft", "standard", "high", "ultra"),
        default="standard",
    )
    reset.add_argument(
        "--review-budget", "--revisions", dest="review_budget", type=int, default=3
    )
    reset.add_argument("--revision-actions", dest="revision_budget", type=int)
    reset.add_argument(
        "--references",
        type=Path,
        help="attributed references.json prepared before screenshot-only play",
    )
    reset.add_argument(
        "--semantic-quality",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Require prompt-aware recognizability reviews and reinspection.",
    )
    reset.add_argument(
        "--recognizability-threshold",
        type=float,
        default=7.0,
    )

    subparsers.add_parser("capture")

    for name in ("click", "drag"):
        action = subparsers.add_parser(name)
        action.add_argument("x1", type=int)
        action.add_argument("y1", type=int)
        if name == "drag":
            action.add_argument("x2", type=int)
            action.add_argument("y2", type=int)
        _add_summary_arguments(action)
        action.add_argument(
            "--revision",
            action="store_true",
            help="Count this canvas change as a checkpoint correction.",
        )

    review = subparsers.add_parser("review")
    review.add_argument("--assessment", required=True)
    review.add_argument(
        "--finding",
        action="append",
        default=[],
        help="JSON object with area, region, issue, suggestion, priority, and confidence",
    )
    _add_semantic_arguments(review)

    verify = subparsers.add_parser("verify")
    verify.add_argument("--assessment", required=True)
    verify.add_argument(
        "--verification",
        action="append",
        default=[],
        help="JSON object with finding_id, status, evidence, and remaining_issue",
    )
    _add_semantic_arguments(verify)

    final = subparsers.add_parser("finalize")
    final.add_argument("--fps", type=int, default=3)
    return parser


def _add_summary_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--goal", required=True)
    parser.add_argument("--selected-tool", required=True)
    parser.add_argument("--intended-action", required=True)
    parser.add_argument("--visual-assessment", required=True)
    parser.add_argument(
        "--pass-name",
        choices=(
            "composition",
            "construction",
            "form",
            "materials",
            "lighting",
            "texture",
            "focal_finish",
        ),
        default="construction",
    )
    parser.add_argument("--detail-key", default="subject")


def _add_semantic_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--recognizability-score", type=float)
    parser.add_argument(
        "--recognizable-without-prompt",
        action=argparse.BooleanOptionalAction,
        default=None,
    )
    parser.add_argument("--prompt-fidelity-score", type=float)
    parser.add_argument("--semantic-summary")


def run(arguments: argparse.Namespace) -> dict[str, Any]:
    if arguments.command == "reset":
        session = PaintRun(
            arguments.run_dir,
            arguments.prompt,
            arguments.seed,
            "model_vision",
            action_budget=arguments.action_budget,
            review_budget=arguments.review_budget,
            references=load_reference_manifest(arguments.references),
            revision_budget=arguments.revision_budget,
            min_actions=arguments.min_actions,
            target_actions=arguments.target_actions,
            detail_level=arguments.detail_level,
            semantic_quality_required=arguments.semantic_quality,
            recognizability_threshold=arguments.recognizability_threshold,
        )
        session.app.set_summary(
            phase="MODEL-VISION SCREENSHOT INTERFACE",
            goal="Inspect the complete application.",
            intended_action="Locate visible tools, palette, canvas, and Save control.",
            assessment="Fresh canvas; no drawing action taken.",
        )
        screenshot = session.capture("model_observation")
        _save_state(arguments.state_file, session)
        return _observation(session, screenshot)

    session = _load_state(arguments.state_file)
    if arguments.command == "capture":
        screenshot = session.capture("model_observation")
        _save_state(arguments.state_file, session)
        return _observation(session, screenshot)
    if arguments.command in {"click", "drag"}:
        summary = DecisionSummary(
            arguments.goal,
            arguments.selected_tool,
            arguments.intended_action,
            arguments.visual_assessment,
            arguments.pass_name,
            arguments.detail_key,
        )
        action = VisibleAction(
            arguments.command,
            (arguments.x1, arguments.y1),
            (arguments.x2, arguments.y2) if arguments.command == "drag" else None,
        )
        result = session.execute(
            action,
            summary,
            is_revision=True if arguments.revision else None,
        )
        _save_state(arguments.state_file, session)
        return {
            "decision_source": "model_vision",
            **result,
        }
    if arguments.command == "review":
        findings = tuple(
            _parse_finding(value, index)
            for index, value in enumerate(arguments.finding, start=1)
        )
        semantic = _parse_semantic_assessment(arguments)
        screenshot = session.review(
            arguments.assessment,
            findings,
            semantic_assessment=semantic,
        )
        _save_state(arguments.state_file, session)
        return _observation(session, screenshot)
    if arguments.command == "verify":
        verifications = tuple(
            _parse_verification(value, index)
            for index, value in enumerate(arguments.verification, start=1)
        )
        screenshot = session.verify_findings(
            arguments.assessment,
            verifications,
            semantic_assessment=_parse_semantic_assessment(arguments),
        )
        _save_state(arguments.state_file, session)
        return _observation(session, screenshot)
    if arguments.command == "finalize":
        result = session.finalize(arguments.fps)
        _save_state(arguments.state_file, session)
        return {
            "decision_source": "model_vision",
            **result,
        }
    raise AssertionError(f"unhandled command: {arguments.command}")


def _observation(session: PaintRun, screenshot: Path) -> dict[str, Any]:
    return {
        "decision_source": "model_vision",
        "decision_input": "complete_application_screenshot_only",
        "screenshot_path": str(screenshot.resolve()),
        "drawing_actions": session.app.drawing_actions,
        "drawing_action_budget": session.action_budget,
        "minimum_actions": session.minimum_actions,
        "target_actions": session.target_actions,
        "detail_level": session.detail_level,
        "reviews": session.app.review_checkpoints,
        "review_budget": session.review_budget,
        "revision_actions": session.app.revision_actions,
        "revision_action_budget": session.revision_budget,
        "reference_count": len(session.app.references),
        "visible_review_findings": len(session.app.review_findings),
        "semantic_quality_required": session.semantic_quality_required,
        "recognizability_threshold": session.recognizability_threshold,
        "quality_gates": session.quality_gate_status(),
    }


def _parse_finding(value: str, index: int) -> ReviewFinding:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as error:
        raise ValueError(f"finding {index} is not valid JSON: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError(f"finding {index} must be a JSON object")
    payload.setdefault("finding_id", f"R?-{index}")
    return ReviewFinding.from_dict(payload)


def _parse_semantic_assessment(
    arguments: argparse.Namespace,
) -> SemanticAssessment | None:
    values = (
        arguments.recognizability_score,
        arguments.recognizable_without_prompt,
        arguments.prompt_fidelity_score,
        arguments.semantic_summary,
    )
    if all(value is None for value in values):
        return None
    if any(value is None for value in values):
        raise ValueError(
            "semantic review requires recognizability score, recognizable-without-prompt, "
            "prompt-fidelity score, and semantic summary"
        )
    return SemanticAssessment(
        float(arguments.recognizability_score),
        bool(arguments.recognizable_without_prompt),
        float(arguments.prompt_fidelity_score),
        str(arguments.semantic_summary),
    )


def _parse_verification(value: str, index: int) -> FindingVerification:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"verification {index} is not valid JSON: {error}"
        ) from error
    if not isinstance(payload, dict):
        raise ValueError(f"verification {index} must be a JSON object")
    return FindingVerification.from_dict(payload)


def _save_state(path: Path, session: PaintRun) -> None:
    PaintRun._write_json(path, session.to_payload())


def _load_state(path: Path) -> PaintRun:
    if not path.exists():
        raise RuntimeError(f"session state does not exist: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"could not load session state: {error}") from error
    if not isinstance(payload, dict):
        raise RuntimeError("session state is not a JSON object")
    return PaintRun.from_payload(payload)


def main() -> int:
    arguments = build_parser().parse_args()
    try:
        result = run(arguments)
    except (OSError, RuntimeError, ValueError) as error:
        print(json.dumps({"ok": False, "error": str(error)}))
        return 2
    print(json.dumps({"ok": True, "result": result}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
