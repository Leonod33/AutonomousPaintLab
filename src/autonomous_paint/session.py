"""Run lifecycle, logging, budgets, screenshots, and persistence."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from PIL import Image, ImageChops

from .app import PaintApplication, UIResult
from .constants import CANVAS_ORIGIN
from .references import ReferenceCard
from .recording import encode_recordings, save_frame, save_png
from .review import ReviewFinding


@dataclass(frozen=True)
class VisibleAction:
    kind: str
    start: tuple[int, int]
    end: tuple[int, int] | None = None


@dataclass(frozen=True)
class DecisionSummary:
    goal: str
    selected_tool: str
    intended_action: str
    visual_assessment: str


class PaintRun:
    def __init__(
        self,
        run_dir: Path,
        prompt: str,
        seed: int,
        decision_source: str,
        action_budget: int = 100,
        review_budget: int = 3,
        references: tuple[ReferenceCard, ...] = (),
    ) -> None:
        self.run_dir = run_dir
        self.prompt = prompt
        self.seed = seed
        self.decision_source = decision_source
        self.action_budget = action_budget
        self.review_budget = review_budget
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.observation_dir = self.run_dir / "screenshots"
        self.frame_dir = self.run_dir / "frames"
        self.output_path = self.run_dir / "final.png"
        self.events: list[dict[str, Any]] = []
        self.frame_index = 0
        self.app = PaintApplication(
            output_path=self.output_path,
            prompt=prompt,
            seed=seed,
            action_budget=action_budget,
            review_budget=review_budget,
            references=references,
        )
        self._write_static_metadata()
        self.capture("initial")

    def _write_static_metadata(self) -> None:
        (self.run_dir / "prompt.txt").write_text(self.prompt + "\n", encoding="utf-8")
        self._write_json(
            self.run_dir / "metadata.json",
            {
                "prompt": self.prompt,
                "seed": self.seed,
                "decision_source": self.decision_source,
                "decision_input": (
                    "complete_application_screenshot_only"
                    if "vision" in self.decision_source
                    else "structured_canvas_state"
                ),
                "action_budget": self.action_budget,
                "review_budget": self.review_budget,
                "reference_count": len(self.app.references),
                "reference_preview_count": sum(
                    1
                    for reference in self.app.references
                    if reference.image_path and Path(reference.image_path).is_file()
                ),
            },
        )

    def execute(
        self,
        action: VisibleAction,
        summary: DecisionSummary,
    ) -> dict[str, Any]:
        if self._would_consume_budget(action) and self.app.drawing_actions >= self.action_budget:
            raise RuntimeError("drawing action budget exhausted")
        self.app.set_review_findings(())
        self.app.set_summary(
            goal=summary.goal,
            tool=summary.selected_tool,
            intended_action=summary.intended_action,
            assessment=summary.visual_assessment,
        )
        if action.kind == "click":
            result = self.app.click(action.start)
        elif action.kind == "drag" and action.end is not None:
            result = self.app.drag(action.start, action.end)
        else:
            raise ValueError(f"invalid visible action: {action}")
        if result.drawing_applied:
            self.app.drawing_actions += 1
        event = {
            "sequence": len(self.events),
            "type": "ui_action",
            "action": asdict(action),
            "summary": asdict(summary),
            "result": asdict(result),
            "drawing_actions": self.app.drawing_actions,
            "review_checkpoints": self.app.review_checkpoints,
        }
        self.events.append(event)
        screenshot = self.capture(f"action_{len(self.events):03d}")
        event["screenshot"] = str(screenshot)
        self._flush_log()
        return {
            "applied": result.applied,
            "drawing_applied": result.drawing_applied,
            "control": result.control,
            "saved_path": result.saved_path,
            "screenshot_path": str(screenshot.resolve()),
            "drawing_actions": self.app.drawing_actions,
            "reviews": self.app.review_checkpoints,
        }

    def review(
        self,
        assessment: str,
        findings: tuple[ReviewFinding, ...] = (),
        goal: str = "Review the complete canvas.",
    ) -> Path:
        if self.app.review_checkpoints >= self.review_budget:
            raise RuntimeError("review checkpoint budget exhausted")
        self.app.review_checkpoints += 1
        if not findings:
            findings = (
                ReviewFinding(
                    f"R{self.app.review_checkpoints}-1",
                    "Whole canvas",
                    (0, 0, self.app.model.width, self.app.model.height),
                    assessment,
                    "Make the single highest-impact visible correction.",
                    "medium",
                    0.6,
                ),
            )
        self.app.set_review_findings(findings)
        self.app.set_summary(
            goal=goal,
            intended_action="Pause drawing and inspect the visible canvas.",
            assessment=assessment,
        )
        self.events.append(
            {
                "sequence": len(self.events),
                "type": "review",
                "assessment": assessment,
                "findings": [finding.to_dict() for finding in findings],
                "drawing_actions": self.app.drawing_actions,
                "review_checkpoints": self.app.review_checkpoints,
            }
        )
        screenshot = self.capture(f"review_{self.app.review_checkpoints}")
        self.events[-1]["screenshot"] = str(screenshot)
        self._flush_log()
        return screenshot

    def capture(self, label: str) -> Path:
        self.observation_dir.mkdir(parents=True, exist_ok=True)
        screenshot = self.observation_dir / f"{self.frame_index:06d}_{label}.png"
        surface = self.app.render()
        save_png(surface, screenshot)
        save_frame(surface, self.frame_dir, self.frame_index)
        self.frame_index += 1
        return screenshot.resolve()

    def finalize(self, fps: int = 3) -> dict[str, str]:
        if not self.output_path.exists():
            raise RuntimeError("final PNG was not saved through the visible Save control")
        final_screenshot = self.capture("final")
        gif_path = self.run_dir / "recording.gif"
        mp4_path = self.run_dir / "recording.mp4"
        encode_recordings(self.frame_dir, gif_path, mp4_path, fps=fps)
        review_report = self._write_review_report(final_screenshot)
        self._flush_log()
        return {
            "final_png": str(self.output_path.resolve()),
            "gif": str(gif_path.resolve()),
            "mp4": str(mp4_path.resolve()),
            "action_log": str((self.run_dir / "actions.json").resolve()),
            "review_report": str(review_report.resolve()),
        }

    def to_payload(self) -> dict[str, Any]:
        return {
            "run_dir": str(self.run_dir),
            "prompt": self.prompt,
            "seed": self.seed,
            "decision_source": self.decision_source,
            "action_budget": self.action_budget,
            "review_budget": self.review_budget,
            "events": self.events,
            "frame_index": self.frame_index,
            "app": self.app.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "PaintRun":
        run = cls.__new__(cls)
        run.run_dir = Path(payload["run_dir"])
        run.prompt = payload["prompt"]
        run.seed = int(payload["seed"])
        run.decision_source = payload["decision_source"]
        run.action_budget = int(payload["action_budget"])
        run.review_budget = int(payload["review_budget"])
        run.observation_dir = run.run_dir / "screenshots"
        run.frame_dir = run.run_dir / "frames"
        run.output_path = run.run_dir / "final.png"
        run.events = list(payload["events"])
        run.frame_index = int(payload["frame_index"])
        run.app = PaintApplication.from_payload(payload["app"])
        return run

    def _write_review_report(self, final_screenshot: Path | None = None) -> Path:
        path = self.run_dir / "review_report.md"
        lines = [
            "# Visual Review Report",
            "",
            f"**Prompt:** {self.prompt}",
            f"**Seed:** {self.seed}",
            f"**Mode:** `{self.decision_source}`",
            "",
        ]
        reviews = [event for event in self.events if event.get("type") == "review"]
        for index, event in enumerate(reviews, start=1):
            lines.extend(
                [
                    f"## Checkpoint {index}",
                    "",
                    str(event["assessment"]),
                    "",
                ]
            )
            for finding in event.get("findings", []):
                lines.extend(
                    [
                        f"### {finding['finding_id']}: {finding['area']}",
                        "",
                        f"- **Priority:** {finding['priority']} ({finding['confidence']:.0%} confidence)",
                        f"- **Region:** `{finding['region']}`",
                        f"- **Needs improving:** {finding['issue']}",
                        f"- **Suggested improvement:** {finding['suggestion']}",
                    ]
                )
                if finding.get("evidence"):
                    lines.append(f"- **Visible evidence:** {finding['evidence']}")
                lines.append("")
            screenshot = event.get("screenshot")
            if screenshot:
                relative = self._relative_artifact(Path(screenshot))
                lines.extend(
                    [f"Review screenshot: [{relative}]({relative})", ""]
                )

        last_review_sequence = max(
            (event["sequence"] for event in reviews),
            default=-1,
        )
        revisions = [
            event
            for event in self.events
            if event.get("sequence", -1) > last_review_sequence
            and (
                (
                    event.get("type") == "ui_action"
                    and event.get("result", {}).get("drawing_applied")
                )
                or event.get("type") == "structured_action"
            )
        ]
        final_findings = reviews[-1].get("findings", []) if reviews else []
        priority_rank = {"high": 3, "medium": 2, "low": 1}
        eligible = [
            finding
            for finding in final_findings
            if finding.get("priority") in {"high", "medium"}
            and float(finding.get("confidence", 0.0)) >= 0.6
        ]
        trigger = (
            max(
                eligible,
                key=lambda finding: (
                    priority_rank.get(str(finding.get("priority")), 0),
                    float(finding.get("confidence", 0.0)),
                ),
            )
            if eligible
            else None
        )
        lines.extend(["## Revision pass", ""])
        if trigger is not None:
            lines.extend(
                [
                    f"**Triggered by:** {trigger['finding_id']} — {trigger['area']} "
                    f"({trigger['priority']}, {trigger['confidence']:.0%} confidence)",
                    "",
                    f"**Planned correction:** {trigger['suggestion']}",
                    "",
                ]
            )
        if revisions:
            for event in revisions:
                summary = event.get("summary", {})
                screenshot = event.get("screenshot")
                artifact = (
                    self._relative_artifact(Path(screenshot))
                    if screenshot
                    else ""
                )
                suffix = f" ([action screenshot]({artifact}))" if artifact else ""
                lines.append(
                    f"- {summary.get('intended_action', 'Visible revision action')}{suffix}"
                )
        else:
            lines.append("- No drawing revision was applied after the final checkpoint.")
        deferred = [
            finding
            for finding in final_findings
            if finding not in eligible
        ]
        for finding in deferred:
            lines.append(
                f"- Intentionally deferred {finding['finding_id']} "
                f"({finding['priority']}, {finding['confidence']:.0%}): "
                "outside the high/medium ≥60% bounded-revision rule."
            )
        lines.extend(
            [
                "",
                "## Before and after",
                "",
            ]
        )
        before_screenshot = self._last_unannotated_screenshot_before_review(reviews)
        if final_screenshot is not None:
            after_relative = self._relative_artifact(final_screenshot)
            lines.append(f"After screenshot: [{after_relative}]({after_relative})")
        lines.append("Final canvas: [final.png](final.png)")
        if trigger is not None and before_screenshot is not None and self.output_path.exists():
            lines.extend(
                [
                    "",
                    f"**Observed outcome:** {self._revision_outcome(before_screenshot, trigger)}",
                ]
            )
        lines.extend(
            [
                "",
                "Review overlays are annotations only and never alter the saved canvas.",
                "",
            ]
        )
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    def _last_unannotated_screenshot_before_review(
        self,
        reviews: list[dict[str, Any]],
    ) -> Path | None:
        if not reviews:
            return None
        review_sequence = reviews[-1].get("sequence", -1)
        candidates = [
            event
            for event in self.events
            if event.get("sequence", -1) < review_sequence
            and event.get("type") in {"ui_action", "structured_action"}
            and event.get("screenshot")
        ]
        return Path(candidates[-1]["screenshot"]) if candidates else None

    def _revision_outcome(
        self,
        before_screenshot: Path,
        trigger: dict[str, Any],
    ) -> str:
        try:
            with Image.open(before_screenshot) as source:
                before = source.convert("RGB")
                ox, oy = CANVAS_ORIGIN
                before = before.crop(
                    (ox, oy, ox + self.app.model.width, oy + self.app.model.height)
                )
            with Image.open(self.output_path) as source:
                after = source.convert("RGB")
            difference = ImageChops.difference(before, after)
            changed_total = self._changed_pixel_count(difference)
            x, y, width, height = trigger["region"]
            region = difference.crop((x, y, x + width, y + height))
            changed_region = self._changed_pixel_count(region)
            if changed_total and changed_region == changed_total:
                scope = "all changed pixels stayed inside the targeted region"
            else:
                scope = (
                    f"{changed_region} of {changed_total} changed pixels were "
                    "inside the targeted region"
                )
            return (
                f"The saved revision changed {changed_total} visible pixels; {scope}. "
                f"This directly addresses {trigger['finding_id']} while preserving "
                "the rest of the composition."
            )
        except (OSError, ValueError, KeyError, TypeError):
            return (
                f"The saved revision action targets {trigger['finding_id']}; "
                "compare the linked before/review and after screenshots."
            )

    @staticmethod
    def _changed_pixel_count(difference: Image.Image) -> int:
        histogram = difference.convert("L").histogram()
        return difference.width * difference.height - histogram[0]

    def _relative_artifact(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self.run_dir.resolve()).as_posix()
        except ValueError:
            return path.name

    def _would_consume_budget(self, action: VisibleAction) -> bool:
        if self.app.canvas_rect.collidepoint(action.start):
            return True
        return (
            action.kind == "click"
            and self.app._tool_rects["clear"].collidepoint(action.start)
        )

    def _flush_log(self) -> None:
        self._write_json(self.run_dir / "actions.json", self.events)

    @staticmethod
    def _write_json(path: Path, value: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{path.name}.",
            dir=path.parent,
            text=True,
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(value, handle, indent=2)
            os.replace(temporary, path)
        except BaseException:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            raise
