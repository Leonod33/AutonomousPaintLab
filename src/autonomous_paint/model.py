"""Canvas state and drawing primitives, independent of PyGame."""

from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path
from typing import Iterable, Sequence

from PIL import Image, ImageDraw

Point = tuple[int, int]
Colour = tuple[int, int, int]


class CanvasModel:
    """Own the artwork pixels and undo history without any UI dependency."""

    def __init__(
        self,
        width: int = 760,
        height: int = 600,
        background: Colour = (245, 247, 250),
        max_history: int = 40,
    ) -> None:
        if width < 1 or height < 1:
            raise ValueError("canvas dimensions must be positive")
        self.width = width
        self.height = height
        self.background = background
        self.max_history = max_history
        self.image = Image.new("RGB", (width, height), background)
        self._history: list[Image.Image] = []

    def _remember(self) -> None:
        self._history.append(self.image.copy())
        if len(self._history) > self.max_history:
            del self._history[0]

    def _point(self, point: Point) -> Point:
        return (
            min(self.width - 1, max(0, int(point[0]))),
            min(self.height - 1, max(0, int(point[1]))),
        )

    def brush(
        self,
        points: Iterable[Point],
        colour: Colour,
        size: int = 8,
    ) -> None:
        path = [self._point(point) for point in points]
        if not path:
            return
        self._remember()
        draw = ImageDraw.Draw(self.image)
        if len(path) == 1:
            x, y = path[0]
            radius = max(1, size // 2)
            draw.ellipse(
                (x - radius, y - radius, x + radius, y + radius),
                fill=colour,
            )
            return
        draw.line(path, fill=colour, width=max(1, size), joint="curve")
        radius = max(1, size // 2)
        for x, y in (path[0], path[-1]):
            draw.ellipse(
                (x - radius, y - radius, x + radius, y + radius),
                fill=colour,
            )

    def line(
        self,
        start: Point,
        end: Point,
        colour: Colour,
        size: int = 6,
    ) -> None:
        self._remember()
        ImageDraw.Draw(self.image).line(
            (self._point(start), self._point(end)),
            fill=colour,
            width=max(1, size),
        )

    def rectangle(
        self,
        start: Point,
        end: Point,
        colour: Colour,
        size: int = 6,
        filled: bool = False,
    ) -> None:
        self._remember()
        box = self._normalized_box(start, end)
        draw = ImageDraw.Draw(self.image)
        draw.rectangle(
            box,
            fill=colour if filled else None,
            outline=colour,
            width=max(1, size),
        )

    def ellipse(
        self,
        start: Point,
        end: Point,
        colour: Colour,
        size: int = 6,
        filled: bool = False,
    ) -> None:
        self._remember()
        box = self._normalized_box(start, end)
        draw = ImageDraw.Draw(self.image)
        draw.ellipse(
            box,
            fill=colour if filled else None,
            outline=colour,
            width=max(1, size),
        )

    def fill(self, point: Point, colour: Colour) -> None:
        self._remember()
        ImageDraw.floodfill(self.image, self._point(point), colour)

    def clear(self) -> None:
        self._remember()
        self.image = Image.new(
            "RGB",
            (self.width, self.height),
            self.background,
        )

    def undo(self) -> bool:
        if not self._history:
            return False
        self.image = self._history.pop()
        return True

    def save(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.image.save(path)
        return path

    def colour_count(self) -> int:
        return len(self.image.getcolors(maxcolors=self.width * self.height) or [])

    def to_payload(self) -> dict[str, object]:
        return {
            "width": self.width,
            "height": self.height,
            "background": list(self.background),
            "max_history": self.max_history,
            "image": self._encode(self.image),
            "history": [self._encode(image) for image in self._history],
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> "CanvasModel":
        model = cls(
            width=int(payload["width"]),
            height=int(payload["height"]),
            background=tuple(payload["background"]),  # type: ignore[arg-type]
            max_history=int(payload["max_history"]),
        )
        model.image = cls._decode(str(payload["image"]))
        model._history = [
            cls._decode(str(value))
            for value in payload.get("history", [])  # type: ignore[union-attr]
        ]
        return model

    def _normalized_box(self, start: Point, end: Point) -> tuple[int, int, int, int]:
        x1, y1 = self._point(start)
        x2, y2 = self._point(end)
        return min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)

    @staticmethod
    def _encode(image: Image.Image) -> str:
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("ascii")

    @staticmethod
    def _decode(value: str) -> Image.Image:
        raw = base64.b64decode(value.encode("ascii"))
        with Image.open(BytesIO(raw)) as image:
            return image.convert("RGB")

