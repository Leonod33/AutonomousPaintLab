"""Structured control and strict screenshot-only agent runners."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from .constants import PALETTE
from .plans import ArtPlan, PlanAction, make_plan
from .references import load_reference_manifest
from .review import ReviewFinding, generate_review_findings
from .session import DecisionSummary, PaintRun, VisibleAction
from .vision import (
    LocatedInterface,
    assess_canvas,
    canvas_point,
    locate_interface,
)


def run_structured_control(
    prompt: str,
    seed: int,
    run_dir: Path,
    action_budget: int = 100,
    review_budget: int = 3,
    reference_manifest: Path | None = None,
) -> dict[str, str]:
    """Apply exact model commands to verify drawing logic; never label as vision."""
    plan = make_plan(prompt, seed)
    if len(plan.actions) + len(plan.revision_actions) > action_budget:
        raise ValueError("plan exceeds drawing action budget")
    run = PaintRun(
        run_dir,
        prompt,
        seed,
        "structured_state",
        action_budget,
        review_budget,
        load_reference_manifest(reference_manifest),
    )
    run.app.set_summary(phase="STRUCTURED-STATE CONTROL")
    checkpoints = _checkpoint_indices(len(plan.actions), review_budget)
    for index, action in enumerate(plan.actions, start=1):
        screenshot = _apply_structured(run, action)
        if index in checkpoints:
            checkpoint = checkpoints.index(index) + 1
            findings = generate_review_findings(
                screenshot,
                (20, 136),
                (760, 600),
                prompt,
                checkpoint,
            )
            run.review(
                f"Structured checkpoint {checkpoint}: "
                f"{run.app.model.colour_count()} exact canvas colours present.",
                findings,
            )
    for action in plan.revision_actions[:3]:
        _apply_structured(run, action)
    run.app.model.save(run.output_path)
    run.capture("saved")
    return run.finalize()


class VisibleBridge(Protocol):
    def act(
        self,
        action: VisibleAction,
        summary: DecisionSummary,
    ) -> tuple[Path, dict[str, object]]: ...

    def review(
        self,
        assessment: str,
        findings: tuple[ReviewFinding, ...],
    ) -> Path: ...

    def finish(self) -> dict[str, str]: ...


class InProcessVisibleBridge:
    """Expose screenshots and UI actions, withholding the PaintRun object."""

    def __init__(self, run: PaintRun) -> None:
        self.__run = run

    def act(
        self,
        action: VisibleAction,
        summary: DecisionSummary,
    ) -> tuple[Path, dict[str, object]]:
        result = self.__run.execute(action, summary)
        return Path(str(result["screenshot_path"])), result

    def review(
        self,
        assessment: str,
        findings: tuple[ReviewFinding, ...],
    ) -> Path:
        return self.__run.review(assessment, findings)

    def finish(self) -> dict[str, str]:
        return self.__run.finalize()


class ScreenshotPaintAgent:
    """Plan from a prompt, observe only PNGs, and emit visible UI actions."""

    def run(
        self,
        prompt: str,
        seed: int,
        initial_screenshot: Path,
        bridge: VisibleBridge,
        action_budget: int = 100,
        review_budget: int = 3,
    ) -> dict[str, str]:
        plan = make_plan(prompt, seed)
        if len(plan.actions) + len(plan.revision_actions) > action_budget:
            raise ValueError("seeded plan exceeds drawing action budget")
        interface = locate_interface(initial_screenshot)
        screenshot = initial_screenshot
        current_tool = ""
        current_colour = ""
        checkpoints = _checkpoint_indices(len(plan.actions), review_budget)

        # Inspect the visible reference board, even when it reports no cards.
        screenshot, _ = bridge.act(
            VisibleAction("click", interface.controls["refs"]),
            DecisionSummary(
                "Gather visual inspiration before drawing.",
                "refs",
                "Open the visible reference board.",
                "Reference board has not yet been inspected.",
            ),
        )
        screenshot, _ = bridge.act(
            VisibleAction("click", interface.controls["refs"]),
            DecisionSummary(
                "Return to the blank canvas.",
                "refs",
                "Close the visible reference board.",
                "Reference ideas noted without copying a single source.",
            ),
        )

        for index, planned in enumerate(plan.actions, start=1):
            if planned.tool != current_tool:
                screenshot, _ = bridge.act(
                    VisibleAction("click", interface.controls[planned.tool]),
                    _summary(planned, "Selecting the visible tool control."),
                )
                current_tool = planned.tool
            if planned.colour != current_colour:
                screenshot, _ = bridge.act(
                    VisibleAction("click", interface.palette[planned.colour]),
                    _summary(planned, "Selecting the visible palette swatch."),
                )
                current_colour = planned.colour
            screenshot, _ = bridge.act(
                _visible_drawing_action(planned, interface),
                _summary(planned, assess_canvas(screenshot, interface)),
            )
            if index in checkpoints:
                checkpoint = checkpoints.index(index) + 1
                findings = generate_review_findings(
                    screenshot,
                    interface.canvas_origin,
                    interface.canvas_size,
                    prompt,
                    checkpoint,
                )
                screenshot = bridge.review(
                    assess_canvas(screenshot, interface),
                    findings,
                )

        # One deliberately bounded revision pass after the third visual review.
        for planned in plan.revision_actions[:3]:
            if planned.tool != current_tool:
                screenshot, _ = bridge.act(
                    VisibleAction("click", interface.controls[planned.tool]),
                    _summary(planned, "Revision pass: select the required tool."),
                )
                current_tool = planned.tool
            if planned.colour != current_colour:
                screenshot, _ = bridge.act(
                    VisibleAction("click", interface.palette[planned.colour]),
                    _summary(planned, "Revision pass: select the required colour."),
                )
                current_colour = planned.colour
            screenshot, _ = bridge.act(
                _visible_drawing_action(planned, interface),
                _summary(planned, assess_canvas(screenshot, interface)),
            )

        save_summary = DecisionSummary(
            goal="Preserve the reviewed artwork.",
            selected_tool=current_tool or "brush",
            intended_action="Click the visible Save control.",
            visual_assessment=assess_canvas(screenshot, interface),
        )
        _, result = bridge.act(
            VisibleAction("click", interface.controls["save"]),
            save_summary,
        )
        if not result.get("saved_path"):
            raise RuntimeError("visible Save control did not produce the final PNG")
        return bridge.finish()


def run_screenshot_agent(
    prompt: str,
    seed: int,
    run_dir: Path,
    action_budget: int = 100,
    review_budget: int = 3,
    reference_manifest: Path | None = None,
) -> dict[str, str]:
    run = PaintRun(
        run_dir,
        prompt,
        seed,
        "deterministic_pixel_vision",
        action_budget,
        review_budget,
        load_reference_manifest(reference_manifest),
    )
    run.app.set_summary(phase="SCREENSHOT-ONLY PIXEL AGENT")
    initial = run.capture("agent_observation")
    bridge = InProcessVisibleBridge(run)
    return ScreenshotPaintAgent().run(
        prompt,
        seed,
        initial,
        bridge,
        action_budget,
        review_budget,
    )


def _apply_structured(run: PaintRun, action: PlanAction) -> Path:
    run.app.set_review_findings(())
    model = run.app.model
    colour = PALETTE[action.colour]
    if action.tool == "fill":
        model.fill(action.start, colour)
    elif action.tool == "brush":
        model.brush([action.start, action.end or action.start], colour, run.app.brush_size)
    elif action.tool == "line":
        model.line(action.start, action.end or action.start, colour, run.app.brush_size)
    elif action.tool == "rectangle":
        model.rectangle(action.start, action.end or action.start, colour, run.app.brush_size)
    elif action.tool == "ellipse":
        model.ellipse(action.start, action.end or action.start, colour, run.app.brush_size)
    else:
        raise ValueError(f"unsupported structured tool: {action.tool}")
    run.app.drawing_actions += 1
    run.app.set_summary(
        goal=action.goal,
        tool=action.tool,
        intended_action=action.intent,
        assessment="Exact canvas command applied for logic verification.",
    )
    run.events.append(
        {
            "sequence": len(run.events),
            "type": "structured_action",
            "tool": action.tool,
            "colour": action.colour,
            "start": list(action.start),
            "end": list(action.end) if action.end else None,
            "summary": {
                "goal": action.goal,
                "selected_tool": action.tool,
                "intended_action": action.intent,
                "visual_assessment": "Exact canvas command applied for logic verification.",
            },
            "drawing_actions": run.app.drawing_actions,
        }
    )
    screenshot = run.capture(f"structured_{run.app.drawing_actions:03d}")
    run.events[-1]["screenshot"] = str(screenshot)
    run._flush_log()
    return screenshot


def _visible_drawing_action(
    action: PlanAction,
    interface: LocatedInterface,
) -> VisibleAction:
    start = canvas_point(interface, action.start)
    if action.end is None:
        return VisibleAction("click", start)
    return VisibleAction("drag", start, canvas_point(interface, action.end))


def _summary(action: PlanAction, assessment: str) -> DecisionSummary:
    return DecisionSummary(
        goal=action.goal,
        selected_tool=action.tool,
        intended_action=action.intent,
        visual_assessment=assessment,
    )


def _checkpoint_indices(action_count: int, review_budget: int) -> list[int]:
    if review_budget < 1:
        return []
    return sorted(
        {
            max(1, round(action_count * index / review_budget))
            for index in range(1, review_budget + 1)
        }
    )
