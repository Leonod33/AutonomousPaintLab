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
    TEXT,
    TOOL_MARKERS,
    TOOLS,
    UTILITY_CONTROLS,
    WINDOW_SIZE,
)
from .model import CanvasModel, Point


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
    ) -> None:
        pygame.init()
        pygame.font.init()
        self.model = model or CanvasModel(*CANVAS_SIZE)
        self.output_path = output_path or Path("painting.png")
        self.prompt = prompt
        self.seed = seed
        self.action_budget = action_budget
        self.review_budget = review_budget
        self.drawing_actions = 0
        self.review_checkpoints = 0
        self.selected_tool = "brush"
        self.selected_colour = "ink"
        self.brush_size = 8
        self.summary = VisibleSummary()
        self.drag_start: Point | None = None
        self.drag_current: Point | None = None
        self._font = pygame.font.Font(None, 24)
        self._small = pygame.font.Font(None, 19)
        self._tiny = pygame.font.Font(None, 16)
        self._title = pygame.font.Font(None, 34)
        self._tool_rects = self._build_tool_rects()
        self._palette_rects = self._build_palette_rects()

    @staticmethod
    def _build_tool_rects() -> dict[str, pygame.Rect]:
        rects: dict[str, pygame.Rect] = {}
        names = list(TOOLS) + list(UTILITY_CONTROLS)
        for index, name in enumerate(names):
            rects[name] = pygame.Rect(20 + index * 94, 72, 86, 48)
        return rects

    @staticmethod
    def _build_palette_rects() -> dict[str, pygame.Rect]:
        rects: dict[str, pygame.Rect] = {}
        for index, name in enumerate(PALETTE):
            column = index % 5
            row = index // 5
            rects[name] = pygame.Rect(824 + column * 72, 198 + row * 70, 52, 52)
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

    def click(self, position: Point) -> UIResult:
        for name, rect in self._tool_rects.items():
            if rect.collidepoint(position):
                if name in TOOLS:
                    self.selected_tool = name
                    self.summary.tool = name
                    return UIResult(True, control=name)
                if name == "undo":
                    return UIResult(self.model.undo(), control=name)
                if name == "clear":
                    self.model.clear()
                    return UIResult(True, drawing_applied=True, control=name)
                if name == "save":
                    saved = self.model.save(self.output_path)
                    return UIResult(True, control=name, saved_path=str(saved))
        for name, rect in self._palette_rects.items():
            if rect.collidepoint(position):
                self.selected_colour = name
                return UIResult(True, control=f"palette:{name}")
        if self.canvas_rect.collidepoint(position):
            local = self._local(position)
            if self.selected_tool == "fill":
                self.model.fill(local, PALETTE[self.selected_colour])
                return UIResult(True, drawing_applied=True, control="canvas")
            if self.selected_tool == "brush":
                self.model.brush([local], PALETTE[self.selected_colour], self.brush_size)
                return UIResult(True, drawing_applied=True, control="canvas")
        return UIResult(False)

    def drag(self, start: Point, end: Point, steps: int = 12) -> UIResult:
        if not self.canvas_rect.collidepoint(start):
            return UIResult(False)
        clipped_end = (
            min(self.canvas_rect.right - 1, max(self.canvas_rect.left, end[0])),
            min(self.canvas_rect.bottom - 1, max(self.canvas_rect.top, end[1])),
        )
        local_start = self._local(start)
        local_end = self._local(clipped_end)
        colour = PALETTE[self.selected_colour]
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
            self.model.rectangle(local_start, local_end, colour, self.brush_size)
        elif self.selected_tool == "ellipse":
            self.model.ellipse(local_start, local_end, colour, self.brush_size)
        else:
            return self.click(start)
        return UIResult(True, drawing_applied=True, control="canvas")

    def render(self) -> pygame.Surface:
        surface = pygame.Surface(WINDOW_SIZE)
        surface.fill(BACKGROUND)
        self._draw_header(surface)
        self._draw_toolbar(surface)
        self._draw_canvas(surface)
        self._draw_side_panel(surface)
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

    def _draw_header(self, surface: pygame.Surface) -> None:
        surface.blit(self._title.render("AUTONOMOUS PAINT LAB", True, TEXT), (20, 20))
        mode = self.summary.phase.upper()
        mode_text = self._font.render(mode, True, ACCENT)
        surface.blit(mode_text, (820, 24))
        seed_text = self._small.render(f"SEED {self.seed}", True, MUTED)
        surface.blit(seed_text, (1125, 28))

    def _draw_toolbar(self, surface: pygame.Surface) -> None:
        for name, rect in self._tool_rects.items():
            selected = name == self.selected_tool
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

    def _draw_side_panel(self, surface: pygame.Surface) -> None:
        panel = pygame.Rect(804, 64, 416, 672)
        pygame.draw.rect(surface, PANEL, panel, border_radius=10)
        pygame.draw.rect(surface, BUTTON_BORDER, panel, width=2, border_radius=10)
        self._blit_text(surface, "PALETTE", (824, 148), self._font, TEXT)
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
            f"DRAWING ACTIONS {self.drawing_actions}/{self.action_budget}    "
            f"REVIEWS {self.review_checkpoints}/{self.review_budget}"
        )
        self._blit_text(surface, counters, (824, 670), self._small, TEXT)
        input_label = (
            "Agent input: complete application screenshot only"
            if "SCREENSHOT" in self.summary.phase.upper()
            or "MODEL-VISION" in self.summary.phase.upper()
            else "Agent input: structured canvas state"
            if "STRUCTURED" in self.summary.phase.upper()
            else "Human input: mouse"
        )
        self._blit_text(surface, input_label, (824, 704), self._tiny, MUTED)

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
        words = text.split()
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
            "review_budget": self.review_budget,
            "drawing_actions": self.drawing_actions,
            "review_checkpoints": self.review_checkpoints,
            "selected_tool": self.selected_tool,
            "selected_colour": self.selected_colour,
            "brush_size": self.brush_size,
            "summary": asdict(self.summary),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "PaintApplication":
        app = cls(
            model=CanvasModel.from_payload(payload["model"]),
            output_path=Path(payload["output_path"]),
            prompt=payload["prompt"],
            seed=int(payload["seed"]),
            action_budget=int(payload["action_budget"]),
            review_budget=int(payload["review_budget"]),
        )
        app.drawing_actions = int(payload["drawing_actions"])
        app.review_checkpoints = int(payload["review_checkpoints"])
        app.selected_tool = payload["selected_tool"]
        app.selected_colour = payload["selected_colour"]
        app.brush_size = int(payload["brush_size"])
        app.summary = VisibleSummary(**payload["summary"])
        return app
