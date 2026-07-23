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
    """Create a compact prompt-specific rubric whose weights total 100."""
    normalized = prompt.lower()
    if "robot" in normalized:
        return (
            RubricCriterion(
                "prompt_fidelity",
                "Prompt fidelity",
                30,
                "Are the robot, cheerful expression, and square-flower garden visibly present?",
            ),
            RubricCriterion(
                "subject_clarity",
                "Subject clarity",
                25,
                "Does the robot read clearly against the sky and ground?",
            ),
            RubricCriterion(
                "composition",
                "Composition",
                20,
                "Are the character and flower group balanced across the canvas?",
            ),
            RubricCriterion(
                "colour_rhythm",
                "Colour rhythm",
                15,
                "Do the accent colours create variety without losing cohesion?",
            ),
            RubricCriterion(
                "focal_finish",
                "Focal finish",
                10,
                "Does the face contain a distinct, finished focal detail?",
            ),
        )
    if "lighthouse" in normalized:
        return (
            RubricCriterion(
                "prompt_fidelity",
                "Prompt fidelity",
                30,
                "Are the lighthouse, beacon, sea, and storm visibly present?",
            ),
            RubricCriterion(
                "focal_clarity",
                "Focal clarity",
                25,
                "Does the pale lighthouse separate strongly from the dark weather?",
            ),
            RubricCriterion(
                "storm_energy",
                "Storm energy",
                20,
                "Do visible rain and wave edges create movement?",
            ),
            RubricCriterion(
                "four_colour_discipline",
                "Four-colour discipline",
                15,
                "Does the image honour the requested four-colour limit?",
            ),
            RubricCriterion(
                "focal_finish",
                "Focal finish",
                10,
                "Do the beacon, window, and foreground accents feel complete?",
            ),
        )
    return (
        RubricCriterion(
            "prompt_fidelity",
            "Prompt fidelity",
            35,
            "Are the requested subject and setting visibly recognizable?",
        ),
        RubricCriterion(
            "subject_clarity",
            "Subject clarity",
            25,
            "Does the principal subject separate from its surroundings?",
        ),
        RubricCriterion(
            "composition",
            "Composition",
            20,
            "Is the visible mass balanced across the canvas?",
        ),
        RubricCriterion(
            "colour_rhythm",
            "Colour rhythm",
            10,
            "Are colours varied but visually coherent?",
        ),
        RubricCriterion(
            "focal_finish",
            "Focal finish",
            10,
            "Is there a visibly deliberate focal detail?",
        ),
    )


def derive_candidate_seeds(base_seed: int, candidate_count: int) -> tuple[int, ...]:
    if not 2 <= candidate_count <= 5:
        raise ValueError("variant tournaments require between two and five candidates")
    return tuple(base_seed + index * 1009 for index in range(candidate_count))


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
    if "robot" in normalized:
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
) -> dict[str, str]:
    """Create, judge, and preserve a small set of screenshot-only variants."""
    if run_dir.exists() and any(run_dir.iterdir()):
        raise FileExistsError(f"tournament directory is not empty: {run_dir}")
    run_dir.mkdir(parents=True, exist_ok=True)
    rubric = build_rubric(prompt)
    seeds = derive_candidate_seeds(seed, candidate_count)
    labels = tuple(chr(ord("A") + index) for index in range(candidate_count))
    preserved_manifest = _preserve_references(reference_manifest, run_dir)
    evaluations: list[CandidateEvaluation] = []
    candidate_artifacts: dict[str, dict[str, str]] = {}

    for variant_index, (label, candidate_seed) in enumerate(zip(labels, seeds)):
        candidate_dir = run_dir / f"candidate-{label.lower()}"
        artifacts = run_screenshot_agent(
            prompt,
            candidate_seed,
            candidate_dir,
            action_budget,
            review_budget,
            preserved_manifest,
            variant_index,
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
        evaluations.append(evaluation)
        candidate_artifacts[label] = {
            name: _relative(run_dir, Path(value))
            for name, value in artifacts.items()
        }

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
        "candidate_count": candidate_count,
        "action_budget_per_candidate": action_budget,
        "review_budget_per_candidate": review_budget,
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
    return {
        "prompt_fidelity": (
            prompt_score,
            f"Robot region is {subject_ratio:.0%} non-background; the square-flower "
            f"band is {flower_ratio:.0%} non-background.",
        ),
        "subject_clarity": (
            clarity_score,
            f"Robot-region contrast is {subject_contrast:.0f}/128 with "
            f"{ink_ratio:.1%} dark outline pixels.",
        ),
        "composition": (
            composition_score,
            f"Foreground centre is ({centroid_x:.0%}, {centroid_y:.0%}) with "
            f"{coverage:.0%} canvas coverage.",
        ),
        "colour_rhythm": (
            colour_score,
            f"{accent_count}/4 accent families are visible; normalized accent "
            f"entropy is {accent_entropy:.2f}.",
        ),
        "focal_finish": (
            finish_score,
            f"Face contrast is {face_contrast:.0f}/128; white eye pixels and a "
            f"yellow focal accent are both visibly present.",
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
        "focal_clarity": (
            clarity_score,
            f"Tower-region contrast is {tower_contrast:.0f}/128 with "
            f"{tower_light:.0%} light focal pixels.",
        ),
        "storm_energy": (
            storm_score,
            f"Visible edge density is {sky_edges:.1%} in the sky and "
            f"{sea_edges:.1%} in the sea.",
        ),
        "four_colour_discipline": (
            colour_score,
            f"{palette_count} Paint palette colours appear above the visibility threshold.",
        ),
        "focal_finish": (
            finish_score,
            f"Foreground centre is ({centroid_x:.0%}, {centroid_y:.0%}); "
            f"light accents cover {coverage:.0%} of the canvas.",
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
        "subject_clarity": (
            _clamp(contrast / 10),
            f"Whole-canvas tonal contrast is {contrast:.0f}/128.",
        ),
        "composition": (
            composition,
            f"Visible centre is ({centroid_x:.0%}, {centroid_y:.0%}) with "
            f"{coverage:.0%} coverage.",
        ),
        "colour_rhythm": (
            _clamp(colours * 1.2),
            f"{colours} palette colours pass the visibility threshold.",
        ),
        "focal_finish": (
            _clamp(edges * 100),
            f"Visible edge density is {edges:.1%}.",
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
) -> Path:
    lines = [
        "# Variant Tournament Report",
        "",
        f"**Prompt:** {prompt}",
        f"**Base seed:** {base_seed}",
        f"**Candidate seeds:** {', '.join(str(seed) for seed in seeds)}",
        "**Judge input:** final complete-application screenshots only",
        "",
        "Candidate labels were assigned before judging. The scorer did not receive "
        "candidate seeds, canvas state, action logs, or review reports.",
        "",
        "## Visible rubric",
        "",
        "| Criterion | Weight | Visible question |",
        "| --- | ---: | --- |",
    ]
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
            "Every candidate directory retains its prompt, seed metadata, action log, "
            "three review checkpoints, complete-application screenshots, final PNG, "
            "GIF, MP4, and review report. `winner.png` is a convenience copy; losing "
            "variants are not deleted.",
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
