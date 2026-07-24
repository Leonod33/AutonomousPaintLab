"""PyGame rendering and visible mouse-action handling."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import os
from pathlib import Path
from typing import Any

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
if not os.environ.get("DISPLAY"):
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from .constants import (
    ACCENT,
    BACKGROUND,
    BUTTON_BORDER,
    CANVAS_BORDER_WIDTH,
    CANVAS_LOCATOR,
    CANVAS_ORIGIN,
    CANVAS_SIZE,
    MUTED,
    PALETTE,
    PALETTE_MARKERS,
    PANEL,
    PANEL_LIGHT,
    SELECTED,
    SIZE_CONTROLS,
    STYLE_CONTROLS,
    TEXT,
    TOOL_MARKERS,
    TOOLS,
    UTILITY_CONTROLS,
    WINDOW_SIZE,
)
from .model import CanvasModel, Point
from .references import ReferenceCard
from .review import ReviewFinding


@dataclass
class VisibleSummary:
    phase: str = "HUMAN PAINT"
    goal: str = "Draw freely on the canvas."
    tool: str = "brush"
    intended_action: str = "Waiting for input."
    assessment: str = "Canvas ready."


@dataclass(frozen=True)
class UIResult:
    applied: bool
    drawing_applied: bool = False
    control: str | None = None
    saved_path: str | None = None


class PaintApplication:
    """Render one complete Paint UI and translate mouse input into model calls."""

    def __init__(
        self,
        model: CanvasModel | None = None,
        output_path: Path | None = None,
        prompt: str = "",
        seed: int = 0,
        action_budget: int = 100,
        review_budget: int = 3,
        references: tuple[ReferenceCard, ...] = (),
        revision_budget: int = 3,
        minimum_actions: int = 0,
        target_actions: int | None = None,
        detail_level: str = "standard",
    ) -> None:
        if action_budget < 1:
            raise ValueError("action budget must be positive")
        if review_budget < 1:
            raise ValueError("review budget must be positive")
        if revision_budget < 0:
            raise ValueError("revision action budget cannot be negative")
        resolved_target = target_actions if target_actions is not None else action_budget
        if not 0 <= minimum_actions <= resolved_target <= action_budget:
            raise ValueError("actions must satisfy minimum <= target <= maximum")
        pygame.init()
        pygame.font.init()
        self.model = model or CanvasModel(*CANVAS_SIZE)
        self.output_path = output_path or Path("painting.png")
        self.prompt = prompt
        self.seed = seed
        self.action_budget = action_budget
        self.minimum_actions = minimum_actions
        self.target_actions = resolved_target
        self.detail_level = detail_level
        self.review_budget = review_budget
        self.revision_budget = revision_budget
        self.drawing_actions = 0
        self.review_checkpoints = 0
        self.revision_actions = 0
        self.selected_tool = "brush"
        self.selected_colour = "ink"
        self.brush_size = 8
        self.shape_mode = "outline"
        self.custom_colour = (18, 23, 35)
        self.recent_colours: list[tuple[int, int, int]] = []
        self.magnifier_point: Point = (CANVAS_SIZE[0] // 2, CANVAS_SIZE[1] // 2)
        self.pending_curve_points: list[Point] = []
        self.selected_curve_id: str | None = None
        self.summary = VisibleSummary()
        self.references = references
        self.reference_board_open = False
        self.review_findings: tuple[ReviewFinding, ...] = ()
        self._reference_image_cache: dict[str, pygame.Surface | None] = {}
        self.drag_start: Point | None = None
        self.drag_current: Point | None = None
        self._font = pygame.font.Font(None, 24)
        self._small = pygame.font.Font(None, 19)
        self._tiny = pygame.font.Font(None, 16)
        self._title = pygame.font.Font(None, 34)
        self._tool_rects = self._build_tool_rects()
        self._palette_rects = self._build_palette_rects()
        self._custom_colour_rect = pygame.Rect(824, 306, 74, 34)
        self._recent_colour_rects = [
            pygame.Rect(824 + index * 22, 344, 16, 14)
            for index in range(6)
        ]
        self._layer_rects = {
            "layer_prev": pygame.Rect(824, 124, 42, 28),
            "layer_add": pygame.Rect(870, 124, 42, 28),
            "layer_remove": pygame.Rect(916, 124, 42, 28),
            "layer_next": pygame.Rect(962, 124, 42, 28),
            "layer_visible": pygame.Rect(1008, 124, 52, 28),
            "layer_down": pygame.Rect(1064, 124, 52, 28),
            "layer_up": pygame.Rect(1120, 124, 52, 28),
        }

    @staticmethod
    def _build_tool_rects() -> dict[str, pygame.Rect]:
        rects: dict[str, pygame.Rect] = {}
        names = (
            list(TOOLS)
            + list(STYLE_CONTROLS)
            + list(SIZE_CONTROLS)
            + list(UTILITY_CONTROLS)
        )
        for index, name in enumerate(names):
            rects[name] = pygame.Rect(20 + index * 70, 72, 64, 48)
        return rects

    @staticmethod
    def _build_palette_rects() -> dict[str, pygame.Rect]:
        rects: dict[str, pygame.Rect] = {}
        for index, name in enumerate(PALETTE):
            column = index % 7
            row = index // 7
            rects[name] = pygame.Rect(824 + column * 54, 185 + row * 60, 42, 42)
        return rects

    @property
    def canvas_rect(self) -> pygame.Rect:
        return pygame.Rect(*CANVAS_ORIGIN, *CANVAS_SIZE)

    def set_summary(
        self,
        *,
        phase: str | None = None,
        goal: str | None = None,
        tool: str | None = None,
        intended_action: str | None = None,
        assessment: str | None = None,
    ) -> None:
        values = asdict(self.summary)
        updates = {
            "phase": phase,
            "goal": goal,
            "tool": tool,
            "intended_action": intended_action,
            "assessment": assessment,
        }
        values.update({key: value for key, value in updates.items() if value is not None})
        self.summary = VisibleSummary(**values)

    def set_review_findings(
        self,
        findings: tuple[ReviewFinding, ...] | list[ReviewFinding],
    ) -> None:
        self.review_findings = tuple(findings)
        if findings:
            self.reference_board_open = False

    def click(self, position: Point) -> UIResult:
        for name, rect in self._tool_rects.items():
            if rect.collidepoint(position):
                if name in TOOLS:
                    self.selected_tool = name
                    self.summary.tool = name
                    if name != "curve":
                        self.pending_curve_points = []
                    return UIResult(True, control=name)
                if name in STYLE_CONTROLS:
                    self.shape_mode = name
                    return UIResult(True, control=name)
                if name in SIZE_CONTROLS:
                    delta = -2 if name == "size_down" else 2
                    self.brush_size = min(64, max(1, self.brush_size + delta))
                    return UIResult(True, control=name)
                if name == "undo":
                    return UIResult(self.model.undo(), control=name)
                if name == "clear":
                    if not self._drawing_budget_available():
                        return UIResult(False, control="budget")
                    self.model.clear()
                    return UIResult(True, drawing_applied=True, control=name)
                if name == "refs":
                    self.reference_board_open = not self.reference_board_open
                    self.review_findings = ()
                    return UIResult(True, control=name)
                if name == "save":
                    saved = self.model.save(self.output_path)
                    return UIResult(True, control=name, saved_path=str(saved))
        for name, rect in self._palette_rects.items():
            if rect.collidepoint(position):
                self.selected_colour = name
                self._remember_colour(PALETTE[name])
                return UIResult(True, control=f"palette:{name}")
        for name, rect in self._layer_rects.items():
            if not rect.collidepoint(position):
                continue
            if name == "layer_add":
                self.model.add_layer()
            elif name == "layer_remove":
                self.model.remove_layer()
            elif name == "layer_prev":
                self.model.select_layer(max(0, self.model.active_layer - 1))
            elif name == "layer_next":
                self.model.select_layer(
                    min(len(self.model.layer_names) - 1, self.model.active_layer + 1)
                )
            elif name == "layer_visible":
                self.model.set_layer_visible(
                    self.model.active_layer,
                    not self.model.layer_visibility[self.model.active_layer],
                )
            elif name == "layer_down":
                self.model.move_layer(self.model.active_layer, -1)
            elif name == "layer_up":
                self.model.move_layer(self.model.active_layer, 1)
            return UIResult(True, control=name)
        if self._custom_colour_rect.collidepoint(position):
            self.selected_colour = "custom"
            return UIResult(True, control="palette:custom")
        for index, rect in enumerate(self._recent_colour_rects):
            if rect.collidepoint(position) and index < len(self.recent_colours):
                self.set_custom_colour(self.recent_colours[index])
                return UIResult(True, control=f"recent:{index + 1}")
        if self.canvas_rect.collidepoint(position) and not self.reference_board_open:
            if not self._drawing_budget_available():
                return UIResult(False, control="budget")
            local = self._local(position)
            self.magnifier_point = local
            if self.selected_tool == "eyedropper":
                self.set_custom_colour(self.model.image.getpixel(local))
                return UIResult(True, control="eyedropper:sample")
            if self.selected_tool == "fill":
                self.model.fill(local, self._colour())
                return UIResult(True, drawing_applied=True, control="canvas")
            if self.selected_tool == "brush":
                self.model.brush([local], self._colour(), self.brush_size)
                return UIResult(True, drawing_applied=True, control="canvas")
            if self.selected_tool == "curve":
                self.pending_curve_points.append(local)
                if len(self.pending_curve_points) < 3:
                    return UIResult(
                        True,
                        control=f"curve_point:{len(self.pending_curve_points)}",
                    )
                self.selected_curve_id = self.model.add_curve_object(
                    self.pending_curve_points[0],
                    self.pending_curve_points[1],
                    self.pending_curve_points[2],
                    self._colour(),
                    self.brush_size,
                )
                self.pending_curve_points = []
                return UIResult(
                    True,
                    drawing_applied=True,
                    control="curve:create",
                )
            if self.selected_tool == "edit":
                self.selected_curve_id = self.model.nearest_curve(local)
                return UIResult(
                    self.selected_curve_id is not None,
                    control="curve:select",
                )
        return UIResult(False)

    def drag(self, start: Point, end: Point, steps: int = 12) -> UIResult:
        if not self.canvas_rect.collidepoint(start) or self.reference_board_open:
            return UIResult(False)
        if not self._drawing_budget_available():
            return UIResult(False, control="budget")
        clipped_end = (
            min(self.canvas_rect.right - 1, max(self.canvas_rect.left, end[0])),
            min(self.canvas_rect.bottom - 1, max(self.canvas_rect.top, end[1])),
        )
        local_start = self._local(start)
        local_end = self._local(clipped_end)
        self.magnifier_point = local_end
        colour = self._colour()
        if self.selected_tool == "brush":
            path = [
                (
                    round(local_start[0] + (local_end[0] - local_start[0]) * index / steps),
                    round(local_start[1] + (local_end[1] - local_start[1]) * index / steps),
                )
                for index in range(steps + 1)
            ]
            self.model.brush(path, colour, self.brush_size)
        elif self.selected_tool == "line":
            self.model.line(local_start, local_end, colour, self.brush_size)
        elif self.selected_tool == "rectangle":
            self.model.rectangle(
                local_start,
                local_end,
                colour,
                self.brush_size,
                filled=self.shape_mode in {"filled", "both"},
            )
        elif self.selected_tool == "ellipse":
            self.model.ellipse(
                local_start,
                local_end,
                colour,
                self.brush_size,
                filled=self.shape_mode in {"filled", "both"},
            )
        elif self.selected_tool == "curve":
            control = (
                round((local_start[0] + local_end[0]) / 2),
                min(local_start[1], local_end[1])
                - max(18, abs(local_end[0] - local_start[0]) // 5),
            )
            self.selected_curve_id = self.model.add_curve_object(
                local_start,
                control,
                local_end,
                colour,
                self.brush_size,
            )
            self.pending_curve_points = []
        elif self.selected_tool == "edit":
            identifier = self.selected_curve_id or self.model.nearest_curve(local_start)
            if identifier is None:
                return UIResult(False, control="curve:edit")
            point_index = self.model.nearest_curve_point(identifier, local_start)
            self.model.edit_curve_point(identifier, point_index, local_end)
            self.selected_curve_id = identifier
        else:
            return self.click(start)
        return UIResult(True, drawing_applied=True, control="canvas")

    def set_custom_colour(self, colour: tuple[int, int, int]) -> None:
        self.custom_colour = tuple(min(255, max(0, int(channel))) for channel in colour)
        self.selected_colour = "custom"
        self._remember_colour(self.custom_colour)

    def _colour(self) -> tuple[int, int, int]:
        if self.selected_colour == "custom":
            return self.custom_colour
        return PALETTE[self.selected_colour]

    def _remember_colour(self, colour: tuple[int, int, int]) -> None:
        if colour in self.recent_colours:
            self.recent_colours.remove(colour)
        self.recent_colours.insert(0, colour)
        del self.recent_colours[6:]

    def render(self) -> pygame.Surface:
        surface = pygame.Surface(WINDOW_SIZE)
        surface.fill(BACKGROUND)
        self._draw_header(surface)
        self._draw_canvas(surface)
        self._draw_side_panel(surface)
        self._draw_toolbar(surface)
        return surface

    def save_screenshot(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        pygame.image.save(self.render(), path)
        return path

    def run_window(self) -> None:
        screen = pygame.display.set_mode(WINDOW_SIZE)
        pygame.display.set_caption("Autonomous Paint Lab")
        clock = pygame.time.Clock()
        dragging = False
        start: Point | None = None
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    start = event.pos
                    dragging = self.canvas_rect.collidepoint(start)
                elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                    if dragging and start is not None and event.pos != start:
                        result = self.drag(start, event.pos)
                    else:
                        result = self.click(event.pos)
                    if result.drawing_applied:
                        self.drawing_actions += 1
                    dragging = False
                    start = None
            screen.blit(self.render(), (0, 0))
            pygame.display.flip()
            clock.tick(60)
        pygame.quit()

    def _local(self, position: Point) -> Point:
        return position[0] - CANVAS_ORIGIN[0], position[1] - CANVAS_ORIGIN[1]

    def _drawing_budget_available(self) -> bool:
        if self.drawing_actions >= self.action_budget:
            return False
        return not (
            self.review_checkpoints >= self.review_budget
            and self.revision_actions >= self.revision_budget
        )

    def _draw_header(self, surface: pygame.Surface) -> None:
        surface.blit(self._title.render("AUTONOMOUS PAINT LAB", True, TEXT), (20, 20))
        mode = self.summary.phase.upper()
        mode_text = self._font.render(mode, True, ACCENT)
        surface.blit(mode_text, (820, 24))
        seed_text = self._small.render(f"SEED {self.seed}", True, MUTED)
        surface.blit(seed_text, (1125, 28))

    def _draw_toolbar(self, surface: pygame.Surface) -> None:
        for name, rect in self._tool_rects.items():
            selected = name == self.selected_tool or (
                name == "refs" and self.reference_board_open
            ) or name == self.shape_mode
            pygame.draw.rect(surface, PANEL_LIGHT if selected else PANEL, rect, border_radius=7)
            pygame.draw.rect(
                surface,
                SELECTED if selected else BUTTON_BORDER,
                rect,
                width=2,
                border_radius=7,
            )
            marker = pygame.Rect(rect.left + 6, rect.top + 6, 12, 12)
            pygame.draw.rect(surface, TOOL_MARKERS[name], marker, border_radius=2)
            label = self._tiny.render(name.upper(), True, TEXT)
            surface.blit(label, label.get_rect(center=(rect.centerx + 4, rect.centery + 5)))

    def _draw_canvas(self, surface: pygame.Surface) -> None:
        border = self.canvas_rect.inflate(CANVAS_BORDER_WIDTH * 2, CANVAS_BORDER_WIDTH * 2)
        pygame.draw.rect(surface, CANVAS_LOCATOR, border, width=CANVAS_BORDER_WIDTH)
        raw = self.model.image.tobytes()
        canvas_surface = pygame.image.fromstring(raw, self.model.image.size, "RGB")
        surface.blit(canvas_surface, CANVAS_ORIGIN)
        if self.reference_board_open:
            self._draw_reference_board(surface)
        elif self.review_findings:
            self._draw_review_overlays(surface)
        elif self.selected_tool in {"curve", "edit"}:
            self._draw_curve_handles(surface)

    def _draw_side_panel(self, surface: pygame.Surface) -> None:
        panel = pygame.Rect(804, 64, 416, 672)
        pygame.draw.rect(surface, PANEL, panel, border_radius=10)
        pygame.draw.rect(surface, BUTTON_BORDER, panel, width=2, border_radius=10)
        layer_labels = {
            "layer_prev": "<",
            "layer_add": "+",
            "layer_remove": "−",
            "layer_next": ">",
            "layer_visible": "EYE",
            "layer_down": "DOWN",
            "layer_up": "UP",
        }
        for name, rect in self._layer_rects.items():
            pygame.draw.rect(surface, PANEL_LIGHT, rect, border_radius=5)
            pygame.draw.rect(surface, BUTTON_BORDER, rect, width=2, border_radius=5)
            label = self._small.render(layer_labels[name], True, TEXT)
            surface.blit(label, label.get_rect(center=rect.center))
        layer_status = (
            f"LAYER {self.model.active_layer + 1}/{len(self.model.layer_names)} "
            f"{self.model.layer_names[self.model.active_layer]}"
        )
        self._blit_text(surface, layer_status, (1022, 132), self._tiny, MUTED)
        self._blit_text(surface, "PALETTE", (824, 158), self._font, TEXT)
        for name, rect in self._palette_rects.items():
            selected = name == self.selected_colour
            pygame.draw.rect(surface, PALETTE[name], rect, border_radius=6)
            pygame.draw.rect(
                surface,
                SELECTED if selected else BUTTON_BORDER,
                rect,
                width=3,
                border_radius=6,
            )
            marker = pygame.Rect(rect.left + 4, rect.top + 4, 8, 8)
            pygame.draw.rect(surface, PALETTE_MARKERS[name], marker)
            label = self._tiny.render(name.upper(), True, TEXT)
            surface.blit(label, (rect.left, rect.bottom + 5))

        custom = self._custom_colour_rect
        pygame.draw.rect(surface, self.custom_colour, custom, border_radius=5)
        pygame.draw.rect(
            surface,
            SELECTED if self.selected_colour == "custom" else BUTTON_BORDER,
            custom,
            width=3,
            border_radius=5,
        )
        status = (
            f"{self.shape_mode.upper()}  •  {self.brush_size}px  •  "
            f"XY {self.magnifier_point}"
        )
        self._blit_text(surface, status, (912, 315), self._tiny, MUTED)
        self._draw_magnifier(surface)
        for index, rect in enumerate(self._recent_colour_rects):
            colour = (
                self.recent_colours[index]
                if index < len(self.recent_colours)
                else PANEL_LIGHT
            )
            pygame.draw.rect(surface, colour, rect, border_radius=2)
            pygame.draw.rect(surface, BUTTON_BORDER, rect, width=1, border_radius=2)

        if self.review_findings:
            self._draw_review_panel(surface)
        else:
            y = 362
            self._blit_text(surface, "DECISION SUMMARY", (824, y), self._font, ACCENT)
            y += 34
            fields = [
                ("CURRENT GOAL", self.summary.goal),
                ("SELECTED TOOL", self.summary.tool.upper()),
                ("INTENDED ACTION", self.summary.intended_action),
                ("VISUAL ASSESSMENT", self.summary.assessment),
            ]
            for heading, value in fields:
                self._blit_text(surface, heading, (824, y), self._tiny, MUTED)
                y += 20
                y = self._wrapped(surface, value, 824, y, 368, self._small, TEXT)
                y += 13

        pygame.draw.line(surface, BUTTON_BORDER, (824, 651), (1200, 651), 1)
        counters = (
            f"ACTIONS {self.drawing_actions}  MIN {self.minimum_actions}  "
            f"TARGET {self.target_actions}  MAX {self.action_budget}   "
            f"REVIEWS {self.review_checkpoints}/{self.review_budget}"
        )
        revision_counters = (
            f"REVISION ACTIONS {self.revision_actions}/{self.revision_budget}   "
            f"REFS {len(self.references)}/{self._reference_preview_count()} PREV"
        )
        self._blit_text(surface, counters, (824, 666), self._tiny, TEXT)
        self._blit_text(surface, revision_counters, (824, 685), self._tiny, TEXT)
        input_label = (
            "Agent input: complete application screenshot only"
            if "SCREENSHOT" in self.summary.phase.upper()
            or "MODEL-VISION" in self.summary.phase.upper()
            else "Agent input: structured canvas state"
            if "STRUCTURED" in self.summary.phase.upper()
            else "Human input: mouse"
        )
        self._blit_text(surface, input_label, (824, 712), self._tiny, MUTED)

    def _draw_review_overlays(self, surface: pygame.Surface) -> None:
        overlay = pygame.Surface(CANVAS_SIZE, pygame.SRCALPHA)
        priority_colours = {
            "high": (255, 103, 120),
            "medium": (255, 213, 79),
            "low": (111, 195, 255),
        }
        for index, finding in enumerate(self.review_findings, start=1):
            x, y, width, height = finding.region
            rect = pygame.Rect(x, y, width, height).clip(
                pygame.Rect(0, 0, *CANVAS_SIZE)
            )
            colour = priority_colours[finding.priority]
            pygame.draw.rect(overlay, (*colour, 38), rect)
            pygame.draw.rect(overlay, (*colour, 255), rect, width=4)
            badge = pygame.Rect(rect.left + 5, rect.top + 5, 30, 30)
            pygame.draw.ellipse(overlay, (*colour, 255), badge)
            pygame.draw.ellipse(overlay, (*BACKGROUND, 255), badge, width=2)
            number = self._small.render(str(index), True, BACKGROUND)
            overlay.blit(number, number.get_rect(center=badge.center))
        surface.blit(overlay, CANVAS_ORIGIN)

    def _draw_curve_handles(self, surface: pygame.Surface) -> None:
        """Show curve anchors and controls without modifying canvas state."""
        points: tuple[Point, ...] = ()
        if self.selected_curve_id is not None:
            try:
                points = self.model.curve_points(self.selected_curve_id)
            except KeyError:
                self.selected_curve_id = None
        if not points and self.pending_curve_points:
            points = tuple(self.pending_curve_points)
        if not points:
            return
        translated = [
            (point[0] + CANVAS_ORIGIN[0], point[1] + CANVAS_ORIGIN[1])
            for point in points
        ]
        if len(translated) >= 2:
            pygame.draw.lines(surface, ACCENT, False, translated, 1)
        for index, point in enumerate(translated):
            colour = PALETTE["yellow"] if index == 1 else ACCENT
            pygame.draw.circle(surface, BACKGROUND, point, 7)
            pygame.draw.circle(surface, colour, point, 7, width=2)

    def _draw_magnifier(self, surface: pygame.Surface) -> None:
        x, y = self.magnifier_point
        radius = 12
        crop = self.model.image.crop(
            (
                max(0, x - radius),
                max(0, y - radius),
                min(self.model.width, x + radius),
                min(self.model.height, y + radius),
            )
        )
        if crop.width < 1 or crop.height < 1:
            return
        raw = pygame.image.fromstring(crop.tobytes(), crop.size, "RGB")
        preview = pygame.transform.scale(raw, (72, 36))
        rect = pygame.Rect(1128, 304, 76, 40)
        pygame.draw.rect(surface, BUTTON_BORDER, rect, border_radius=4)
        surface.blit(preview, (rect.x + 2, rect.y + 2))
        pygame.draw.line(
            surface,
            SELECTED,
            (rect.centerx - 5, rect.centery),
            (rect.centerx + 5, rect.centery),
            1,
        )
        pygame.draw.line(
            surface,
            SELECTED,
            (rect.centerx, rect.centery - 5),
            (rect.centerx, rect.centery + 5),
            1,
        )

    def _draw_review_panel(self, surface: pygame.Surface) -> None:
        y = 356
        self._blit_text(surface, "ART DIRECTOR REVIEW", (824, y), self._font, ACCENT)
        y += 31
        priority_colours = {
            "high": (255, 103, 120),
            "medium": (255, 213, 79),
            "low": (111, 195, 255),
        }
        for index, finding in enumerate(self.review_findings[:2], start=1):
            colour = priority_colours[finding.priority]
            heading = (
                f"{index}  {finding.priority.upper()} • {finding.area} "
                f"({finding.confidence:.0%})"
            )
            self._blit_text(surface, heading, (824, y), self._tiny, colour)
            y += 19
            y = self._wrapped(surface, finding.issue, 824, y, 372, self._tiny, TEXT)
            y += 4
            self._blit_text(surface, "NEXT", (824, y), self._tiny, MUTED)
            y += 17
            y = self._wrapped(
                surface,
                finding.suggestion,
                824,
                y,
                372,
                self._tiny,
                TEXT,
            )
            y += 10
        if len(self.review_findings) > 2:
            self._blit_text(
                surface,
                f"+ {len(self.review_findings) - 2} more finding(s) in review_report.md",
                (824, min(y, 632)),
                self._tiny,
                MUTED,
            )

    def _draw_reference_board(self, surface: pygame.Surface) -> None:
        board = pygame.Surface(CANVAS_SIZE, pygame.SRCALPHA)
        board.fill((10, 16, 30, 246))
        board.blit(
            self._title.render("REFERENCE BOARD", True, ACCENT),
            (24, 20),
        )
        board.blit(
            self._small.render(
                "Use for visual research—combine ideas; do not trace.",
                True,
                MUTED,
            ),
            (25, 55),
        )
        if not self.references:
            message = self._font.render(
                "No references loaded. Close REFS to return to the canvas.",
                True,
                TEXT,
            )
            board.blit(message, (40, 150))
            surface.blit(board, CANVAS_ORIGIN)
            return

        card_width = 228
        for index, reference in enumerate(self.references[:3]):
            x = 18 + index * 247
            card = pygame.Rect(x, 92, card_width, 470)
            pygame.draw.rect(board, PANEL_LIGHT, card, border_radius=8)
            pygame.draw.rect(board, BUTTON_BORDER, card, width=2, border_radius=8)
            image_rect = pygame.Rect(x + 10, 104, card_width - 20, 205)
            pygame.draw.rect(board, BACKGROUND, image_rect, border_radius=5)
            reference_surface = self._reference_surface(reference)
            if reference_surface is not None:
                rect = reference_surface.get_rect(center=image_rect.center)
                board.blit(reference_surface, rect)
            else:
                missing = self._tiny.render("PREVIEW UNAVAILABLE", True, MUTED)
                board.blit(missing, missing.get_rect(center=image_rect.center))
            y = 318
            y = self._wrapped(board, reference.title, x + 10, y, card_width - 20, self._small, TEXT)
            y += 5
            fields = (
                ("USE", reference.note, TEXT),
                ("QUERY", reference.search_query or "Manually supplied", MUTED),
                ("SOURCE", reference.source_url, ACCENT),
                (
                    "RIGHTS",
                    reference.rights_note
                    or "Check source terms; use for inspiration only.",
                    MUTED,
                ),
            )
            for label, value, colour in fields:
                compact = value if len(value) <= 112 else f"{value[:109]}..."
                y = self._wrapped(
                    board,
                    f"{label}: {compact}",
                    x + 10,
                    y,
                    card_width - 20,
                    self._tiny,
                    colour,
                )
                y += 4
        surface.blit(board, CANVAS_ORIGIN)

    def _reference_preview_count(self) -> int:
        return sum(
            1
            for reference in self.references
            if reference.image_path and Path(reference.image_path).is_file()
        )

    def _reference_surface(self, reference: ReferenceCard) -> pygame.Surface | None:
        path = reference.image_path
        if not path:
            return None
        if path in self._reference_image_cache:
            return self._reference_image_cache[path]
        try:
            image = pygame.image.load(path)
            width, height = image.get_size()
            scale = min(208 / width, 205 / height)
            scaled = pygame.transform.smoothscale(
                image,
                (max(1, round(width * scale)), max(1, round(height * scale))),
            )
        except (pygame.error, OSError, ValueError):
            scaled = None
        self._reference_image_cache[path] = scaled
        return scaled

    @staticmethod
    def _blit_text(
        surface: pygame.Surface,
        text: str,
        position: Point,
        font: pygame.font.Font,
        colour: tuple[int, int, int],
    ) -> None:
        surface.blit(font.render(text, True, colour), position)

    @staticmethod
    def _wrapped(
        surface: pygame.Surface,
        text: str,
        x: int,
        y: int,
        width: int,
        font: pygame.font.Font,
        colour: tuple[int, int, int],
    ) -> int:
        words: list[str] = []
        for word in text.split():
            if font.size(word)[0] <= width:
                words.append(word)
                continue
            chunk = ""
            for character in word:
                candidate = f"{chunk}{character}"
                if chunk and font.size(candidate)[0] > width:
                    words.append(chunk)
                    chunk = character
                else:
                    chunk = candidate
            if chunk:
                words.append(chunk)
        line = ""
        for word in words:
            candidate = f"{line} {word}".strip()
            if line and font.size(candidate)[0] > width:
                surface.blit(font.render(line, True, colour), (x, y))
                y += font.get_linesize()
                line = word
            else:
                line = candidate
        if line:
            surface.blit(font.render(line, True, colour), (x, y))
            y += font.get_linesize()
        return y

    def to_payload(self) -> dict[str, Any]:
        return {
            "model": self.model.to_payload(),
            "output_path": str(self.output_path),
            "prompt": self.prompt,
            "seed": self.seed,
            "action_budget": self.action_budget,
            "minimum_actions": self.minimum_actions,
            "target_actions": self.target_actions,
            "detail_level": self.detail_level,
            "review_budget": self.review_budget,
            "revision_budget": self.revision_budget,
            "drawing_actions": self.drawing_actions,
            "review_checkpoints": self.review_checkpoints,
            "revision_actions": self.revision_actions,
            "selected_tool": self.selected_tool,
            "selected_colour": self.selected_colour,
            "brush_size": self.brush_size,
            "shape_mode": self.shape_mode,
            "custom_colour": list(self.custom_colour),
            "recent_colours": [list(colour) for colour in self.recent_colours],
            "magnifier_point": list(self.magnifier_point),
            "pending_curve_points": [
                list(point) for point in self.pending_curve_points
            ],
            "selected_curve_id": self.selected_curve_id,
            "summary": asdict(self.summary),
            "references": [reference.to_dict() for reference in self.references],
            "reference_board_open": self.reference_board_open,
            "review_findings": [
                finding.to_dict() for finding in self.review_findings
            ],
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "PaintApplication":
        app = cls(
            model=CanvasModel.from_payload(payload["model"]),
            output_path=Path(payload["output_path"]),
            prompt=payload["prompt"],
            seed=int(payload["seed"]),
            action_budget=int(payload["action_budget"]),
            minimum_actions=int(payload.get("minimum_actions", 0)),
            target_actions=int(payload.get("target_actions", payload["action_budget"])),
            detail_level=str(payload.get("detail_level", "standard")),
            review_budget=int(payload["review_budget"]),
            references=tuple(
                ReferenceCard.from_dict(value)
                for value in payload.get("references", [])
            ),
            revision_budget=int(payload.get("revision_budget", 3)),
        )
        app.drawing_actions = int(payload["drawing_actions"])
        app.review_checkpoints = int(payload["review_checkpoints"])
        app.revision_actions = int(payload.get("revision_actions", 0))
        app.selected_tool = payload["selected_tool"]
        app.selected_colour = payload["selected_colour"]
        app.brush_size = int(payload["brush_size"])
        app.shape_mode = str(payload.get("shape_mode", "outline"))
        app.custom_colour = tuple(payload.get("custom_colour", (18, 23, 35)))  # type: ignore[arg-type]
        app.recent_colours = [
            tuple(colour)  # type: ignore[arg-type]
            for colour in payload.get("recent_colours", [])  # type: ignore[union-attr]
        ]
        app.magnifier_point = tuple(payload.get("magnifier_point", (380, 300)))  # type: ignore[arg-type]
        app.pending_curve_points = [
            tuple(point)  # type: ignore[arg-type]
            for point in payload.get("pending_curve_points", [])
        ]
        selected_curve_id = payload.get("selected_curve_id")
        app.selected_curve_id = (
            str(selected_curve_id) if selected_curve_id is not None else None
        )
        app.summary = VisibleSummary(**payload["summary"])
        app.reference_board_open = bool(payload.get("reference_board_open", False))
        app.review_findings = tuple(
            ReviewFinding.from_dict(value)
            for value in payload.get("review_findings", [])
        )
        return app
