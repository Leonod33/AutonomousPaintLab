"""Run lifecycle, logging, budgets, screenshots, and persistence."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from .app import PaintApplication, UIResult
from .recording import encode_recordings, save_frame


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
            },
        )

    def execute(
        self,
        action: VisibleAction,
        summary: DecisionSummary,
    ) -> dict[str, Any]:
        if self._would_consume_budget(action) and self.app.drawing_actions >= self.action_budget:
            raise RuntimeError("drawing action budget exhausted")
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

    def review(self, assessment: str, goal: str = "Review the complete canvas.") -> Path:
        if self.app.review_checkpoints >= self.review_budget:
            raise RuntimeError("review checkpoint budget exhausted")
        self.app.review_checkpoints += 1
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
        import pygame

        pygame.image.save(surface, screenshot)
        save_frame(surface, self.frame_dir, self.frame_index)
        self.frame_index += 1
        return screenshot.resolve()

    def finalize(self, fps: int = 3) -> dict[str, str]:
        if not self.output_path.exists():
            raise RuntimeError("final PNG was not saved through the visible Save control")
        self.capture("final")
        gif_path = self.run_dir / "recording.gif"
        mp4_path = self.run_dir / "recording.mp4"
        encode_recordings(self.frame_dir, gif_path, mp4_path, fps=fps)
        self._flush_log()
        return {
            "final_png": str(self.output_path.resolve()),
            "gif": str(gif_path.resolve()),
            "mp4": str(mp4_path.resolve()),
            "action_log": str((self.run_dir / "actions.json").resolve()),
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
