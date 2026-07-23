"""Human-readable, region-specific visual review findings."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from PIL import Image

Region = tuple[int, int, int, int]


@dataclass(frozen=True)
class ReviewFinding:
    """One inspectable claim about a visible part of the artwork."""

    finding_id: str
    area: str
    region: Region
    issue: str
    suggestion: str
    priority: str = "medium"
    confidence: float = 0.75
    evidence: str = ""

    def __post_init__(self) -> None:
        if self.priority not in {"high", "medium", "low"}:
            raise ValueError("review priority must be high, medium, or low")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("review confidence must be between zero and one")
        x, y, width, height = self.region
        if min(x, y, width, height) < 0 or width < 1 or height < 1:
            raise ValueError("review region must be a positive canvas rectangle")
        if not all((self.area, self.issue, self.suggestion)):
            raise ValueError("review area, issue, and suggestion are required")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ReviewFinding":
        region = value.get("region")
        if not isinstance(region, (list, tuple)) or len(region) != 4:
            raise ValueError("review finding region must contain x, y, width, height")
        return cls(
            finding_id=str(value.get("finding_id", "finding")),
            area=str(value["area"]),
            region=tuple(int(number) for number in region),
            issue=str(value["issue"]),
            suggestion=str(value["suggestion"]),
            priority=str(value.get("priority", "medium")).lower(),
            confidence=float(value.get("confidence", 0.75)),
            evidence=str(value.get("evidence", "")),
        )


def generate_review_findings(
    screenshot: Path,
    canvas_origin: tuple[int, int],
    canvas_size: tuple[int, int],
    prompt: str,
    checkpoint: int,
) -> tuple[ReviewFinding, ...]:
    """Create deterministic findings from screenshot pixels and prompt semantics."""
    width, height = canvas_size
    metrics = _visible_metrics(screenshot, canvas_origin, canvas_size)
    normalized = prompt.lower()
    identifier = f"R{checkpoint}"

    if "robot" in normalized:
        if checkpoint == 1:
            return (
                ReviewFinding(
                    f"{identifier}-1",
                    "Main character silhouette",
                    (110, 70, 390, 440),
                    "The setting is established, but the robot still blends into the broad sky area.",
                    "Complete the dark outer silhouette before adding small decorative details.",
                    "high",
                    0.84,
                    _evidence(
                        "The central sky remains a broad uninterrupted light shape, "
                        "with no equally strong dark character outline yet.",
                        metrics,
                    ),
                ),
            )
        flower_issue = (
            "The first square flower establishes the motif, but the remaining bare stems feel empty and evenly spaced."
            if checkpoint == 2
            else "The square flowers are legible, though their repeated spacing makes the garden feel slightly mechanical."
        )
        flower_suggestion = (
            "Complete the remaining blossoms and vary at least one height while retaining the square motif."
            if checkpoint == 2
            else "Keep the square motif but vary one height or colour accent if the action budget allows."
        )
        return (
            ReviewFinding(
                f"{identifier}-1",
                "Robot face and expression",
                (210, 105, 210, 190),
                "The eyes read clearly, but the mouth is a narrow dark mark and feels less cheerful than the rest of the design.",
                "Add one short warm highlight at the smile so the expression becomes the focal detail.",
                "high" if checkpoint >= 3 else "medium",
                0.88,
                _evidence(
                    "The mouth is a single thin dark horizontal stroke beneath two "
                    "large bright circular eyes.",
                    metrics,
                ),
            ),
            ReviewFinding(
                f"{identifier}-2",
                "Flower grouping",
                (445, 300, 310, 185),
                flower_issue,
                flower_suggestion,
                "low",
                0.69,
                "The visible square blossoms sit at near-even intervals along the "
                "same horizontal band.",
            ),
        )

    if "lighthouse" in normalized:
        if checkpoint == 1:
            return (
                ReviewFinding(
                    f"{identifier}-1",
                    "Storm composition",
                    (0, 0, width, height),
                    "The sea and sky divide is clear, but the focal structure is not yet strong enough to anchor the scene.",
                    "Finish the bright central lighthouse before adding more rain or wave texture.",
                    "high",
                    0.86,
                    _evidence(
                        "The sea and sky already form large horizontal bands, while "
                        "the central tower shape is still incomplete.",
                        metrics,
                    ),
                ),
            )
        return (
            ReviewFinding(
                f"{identifier}-1",
                "Lighthouse against the sea",
                (285, 120, 230, 430),
                "The lighthouse reads well, but its lower edge competes with similarly pale wave marks.",
                "Add one brighter foreground foam stroke that leads toward the tower without crossing its outline.",
                "high" if checkpoint >= 3 else "medium",
                0.83,
                _evidence(
                    "Several pale wave marks touch the visual band around the "
                    "tower base, reducing separation at its lower edge.",
                    metrics,
                ),
            ),
            ReviewFinding(
                f"{identifier}-2",
                "Beacon direction",
                (420, 80, 330, 160),
                "The beam is visible, though the large empty area around its tip weakens the sense of weather.",
                "Retain the empty space; only add a small rain accent if the beam still feels detached.",
                "low",
                0.64,
                "The yellow beam remains isolated from most storm strokes.",
            ),
        )

    return (
        ReviewFinding(
            f"{identifier}-1",
            "Overall composition",
            (0, 0, width, height),
            "The image is readable, but the strongest contrast is not clearly concentrated in one focal area.",
            "Choose the intended subject and add one small high-contrast accent there.",
            "medium",
            0.68,
            _evidence(
                "Dark and light marks are distributed across the canvas without "
                "one small region carrying a unique contrast accent.",
                metrics,
            ),
        ),
    )


def _evidence(visible_claim: str, metrics: str) -> str:
    """Keep the human-visible claim primary and the coarse audit secondary."""
    return f"{visible_claim} {metrics}"


def _visible_metrics(
    screenshot: Path,
    canvas_origin: tuple[int, int],
    canvas_size: tuple[int, int],
) -> str:
    with Image.open(screenshot) as source:
        image = source.convert("RGB")
        x, y = canvas_origin
        width, height = canvas_size
        canvas = image.crop((x, y, x + width, y + height))
        colours = canvas.getcolors(maxcolors=width * height) or []
        light = sum(count for count, colour in colours if sum(colour) / 3 >= 185)
        dark = sum(count for count, colour in colours if sum(colour) / 3 <= 90)
        total = max(1, width * height)
        return (
            f"Visible pixel audit: {len(colours)} exact colours; "
            f"{light / total:.0%} light and {dark / total:.0%} dark."
        )
