"""Structured control and strict screenshot-only agent runners."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from .constants import PALETTE
from .plans import ArtPlan, PlanAction, prepare_plan
from .quality import resolve_budget_policy
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
    revision_budget: int | None = None,
    min_actions: int | None = None,
    target_actions: int | None = None,
    max_actions: int | None = None,
    detail_level: str = "standard",
) -> dict[str, str]:
    """Apply exact model commands to verify drawing logic; never label as vision."""
    policy = resolve_budget_policy(
        action_budget=action_budget,
        min_actions=min_actions,
        target_actions=target_actions,
        max_actions=max_actions,
        review_budget=review_budget,
        revision_budget=revision_budget,
        detail_level=detail_level,
    )
    plan = prepare_plan(
        prompt,
        seed,
        target_actions=policy.target_actions,
        maximum_actions=policy.maximum_actions,
        revision_budget=policy.revision_actions,
    )
    run = PaintRun(
        run_dir,
        prompt,
        seed,
        "structured_state",
        action_budget=policy.maximum_actions,
        review_budget=policy.review_checkpoints,
        references=load_reference_manifest(reference_manifest),
        revision_budget=policy.revision_actions,
        min_actions=policy.minimum_actions,
        target_actions=policy.target_actions,
        detail_level=policy.detail_level,
    )
    run.app.set_summary(phase="STRUCTURED-STATE CONTROL")
    checkpoints = _checkpoint_indices(len(plan.actions), policy.review_checkpoints)
    revision_cursor = 0
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
            revision_stop = round(
                checkpoint * len(plan.revision_actions) / policy.review_checkpoints
            )
            for revision in plan.revision_actions[revision_cursor:revision_stop]:
                _apply_structured(run, revision, is_revision=True)
            revision_cursor = revision_stop
    run.assert_save_ready()
    run.app.model.save(run.output_path)
    run.capture("saved")
    return run.finalize()


class VisibleBridge(Protocol):
    def act(
        self,
        action: VisibleAction,
        summary: DecisionSummary,
        *,
        is_revision: bool | None = None,
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
        *,
        is_revision: bool | None = None,
    ) -> tuple[Path, dict[str, object]]:
        result = self.__run.execute(action, summary, is_revision=is_revision)
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
        variant_index: int = 0,
        revision_budget: int | None = None,
        min_actions: int | None = None,
        target_actions: int | None = None,
        max_actions: int | None = None,
        detail_level: str = "standard",
    ) -> dict[str, str]:
        policy = resolve_budget_policy(
            action_budget=action_budget,
            min_actions=min_actions,
            target_actions=target_actions,
            max_actions=max_actions,
            review_budget=review_budget,
            revision_budget=revision_budget,
            detail_level=detail_level,
        )
        plan = prepare_plan(
            prompt,
            seed,
            variant_index,
            target_actions=policy.target_actions,
            maximum_actions=policy.maximum_actions,
            revision_budget=policy.revision_actions,
        )
        interface = locate_interface(initial_screenshot)
        screenshot = initial_screenshot
        current_tool = ""
        current_colour = ""
        current_mode = "outline"
        current_size = 8
        checkpoints = _checkpoint_indices(len(plan.actions), policy.review_checkpoints)
        revision_cursor = 0

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
            if (
                planned.tool in {"rectangle", "ellipse"}
                and planned.shape_mode != current_mode
            ):
                screenshot, _ = bridge.act(
                    VisibleAction("click", interface.controls[planned.shape_mode]),
                    _summary(planned, "Selecting the visible shape style."),
                )
                current_mode = planned.shape_mode
            if planned.colour != current_colour:
                screenshot, _ = bridge.act(
                    VisibleAction("click", interface.palette[planned.colour]),
                    _summary(planned, "Selecting the visible palette swatch."),
                )
                current_colour = planned.colour
            desired_size = _visible_brush_size(planned.brush_size, current_size)
            while current_size != desired_size:
                control = "size_down" if current_size > desired_size else "size_up"
                screenshot, _ = bridge.act(
                    VisibleAction("click", interface.controls[control]),
                    _summary(planned, f"Adjusting visible brush size toward {desired_size}px."),
                )
                current_size = (
                    max(1, current_size - 2)
                    if control == "size_down"
                    else min(64, current_size + 2)
                )
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
                revision_stop = round(
                    checkpoint
                    * len(plan.revision_actions)
                    / policy.review_checkpoints
                )
                for revision in plan.revision_actions[revision_cursor:revision_stop]:
                    if revision.tool != current_tool:
                        screenshot, _ = bridge.act(
                            VisibleAction("click", interface.controls[revision.tool]),
                            _summary(
                                revision,
                                "Checkpoint correction: select the required tool.",
                            ),
                        )
                        current_tool = revision.tool
                    if (
                        revision.tool in {"rectangle", "ellipse"}
                        and revision.shape_mode != current_mode
                    ):
                        screenshot, _ = bridge.act(
                            VisibleAction(
                                "click",
                                interface.controls[revision.shape_mode],
                            ),
                            _summary(
                                revision,
                                "Checkpoint correction: select the shape style.",
                            ),
                        )
                        current_mode = revision.shape_mode
                    if revision.colour != current_colour:
                        screenshot, _ = bridge.act(
                            VisibleAction("click", interface.palette[revision.colour]),
                            _summary(
                                revision,
                                "Checkpoint correction: select the required colour.",
                            ),
                        )
                        current_colour = revision.colour
                    desired_size = _visible_brush_size(
                        revision.brush_size,
                        current_size,
                    )
                    while current_size != desired_size:
                        control = (
                            "size_down"
                            if current_size > desired_size
                            else "size_up"
                        )
                        screenshot, _ = bridge.act(
                            VisibleAction("click", interface.controls[control]),
                            _summary(
                                revision,
                                f"Set checkpoint correction size to {desired_size}px.",
                            ),
                        )
                        current_size = (
                            max(1, current_size - 2)
                            if control == "size_down"
                            else min(64, current_size + 2)
                        )
                    screenshot, _ = bridge.act(
                        _visible_drawing_action(revision, interface),
                        _summary(revision, assess_canvas(screenshot, interface)),
                        is_revision=True,
                    )
                revision_cursor = revision_stop

        save_summary = DecisionSummary(
            goal="Preserve the reviewed artwork.",
            selected_tool=current_tool or "brush",
            intended_action="Click the visible Save control.",
            visual_assessment=assess_canvas(screenshot, interface),
            pass_name="focal_finish",
            detail_key="save_gate",
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
    variant_index: int = 0,
    revision_budget: int | None = None,
    min_actions: int | None = None,
    target_actions: int | None = None,
    max_actions: int | None = None,
    detail_level: str = "standard",
) -> dict[str, str]:
    run = PaintRun(
        run_dir,
        prompt,
        seed,
        "deterministic_pixel_vision",
        action_budget=action_budget,
        review_budget=review_budget,
        references=load_reference_manifest(reference_manifest),
        variant_index=variant_index,
        revision_budget=revision_budget,
        min_actions=min_actions,
        target_actions=target_actions,
        max_actions=max_actions,
        detail_level=detail_level,
    )
    run.app.set_summary(phase="SCREENSHOT-ONLY PIXEL AGENT")
    initial = run.capture("agent_observation")
    bridge = InProcessVisibleBridge(run)
    return ScreenshotPaintAgent().run(
        prompt,
        seed,
        initial,
        bridge,
        action_budget=action_budget,
        review_budget=review_budget,
        variant_index=variant_index,
        revision_budget=revision_budget,
        min_actions=min_actions,
        target_actions=target_actions,
        max_actions=max_actions,
        detail_level=detail_level,
    )


def _apply_structured(
    run: PaintRun,
    action: PlanAction,
    *,
    is_revision: bool = False,
) -> Path:
    if run.app.drawing_actions >= run.action_budget:
        raise RuntimeError("drawing action budget exhausted")
    if is_revision and run.app.revision_actions >= run.revision_budget:
        raise RuntimeError("revision action budget exhausted")
    run.app.set_review_findings(())
    model = run.app.model
    colour = PALETTE[action.colour]
    size = action.brush_size or run.app.brush_size
    if action.tool == "fill":
        model.fill(action.start, colour)
    elif action.tool == "brush":
        model.brush([action.start, action.end or action.start], colour, size)
    elif action.tool == "line":
        model.line(action.start, action.end or action.start, colour, size)
    elif action.tool == "rectangle":
        model.rectangle(
            action.start,
            action.end or action.start,
            colour,
            size,
            filled=action.shape_mode in {"filled", "both"},
        )
    elif action.tool == "ellipse":
        model.ellipse(
            action.start,
            action.end or action.start,
            colour,
            size,
            filled=action.shape_mode in {"filled", "both"},
        )
    elif action.tool == "curve":
        end = action.end or action.start
        control = (
            round((action.start[0] + end[0]) / 2),
            min(action.start[1], end[1])
            - max(18, abs(end[0] - action.start[0]) // 5),
        )
        model.add_curve_object(action.start, control, end, colour, size)
    else:
        raise ValueError(f"unsupported structured tool: {action.tool}")
    run.app.drawing_actions += 1
    if is_revision:
        run.app.revision_actions += 1
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
            "revision_actions": run.app.revision_actions,
            "is_revision": is_revision,
            "pass_name": action.pass_name,
            "detail_key": action.detail_key,
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
        pass_name=action.pass_name,
        detail_key=action.detail_key,
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


def _visible_brush_size(requested: int | None, current: int) -> int:
    if requested is None:
        return current
    value = min(64, max(1, requested))
    if value > 1 and value % 2:
        value += 1
    return min(64, value)
