"""Blind, screenshot-only comparison of reproducible Paint candidates."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import shutil
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageStat

from .agents import run_screenshot_agent
from .constants import PALETTE
from .references import ReferenceCard, load_reference_manifest
from .quality import resolve_budget_policy
from .vision import locate_interface


@dataclass(frozen=True)
class RubricCriterion:
    key: str
    label: str
    weight: int
    visible_question: str


@dataclass(frozen=True)
class CriterionScore:
    key: str
    label: str
    weight: int
    score: float
    evidence: str


@dataclass(frozen=True)
class CandidateEvaluation:
    candidate_id: str
    screenshot: str
    final_png: str
    total_score: float
    criteria: tuple[CriterionScore, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["criteria"] = [asdict(item) for item in self.criteria]
        return value


def build_rubric(prompt: str) -> tuple[RubricCriterion, ...]:
    """Create a detail-sensitive prompt rubric whose weights total 100."""
    normalized = prompt.lower()
    if "guinea pig" in normalized or "cuddle cup" in normalized:
        fidelity = "Are a cute resting guinea pig and an enclosing padded cuddle cup unmistakable?"
        accuracy = "Are the rounded body, small ears, eye, muzzle, paws, and resting pose believable?"
    elif "robot" in normalized:
        fidelity = "Are the robot, cheerful expression, and square-flower garden unmistakable?"
        accuracy = "Are the robot's head, torso, limbs, face, and gardening pose coherent?"
    elif "lighthouse" in normalized:
        fidelity = "Are the lighthouse, beacon, rough sea, and storm unmistakable?"
        accuracy = "Are the tower, lantern room, roof, horizon, and wave scale structurally coherent?"
    else:
        fidelity = "Are every requested subject, action, setting, and named prop recognizable?"
        accuracy = "Are the subject's proportions, pose, and relationships internally coherent?"
    return (
        RubricCriterion(
            "prompt_fidelity",
            "Prompt fidelity",
            20,
            fidelity,
        ),
        RubricCriterion(
            "representation_accuracy",
            "Representation accuracy",
            20,
            accuracy,
        ),
        RubricCriterion(
            "composition",
            "Composition",
            15,
            "Is the focal subject clearly placed with useful negative space and visual flow?",
        ),
        RubricCriterion(
            "depth_lighting",
            "Depth and lighting",
            15,
            "Do overlap, cast shadows, highlights, and value separation create convincing depth?",
        ),
        RubricCriterion(
            "material_rendering",
            "Material rendering",
            15,
            "Do distinct surfaces—such as fur, fabric, metal, water, or foliage—read differently?",
        ),
        RubricCriterion(
            "fine_detail",
            "Fine detail",
            10,
            "Are small focal marks, edge variations, and secondary details deliberate and clean?",
        ),
        RubricCriterion(
            "originality",
            "Originality",
            5,
            "Does the candidate have a distinct pose, silhouette, colour decision, or rendering character?",
        ),
    )


def derive_candidate_seeds(base_seed: int, candidate_count: int) -> tuple[int, ...]:
    if not 2 <= candidate_count <= 5:
        raise ValueError("variant tournaments require between two and five candidates")
    return tuple(base_seed + index * 1009 for index in range(candidate_count))


def build_diversity_contracts(candidate_count: int) -> tuple[dict[str, str], ...]:
    """Assign visible creative differences instead of relying on seed noise."""
    contracts = (
        {
            "pose": "low resting pose, face turned toward the viewer",
            "composition": "balanced central subject with generous context",
            "lighting": "soft diffuse daylight",
            "rendering": "clean rounded shapes with restrained texture",
        },
        {
            "pose": "three-quarter pose with a stronger diagonal",
            "composition": "off-centre crop and asymmetrical negative space",
            "lighting": "warm side light with a cool shadow",
            "rendering": "layered short texture marks",
        },
        {
            "pose": "compact curled pose emphasizing enclosure",
            "composition": "closer crop with the prop framing the subject",
            "lighting": "bright rim light and deeper interior shadow",
            "rendering": "graphic colour blocks plus fine focal detail",
        },
        {
            "pose": "relaxed side profile",
            "composition": "low horizon and broad foreground",
            "lighting": "muted overcast values",
            "rendering": "soft tonal masses with selective crisp edges",
        },
        {
            "pose": "alert resting pose with visible paws",
            "composition": "high viewpoint and elliptical framing",
            "lighting": "warm ambient glow",
            "rendering": "decorative seams and rhythmic marks",
        },
    )
    return contracts[:candidate_count]


def score_candidate(
    candidate_id: str,
    screenshot: Path,
    final_png: Path,
    prompt: str,
    rubric: tuple[RubricCriterion, ...],
) -> CandidateEvaluation:
    """Judge one candidate from its complete-application screenshot only."""
    interface = locate_interface(screenshot)
    with Image.open(screenshot) as source:
        application = source.convert("RGB")
        x, y = interface.canvas_origin
        width, height = interface.canvas_size
        canvas = application.crop((x, y, x + width, y + height))

    normalized = prompt.lower()
    if "guinea pig" in normalized or "cuddle cup" in normalized:
        raw_scores = _score_guinea_pig(canvas)
    elif "robot" in normalized:
        raw_scores = _score_robot(canvas)
    elif "lighthouse" in normalized:
        raw_scores = _score_lighthouse(canvas)
    else:
        raw_scores = _score_generic(canvas)

    criteria = tuple(
        CriterionScore(
            criterion.key,
            criterion.label,
            criterion.weight,
            round(raw_scores[criterion.key][0], 1),
            raw_scores[criterion.key][1],
        )
        for criterion in rubric
    )
    total = sum(item.score * item.weight / 10 for item in criteria)
    return CandidateEvaluation(
        candidate_id,
        str(screenshot.resolve()),
        str(final_png.resolve()),
        round(total, 1),
        criteria,
    )


def run_variant_tournament(
    prompt: str,
    seed: int,
    run_dir: Path,
    candidate_count: int = 3,
    action_budget: int = 100,
    review_budget: int = 3,
    reference_manifest: Path | None = None,
    revision_budget: int | None = None,
    min_actions: int | None = None,
    target_actions: int | None = None,
    max_actions: int | None = None,
    detail_level: str = "standard",
    finalist_count: int = 2,
) -> dict[str, str]:
    """Qualify thumbnails, then rerun the best concepts at the full detail target."""
    policy = resolve_budget_policy(
        action_budget=action_budget,
        min_actions=min_actions,
        target_actions=target_actions,
        max_actions=max_actions,
        review_budget=review_budget,
        revision_budget=revision_budget,
        detail_level=detail_level,
    )
    seeds = derive_candidate_seeds(seed, candidate_count)
    if not 1 <= finalist_count <= candidate_count:
        raise ValueError("finalist count must be between one and candidate count")
    if run_dir.exists() and any(run_dir.iterdir()):
        raise FileExistsError(f"tournament directory is not empty: {run_dir}")
    run_dir.mkdir(parents=True, exist_ok=True)
    rubric = build_rubric(prompt)
    labels = tuple(chr(ord("A") + index) for index in range(candidate_count))
    diversity_contracts = build_diversity_contracts(candidate_count)
    preserved_manifest = _preserve_references(reference_manifest, run_dir)
    qualifier_evaluations: list[CandidateEvaluation] = []
    evaluations: list[CandidateEvaluation] = []
    candidate_artifacts: dict[str, dict[str, str]] = {}

    for variant_index, (label, candidate_seed) in enumerate(zip(labels, seeds)):
        candidate_dir = run_dir / "qualifiers" / f"candidate-{label.lower()}"
        artifacts = run_screenshot_agent(
            prompt,
            candidate_seed,
            candidate_dir,
            action_budget=min(45, policy.maximum_actions),
            review_budget=min(2, policy.review_checkpoints),
            reference_manifest=preserved_manifest,
            variant_index=variant_index,
            revision_budget=min(4, policy.revision_actions),
            min_actions=min(20, policy.maximum_actions),
            target_actions=min(35, policy.maximum_actions),
            detail_level="draft",
        )
        final_screenshots = sorted(
            (candidate_dir / "screenshots").glob("*_final.png")
        )
        if not final_screenshots:
            raise RuntimeError(f"candidate {label} has no final application screenshot")
        final_screenshot = final_screenshots[-1]
        evaluation = score_candidate(
            label,
            final_screenshot,
            Path(artifacts["final_png"]),
            prompt,
            rubric,
        )
        qualifier_evaluations.append(evaluation)
        candidate_artifacts[label] = {
            f"qualifier_{name}": _relative(run_dir, Path(value))
            for name, value in artifacts.items()
        }

    qualifier_ranked = sorted(
        qualifier_evaluations,
        key=lambda item: (-item.total_score, item.candidate_id),
    )
    finalist_ids = {
        item.candidate_id for item in qualifier_ranked[:finalist_count]
    }
    for variant_index, (label, candidate_seed) in enumerate(zip(labels, seeds)):
        if label not in finalist_ids:
            continue
        candidate_dir = run_dir / "finalists" / f"candidate-{label.lower()}"
        artifacts = run_screenshot_agent(
            prompt,
            candidate_seed,
            candidate_dir,
            action_budget=policy.maximum_actions,
            review_budget=policy.review_checkpoints,
            reference_manifest=preserved_manifest,
            variant_index=variant_index,
            revision_budget=policy.revision_actions,
            min_actions=policy.minimum_actions,
            target_actions=policy.target_actions,
            detail_level=policy.detail_level,
        )
        final_screenshots = sorted(
            (candidate_dir / "screenshots").glob("*_final.png")
        )
        if not final_screenshots:
            raise RuntimeError(f"finalist {label} has no final application screenshot")
        evaluation = score_candidate(
            label,
            final_screenshots[-1],
            Path(artifacts["final_png"]),
            prompt,
            rubric,
        )
        evaluations.append(evaluation)
        candidate_artifacts[label].update(
            {
                f"finalist_{name}": _relative(run_dir, Path(value))
                for name, value in artifacts.items()
            }
        )

    ranked = sorted(
        evaluations,
        key=lambda item: (-item.total_score, item.candidate_id),
    )
    winner = ranked[0]
    winner_png = run_dir / "winner.png"
    winner_screenshot = run_dir / "winner_full_app.png"
    shutil.copyfile(winner.final_png, winner_png)
    shutil.copyfile(winner.screenshot, winner_screenshot)
    decision = _decision_summary(ranked)
    montage = _render_montage(
        run_dir / "tournament_montage.png",
        prompt,
        rubric,
        ranked,
        winner.candidate_id,
        decision,
    )
    report = _write_report(
        run_dir / "tournament_report.md",
        prompt,
        seed,
        seeds,
        rubric,
        ranked,
        winner.candidate_id,
        decision,
        policy.minimum_actions,
        policy.target_actions,
        policy.maximum_actions,
        policy.review_checkpoints,
        policy.revision_actions,
        qualifier_ranked,
        diversity_contracts,
    )
    manifest = {
        "prompt": prompt,
        "base_seed": seed,
        "candidate_seeds": {
            label: candidate_seed for label, candidate_seed in zip(labels, seeds)
        },
        "candidate_variants": {
            label: index for index, label in enumerate(labels)
        },
        "diversity_contracts": {
            label: contract
            for label, contract in zip(labels, diversity_contracts)
        },
        "candidate_count": candidate_count,
        "tournament_stages": {
            "qualification": {
                "target_actions": min(35, policy.maximum_actions),
                "maximum_actions": min(45, policy.maximum_actions),
                "ranking": [item.candidate_id for item in qualifier_ranked],
            },
            "final": {
                "minimum_actions": policy.minimum_actions,
                "target_actions": policy.target_actions,
                "maximum_actions": policy.maximum_actions,
                "finalists": [item.candidate_id for item in evaluations],
            },
        },
        "action_budget_per_finalist": policy.maximum_actions,
        "minimum_actions_per_finalist": policy.minimum_actions,
        "target_actions_per_finalist": policy.target_actions,
        "review_budget_per_finalist": policy.review_checkpoints,
        "revision_action_budget_per_finalist": policy.revision_actions,
        "detail_level": policy.detail_level,
        "decision_source": "deterministic_complete_application_screenshot_judge",
        "judge_input": "final_complete_application_screenshot_only",
        "blind_labels": list(labels),
        "rubric": [asdict(item) for item in rubric],
        "ranking": [item.candidate_id for item in ranked],
        "winner": winner.candidate_id,
        "decision_summary": decision,
        "evaluations": [
            {
                **item.to_dict(),
                "screenshot": _relative(run_dir, Path(item.screenshot)),
                "final_png": _relative(run_dir, Path(item.final_png)),
            }
            for item in ranked
        ],
        "qualification_evaluations": [
            {
                **item.to_dict(),
                "screenshot": _relative(run_dir, Path(item.screenshot)),
                "final_png": _relative(run_dir, Path(item.final_png)),
            }
            for item in qualifier_ranked
        ],
        "candidate_artifacts": candidate_artifacts,
    }
    tournament_json = run_dir / "tournament.json"
    tournament_json.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (run_dir / "prompt.txt").write_text(f"{prompt}\n", encoding="utf-8")
    return {
        "winner": winner.candidate_id,
        "winner_png": str(winner_png.resolve()),
        "winner_full_app": str(winner_screenshot.resolve()),
        "montage": str(montage.resolve()),
        "report": str(report.resolve()),
        "tournament_json": str(tournament_json.resolve()),
    }


def _score_robot(canvas: Image.Image) -> dict[str, tuple[float, str]]:
    subject = _crop(canvas, (120, 55, 460, 455))
    flowers = _crop(canvas, (430, 250, 330, 245))
    face = _crop(canvas, (180, 70, 270, 230))
    subject_ratio = _non_colour_ratio(subject, {"sky", "green"})
    flower_ratio = _non_colour_ratio(flowers, {"sky", "green"})
    ink_ratio = _colour_ratio(subject, {"ink"})
    subject_contrast = _contrast(subject)
    centroid_x, centroid_y, coverage = _foreground_geometry(
        canvas,
        {"sky", "green"},
    )
    accents = ("coral", "teal", "violet", "yellow")
    accent_count = sum(_colour_ratio(canvas, {name}) > 0.002 for name in accents)
    accent_entropy = _palette_entropy(canvas, accents)
    face_white = _colour_ratio(face, {"white"})
    face_yellow = _colour_ratio(face, {"yellow"})
    face_contrast = _contrast(face)
    prompt_score = _clamp(
        4.0 * min(1.0, subject_ratio / 0.30)
        + 4.0 * min(1.0, flower_ratio / 0.13)
        + 2.0 * min(1.0, accent_count / 3)
    )
    clarity_score = _clamp(
        5.5 * min(1.0, subject_contrast / 78)
        + 4.5 * min(1.0, ink_ratio / 0.055)
    )
    composition_score = _clamp(
        10
        - abs(centroid_x - 0.50) * 18
        - abs(centroid_y - 0.49) * 12
        - abs(coverage - 0.25) * 16
    )
    colour_score = _clamp(5 * accent_count / 4 + 5 * accent_entropy)
    finish_score = _clamp(
        3.5 * min(1.0, face_white / 0.08)
        + 2.5 * min(1.0, face_yellow / 0.012)
        + 4.0 * min(1.0, face_contrast / 82)
    )
    edges = _edge_density(canvas)
    return {
        "prompt_fidelity": (
            prompt_score,
            f"Robot region is {subject_ratio:.0%} non-background; the square-flower "
            f"band is {flower_ratio:.0%} non-background.",
        ),
        "representation_accuracy": (
            clarity_score,
            f"Robot-region contrast is {subject_contrast:.0f}/128 with "
            f"{ink_ratio:.1%} dark outline pixels.",
        ),
        "composition": (
            composition_score,
            f"Foreground centre is ({centroid_x:.0%}, {centroid_y:.0%}) with "
            f"{coverage:.0%} canvas coverage.",
        ),
        "depth_lighting": (
            _clamp((clarity_score + composition_score) / 2),
            f"Value separation is {subject_contrast:.0f}/128 and the foreground "
            f"centre remains at ({centroid_x:.0%}, {centroid_y:.0%}).",
        ),
        "material_rendering": (
            _clamp((colour_score + edges * 80) / 2),
            f"{accent_count}/4 material accents are visible with {edges:.1%} "
            "whole-canvas edge density.",
        ),
        "fine_detail": (
            finish_score,
            f"Face contrast is {face_contrast:.0f}/128; white eye pixels and a "
            f"yellow focal accent are both visibly present.",
        ),
        "originality": (
            _clamp(4 + 6 * accent_entropy),
            f"Normalized accent entropy is {accent_entropy:.2f}, reflecting the "
            "candidate's distinct colour distribution.",
        ),
    }


def _score_lighthouse(canvas: Image.Image) -> dict[str, tuple[float, str]]:
    tower = _crop(canvas, (270, 90, 290, 455))
    sky = _crop(canvas, (0, 0, canvas.width, 400))
    sea = _crop(canvas, (0, 390, canvas.width, canvas.height - 390))
    tower_light = _colour_ratio(tower, {"white", "yellow"})
    environment_dark = _colour_ratio(canvas, {"navy", "storm"})
    palette_count = _present_palette_count(canvas)
    tower_contrast = _contrast(tower)
    sky_edges = _edge_density(sky)
    sea_edges = _edge_density(sea)
    centroid_x, centroid_y, coverage = _foreground_geometry(
        canvas,
        {"navy", "storm"},
    )
    prompt_score = _clamp(
        4.5 * min(1.0, tower_light / 0.18)
        + 3.5 * min(1.0, environment_dark / 0.75)
        + 2.0 * min(1.0, (sky_edges + sea_edges) / 0.12)
    )
    clarity_score = _clamp(
        5.5 * min(1.0, tower_light / 0.20)
        + 4.5 * min(1.0, tower_contrast / 86)
    )
    storm_score = _clamp(5 * min(1.0, sky_edges / 0.06) + 5 * min(1.0, sea_edges / 0.07))
    colour_score = _clamp(10 - abs(palette_count - 4) * 2.5)
    finish_score = _clamp(
        4 * min(1.0, _colour_ratio(tower, {"yellow"}) / 0.035)
        + 3 * min(1.0, _colour_ratio(sea, {"white"}) / 0.025)
        + 3 * max(0.0, 1 - abs(centroid_x - 0.50) * 5)
    )
    return {
        "prompt_fidelity": (
            prompt_score,
            f"The tower region is {tower_light:.0%} white/yellow and the weather "
            f"field is {environment_dark:.0%} navy/storm grey.",
        ),
        "representation_accuracy": (
            clarity_score,
            f"Tower-region contrast is {tower_contrast:.0f}/128 with "
            f"{tower_light:.0%} light focal pixels.",
        ),
        "depth_lighting": (
            clarity_score,
            f"Tower contrast is {tower_contrast:.0f}/128 and light focal pixels "
            f"cover {tower_light:.0%} of the tower region.",
        ),
        "material_rendering": (
            storm_score,
            f"Edge density differs across storm sky ({sky_edges:.1%}) and "
            f"rough sea ({sea_edges:.1%}).",
        ),
        "fine_detail": (
            finish_score,
            f"Foreground centre is ({centroid_x:.0%}, {centroid_y:.0%}); "
            f"light accents cover {coverage:.0%} of the canvas.",
        ),
        "originality": (
            colour_score,
            f"{palette_count} visible palette colours define this candidate's "
            "disciplined storm treatment.",
        ),
    }


def _score_guinea_pig(canvas: Image.Image) -> dict[str, tuple[float, str]]:
    animal = _crop(canvas, (150, 160, 440, 310))
    face = _crop(canvas, (130, 185, 220, 210))
    cup = _crop(canvas, (75, 245, 620, 305))
    fur_ratio = _colour_ratio(animal, {"tan", "brown", "cream", "white"})
    cup_ratio = _colour_ratio(cup, {"teal", "violet", "coral", "navy", "green"})
    eye_ratio = _colour_ratio(face, {"ink", "white"})
    pink_ratio = _colour_ratio(face, {"coral", "pink"})
    animal_contrast = _contrast(animal)
    cup_edges = _edge_density(cup)
    fur_edges = _edge_density(animal)
    centroid_x, centroid_y, coverage = _foreground_geometry(canvas, {"cream"})
    colours = _present_palette_count(canvas)
    fidelity = _clamp(
        4.5 * min(1.0, fur_ratio / 0.45)
        + 3.5 * min(1.0, cup_ratio / 0.35)
        + 2.0 * min(1.0, eye_ratio / 0.025)
    )
    accuracy = _clamp(
        4 * min(1.0, eye_ratio / 0.035)
        + 2 * min(1.0, pink_ratio / 0.02)
        + 4 * min(1.0, fur_ratio / 0.50)
    )
    composition = _clamp(
        10
        - abs(centroid_x - 0.50) * 16
        - abs(centroid_y - 0.57) * 12
        - abs(coverage - 0.35) * 12
    )
    depth = _clamp(
        6 * min(1.0, animal_contrast / 65)
        + 4 * min(1.0, cup_edges / 0.08)
    )
    material = _clamp(
        5 * min(1.0, fur_edges / 0.09)
        + 5 * min(1.0, cup_edges / 0.08)
    )
    detail = _clamp(
        4 * min(1.0, eye_ratio / 0.04)
        + 3 * min(1.0, fur_edges / 0.10)
        + 3 * min(1.0, cup_edges / 0.09)
    )
    originality = _clamp(3 + min(7, colours * 0.75))
    return {
        "prompt_fidelity": (
            fidelity,
            f"The animal region is {fur_ratio:.0%} fur colours and the cuddle-cup "
            f"region is {cup_ratio:.0%} padded accent colour.",
        ),
        "representation_accuracy": (
            accuracy,
            f"The face contains {eye_ratio:.1%} eye/outline pixels and "
            f"{pink_ratio:.1%} warm muzzle/ear pixels.",
        ),
        "composition": (
            composition,
            f"Foreground centre is ({centroid_x:.0%}, {centroid_y:.0%}) with "
            f"{coverage:.0%} canvas coverage.",
        ),
        "depth_lighting": (
            depth,
            f"Animal contrast is {animal_contrast:.0f}/128 and cup edge density "
            f"is {cup_edges:.1%}.",
        ),
        "material_rendering": (
            material,
            f"Fur edge density is {fur_edges:.1%}, compared with {cup_edges:.1%} "
            "in the fabric region.",
        ),
        "fine_detail": (
            detail,
            f"Eye marks, fur edges, and fabric seams are independently visible "
            f"at densities of {eye_ratio:.1%}, {fur_edges:.1%}, and {cup_edges:.1%}.",
        ),
        "originality": (
            originality,
            f"{colours} visible palette families define the candidate's treatment.",
        ),
    }


def _score_generic(canvas: Image.Image) -> dict[str, tuple[float, str]]:
    contrast = _contrast(canvas)
    edges = _edge_density(canvas)
    colours = _present_palette_count(canvas)
    centroid_x, centroid_y, coverage = _foreground_geometry(canvas, {"white"})
    composition = _clamp(
        10 - abs(centroid_x - 0.5) * 16 - abs(centroid_y - 0.5) * 12
    )
    return {
        "prompt_fidelity": (
            _clamp(4 + colours * 0.7),
            f"{colours} visible palette colours establish differentiated forms.",
        ),
        "representation_accuracy": (
            _clamp(contrast / 10),
            f"Whole-canvas tonal contrast is {contrast:.0f}/128.",
        ),
        "composition": (
            composition,
            f"Visible centre is ({centroid_x:.0%}, {centroid_y:.0%}) with "
            f"{coverage:.0%} coverage.",
        ),
        "depth_lighting": (
            _clamp((contrast / 12) + coverage * 4),
            f"Tonal contrast is {contrast:.0f}/128 with {coverage:.0%} "
            "foreground coverage.",
        ),
        "material_rendering": (
            _clamp(colours * 0.8 + edges * 45),
            f"{colours} palette colours and {edges:.1%} edge density create "
            "surface differentiation.",
        ),
        "fine_detail": (
            _clamp(edges * 100),
            f"Visible edge density is {edges:.1%}.",
        ),
        "originality": (
            _clamp(3 + colours * 0.7),
            f"{colours} visible palette families establish a distinct treatment.",
        ),
    }


def _decision_summary(ranked: list[CandidateEvaluation]) -> str:
    winner = ranked[0]
    if len(ranked) == 1:
        return f"Candidate {winner.candidate_id} wins with {winner.total_score:.1f}/100."
    runner_up = ranked[1]
    runner_scores = {item.key: item for item in runner_up.criteria}
    advantages = sorted(
        (
            (
                item.score - runner_scores[item.key].score,
                item.label,
                item.score,
                runner_scores[item.key].score,
            )
            for item in winner.criteria
        ),
        reverse=True,
    )
    positive = [item for item in advantages if item[0] > 0.05][:2]
    if positive:
        detail = " and ".join(
            f"{label} ({winner_score:.1f} vs {runner_score:.1f})"
            for _, label, winner_score, runner_score in positive
        )
        runner_advantages = sorted(
            (
                (
                    runner_scores[item.key].score - item.score,
                    item.label,
                    runner_scores[item.key].score,
                    item.score,
                )
                for item in winner.criteria
                if runner_scores[item.key].score - item.score > 0.05
            ),
            reverse=True,
        )
        margin = winner.total_score - runner_up.total_score
        summary = (
            f"Candidate {winner.candidate_id} wins by {margin:.1f} points "
            f"({winner.total_score:.1f} vs {runner_up.total_score:.1f}). "
            f"Its lead on {detail}"
        )
        if runner_advantages:
            _, label, runner_score, winner_score = runner_advantages[0]
            summary += (
                f" narrowly outweighs {runner_up.candidate_id}'s {label} edge "
                f"({runner_score:.1f} vs {winner_score:.1f})."
            )
        else:
            summary += "."
        return summary
    return (
        f"Candidate {winner.candidate_id} wins with {winner.total_score:.1f}/100; "
        "the candidates tied on scored criteria, so the stable label order decided it."
    )


def _write_report(
    path: Path,
    prompt: str,
    base_seed: int,
    seeds: tuple[int, ...],
    rubric: tuple[RubricCriterion, ...],
    ranked: list[CandidateEvaluation],
    winner_id: str,
    decision: str,
    minimum_actions: int,
    target_actions: int,
    action_budget: int,
    review_budget: int,
    revision_budget: int,
    qualifier_ranked: list[CandidateEvaluation],
    diversity_contracts: tuple[dict[str, str], ...],
) -> Path:
    lines = [
        "# Variant Tournament Report",
        "",
        f"**Prompt:** {prompt}",
        f"**Base seed:** {base_seed}",
        f"**Candidate seeds:** {', '.join(str(seed) for seed in seeds)}",
        f"**Finalist budgets:** {minimum_actions} minimum / {target_actions} target / "
        f"{action_budget} maximum drawing actions; "
        f"{review_budget} review checkpoints; {revision_budget} correction actions",
        "**Judge input:** final complete-application screenshots only",
        "",
        "Candidate labels were assigned before judging. The scorer did not receive "
        "candidate seeds, canvas state, action logs, or review reports.",
        "",
        "## Qualification",
        "",
        "Every candidate first produced a bounded draft. The blind draft ranking was "
        f"{', '.join(item.candidate_id for item in qualifier_ranked)}; only the selected "
        "finalists were reproduced at the full detail target.",
        "",
        "| Candidate | Pose | Composition | Lighting | Rendering |",
        "| --- | --- | --- | --- | --- |",
    ]
    lines.extend(
        "| "
        + " | ".join(
            (
                chr(ord("A") + index),
                contract["pose"],
                contract["composition"],
                contract["lighting"],
                contract["rendering"],
            )
        )
        + " |"
        for index, contract in enumerate(diversity_contracts)
    )
    lines.extend(
        [
            "",
            "## Visible rubric",
            "",
            "| Criterion | Weight | Visible question |",
            "| --- | ---: | --- |",
        ]
    )
    lines.extend(
        f"| {item.label} | {item.weight}% | {item.visible_question} |"
        for item in rubric
    )
    lines.extend(
        [
            "",
            "## Result",
            "",
            decision,
            "",
            "| Rank | Candidate | Score | Final full-app screenshot |",
            "| ---: | --- | ---: | --- |",
        ]
    )
    for rank, candidate in enumerate(ranked, start=1):
        screenshot = _relative(path.parent, Path(candidate.screenshot))
        winner_mark = " — winner" if candidate.candidate_id == winner_id else ""
        lines.append(
            f"| {rank} | {candidate.candidate_id}{winner_mark} | "
            f"{candidate.total_score:.1f}/100 | [{screenshot}]({screenshot}) |"
        )
    for candidate in ranked:
        lines.extend(
            [
                "",
                f"## Candidate {candidate.candidate_id}",
                "",
            ]
        )
        for item in candidate.criteria:
            lines.extend(
                [
                    f"- **{item.label}: {item.score:.1f}/10** "
                    f"(weight {item.weight}%) — {item.evidence}",
                ]
            )
    lines.extend(
        [
            "",
            "## Preservation",
            "",
            "Every qualifier directory retains its prompt, seed metadata, action log, "
            "configured review checkpoints, complete-application screenshots, final PNG, "
            "GIF, MP4, review report, and quality gates. Finalists retain a second full-"
            "detail run. `winner.png` is a convenience copy; losing variants are not "
            "deleted.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _render_montage(
    path: Path,
    prompt: str,
    rubric: tuple[RubricCriterion, ...],
    ranked: list[CandidateEvaluation],
    winner_id: str,
    decision: str,
) -> Path:
    count = len(ranked)
    width = min(1800, max(1200, 70 + count * 500))
    card_gap = 18
    card_width = (width - 70 - card_gap * (count - 1)) // count
    height = 940
    background = (11, 18, 32)
    panel = (27, 39, 61)
    text_colour = (238, 244, 255)
    muted = (165, 180, 203)
    accent = (78, 232, 214)
    winner_colour = (88, 228, 168)
    image = Image.new("RGB", (width, height), background)
    draw = ImageDraw.Draw(image)
    title_font = _font(34, bold=True)
    heading_font = _font(23, bold=True)
    body_font = _font(17)
    small_font = _font(15)
    draw.text((35, 25), "AUTONOMOUS PAINT • VARIANT TOURNAMENT", font=title_font, fill=accent)
    draw.text((35, 72), f'Brief: “{prompt}”', font=body_font, fill=text_colour)
    rubric_line = "  •  ".join(f"{item.label} {item.weight}%" for item in rubric)
    draw.text((35, 105), rubric_line, font=small_font, fill=muted)

    for rank, candidate in enumerate(ranked, start=1):
        x = 35 + (rank - 1) * (card_width + card_gap)
        card = (x, 142, x + card_width, 690)
        outline = winner_colour if candidate.candidate_id == winner_id else (73, 94, 125)
        draw.rounded_rectangle(card, radius=12, fill=panel, outline=outline, width=4)
        heading = (
            f"#{rank}  CANDIDATE {candidate.candidate_id}"
            + ("  •  WINNER" if candidate.candidate_id == winner_id else "")
        )
        draw.text((x + 16, 158), heading, font=heading_font, fill=outline)
        with Image.open(candidate.screenshot) as source:
            screenshot = source.convert("RGB")
            screenshot.thumbnail((card_width - 32, 300), Image.Resampling.LANCZOS)
        screenshot_x = x + (card_width - screenshot.width) // 2
        screenshot_y = 202
        image.paste(screenshot, (screenshot_x, screenshot_y))
        y = screenshot_y + screenshot.height + 18
        draw.text(
            (x + 16, y),
            f"TOTAL  {candidate.total_score:.1f}/100",
            font=heading_font,
            fill=text_colour,
        )
        y += 38
        for item in candidate.criteria:
            draw.text(
                (x + 16, y),
                f"{item.label}: {item.score:.1f}/10  •  {item.weight}%",
                font=small_font,
                fill=text_colour,
            )
            y += 25

    draw.rounded_rectangle(
        (35, 720, width - 35, height - 32),
        radius=12,
        fill=(20, 31, 49),
        outline=winner_colour,
        width=3,
    )
    draw.text((55, 742), "VISIBLE DECISION SUMMARY", font=heading_font, fill=winner_colour)
    y = 782
    for line in _wrap_text(decision, body_font, width - 110):
        draw.text((55, y), line, font=body_font, fill=text_colour)
        y += 25
    y += 8
    note = (
        "Judging input: final complete-application screenshots only. "
        "All candidates and their recordings are preserved."
    )
    for line in _wrap_text(note, small_font, width - 110):
        draw.text((55, y), line, font=small_font, fill=muted)
        y += 22
    image.save(path, format="PNG")
    return path


def _preserve_references(source: Path | None, run_dir: Path) -> Path | None:
    cards = load_reference_manifest(source)
    if not cards:
        return None
    reference_dir = run_dir / "references"
    reference_dir.mkdir(parents=True, exist_ok=True)
    preserved: list[ReferenceCard] = []
    for index, card in enumerate(cards, start=1):
        image_path = ""
        if card.image_path and Path(card.image_path).is_file():
            destination = reference_dir / f"reference_{index:02d}.png"
            shutil.copyfile(card.image_path, destination)
            image_path = str(destination.relative_to(run_dir))
        preserved.append(
            ReferenceCard(
                card.title,
                card.source_url,
                card.note,
                image_path,
                card.search_query,
                card.rights_note,
            )
        )
    manifest = run_dir / "references.json"
    manifest.write_text(
        json.dumps({"references": [asdict(card) for card in preserved]}, indent=2),
        encoding="utf-8",
    )
    return manifest


def _crop(image: Image.Image, box: tuple[int, int, int, int]) -> Image.Image:
    x, y, width, height = box
    return image.crop((x, y, min(image.width, x + width), min(image.height, y + height)))


def _colour_ratio(image: Image.Image, names: set[str]) -> float:
    selected = {PALETTE[name] for name in names}
    counts = image.getcolors(maxcolors=image.width * image.height) or []
    matching = sum(count for count, colour in counts if colour in selected)
    return matching / max(1, image.width * image.height)


def _non_colour_ratio(image: Image.Image, background_names: set[str]) -> float:
    return 1 - _colour_ratio(image, background_names)


def _contrast(image: Image.Image) -> float:
    return float(ImageStat.Stat(image.convert("L")).stddev[0])


def _edge_density(image: Image.Image) -> float:
    histogram = image.convert("L").filter(ImageFilter.FIND_EDGES).histogram()
    strong = sum(histogram[32:])
    return strong / max(1, image.width * image.height)


def _present_palette_count(image: Image.Image) -> int:
    counts = image.getcolors(maxcolors=image.width * image.height) or []
    return sum(
        any(colour == palette_colour and count > 80 for count, colour in counts)
        for palette_colour in PALETTE.values()
    )


def _palette_entropy(image: Image.Image, names: tuple[str, ...]) -> float:
    counts = image.getcolors(maxcolors=image.width * image.height) or []
    by_colour = {colour: count for count, colour in counts}
    values = [by_colour.get(PALETTE[name], 0) for name in names]
    total = sum(values)
    if total == 0:
        return 0.0
    entropy = -sum(
        (value / total) * math.log2(value / total)
        for value in values
        if value
    )
    return entropy / math.log2(len(names))


def _foreground_geometry(
    image: Image.Image,
    background_names: set[str],
) -> tuple[float, float, float]:
    background = {PALETTE[name] for name in background_names}
    pixels = image.load()
    count = 0
    sum_x = 0
    sum_y = 0
    for y in range(image.height):
        for x in range(image.width):
            if pixels[x, y] not in background:
                count += 1
                sum_x += x
                sum_y += y
    if count == 0:
        return 0.5, 0.5, 0.0
    return (
        sum_x / count / max(1, image.width - 1),
        sum_y / count / max(1, image.height - 1),
        count / (image.width * image.height),
    )


def _clamp(value: float) -> float:
    return max(0.0, min(10.0, value))


def _relative(base: Path, target: Path) -> str:
    return target.resolve().relative_to(base.resolve()).as_posix()


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    filename = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    path = Path("/usr/share/fonts/truetype/dejavu") / filename
    try:
        return ImageFont.truetype(str(path), size)
    except OSError:
        return ImageFont.load_default()


def _wrap_text(
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    width: int,
) -> list[str]:
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    lines: list[str] = []
    line = ""
    for word in text.split():
        candidate = f"{line} {word}".strip()
        if line and probe.textbbox((0, 0), candidate, font=font)[2] > width:
            lines.append(line)
            line = word
        else:
            line = candidate
    if line:
        lines.append(line)
    return lines
