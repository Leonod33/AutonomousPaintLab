"""Canvas state and drawing primitives, independent of PyGame."""

from __future__ import annotations

import base64
import copy
from io import BytesIO
import math
from pathlib import Path
from typing import Iterable, Sequence

from PIL import Image, ImageDraw, ImageFilter

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
        self._layers: list[dict[str, object]] = [
            {
                "name": "Background",
                "visible": True,
                "image": Image.new("RGBA", (width, height), (*background, 255)),
                "objects": [],
            }
        ]
        self.active_layer = 0
        self._next_object_id = 1
        self._history: list[list[dict[str, object]]] = []

    @property
    def image(self) -> Image.Image:
        composite = Image.new("RGBA", (self.width, self.height), (*self.background, 255))
        for layer in self._layers:
            if layer["visible"]:
                composite = Image.alpha_composite(
                    composite,
                    self._render_layer(layer),
                )
        return composite.convert("RGB")

    @image.setter
    def image(self, value: Image.Image) -> None:
        self._layers = [
            {
                "name": "Background",
                "visible": True,
                "image": value.convert("RGBA"),
                "objects": [],
            }
        ]
        self.active_layer = 0

    @property
    def layer_names(self) -> tuple[str, ...]:
        return tuple(str(layer["name"]) for layer in self._layers)

    @property
    def layer_visibility(self) -> tuple[bool, ...]:
        return tuple(bool(layer["visible"]) for layer in self._layers)

    def add_layer(self, name: str | None = None) -> int:
        self._remember()
        self._layers.append(
            {
                "name": name or f"Layer {len(self._layers)}",
                "visible": True,
                "image": Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0)),
                "objects": [],
            }
        )
        self.active_layer = len(self._layers) - 1
        return self.active_layer

    def select_layer(self, index: int) -> None:
        if not 0 <= index < len(self._layers):
            raise IndexError("layer index out of range")
        self.active_layer = index

    def set_layer_visible(self, index: int, visible: bool) -> None:
        if not 0 <= index < len(self._layers):
            raise IndexError("layer index out of range")
        self._remember()
        self._layers[index]["visible"] = bool(visible)

    def move_layer(self, index: int, offset: int) -> int:
        """Move a layer in the compositing order and return its new index."""
        if not 0 <= index < len(self._layers):
            raise IndexError("layer index out of range")
        destination = min(len(self._layers) - 1, max(0, index + int(offset)))
        if destination == index:
            return index
        self._remember()
        layer = self._layers.pop(index)
        self._layers.insert(destination, layer)
        self.active_layer = destination
        return destination

    def rename_layer(self, index: int, name: str) -> None:
        if not 0 <= index < len(self._layers):
            raise IndexError("layer index out of range")
        cleaned = name.strip()
        if not cleaned:
            raise ValueError("layer name cannot be empty")
        self._remember()
        self._layers[index]["name"] = cleaned[:40]

    def remove_layer(self, index: int | None = None) -> bool:
        if len(self._layers) == 1:
            return False
        target = self.active_layer if index is None else index
        if not 0 <= target < len(self._layers):
            raise IndexError("layer index out of range")
        self._remember()
        del self._layers[target]
        self.active_layer = min(self.active_layer, len(self._layers) - 1)
        return True

    def flatten_layers(self) -> None:
        composite = self.image
        self._remember()
        self.image = composite

    @property
    def curve_objects(self) -> tuple[dict[str, object], ...]:
        """Return safe copies of persistent editable curve objects."""
        values: list[dict[str, object]] = []
        for layer_index, layer in enumerate(self._layers):
            for item in layer.get("objects", []):  # type: ignore[union-attr]
                if item.get("type") == "curve":
                    value = copy.deepcopy(item)
                    value["layer_index"] = layer_index
                    values.append(value)
        return tuple(values)

    def add_curve_object(
        self,
        start: Point,
        control: Point,
        end: Point,
        colour: Colour,
        size: int = 4,
    ) -> str:
        """Add a persistent quadratic curve that can be reshaped later."""
        self._remember()
        identifier = f"curve-{self._next_object_id}"
        self._next_object_id += 1
        objects = self._layers[self.active_layer].setdefault("objects", [])
        objects.append(  # type: ignore[union-attr]
            {
                "id": identifier,
                "type": "curve",
                "points": [
                    list(self._point(start)),
                    list(self._point(control)),
                    list(self._point(end)),
                ],
                "colour": list(colour),
                "size": max(1, int(size)),
            }
        )
        return identifier

    def edit_curve_point(
        self,
        object_id: str,
        point_index: int,
        point: Point,
    ) -> None:
        """Move one anchor/control point on a persistent curve."""
        if point_index not in {0, 1, 2}:
            raise IndexError("curve point index must be zero, one, or two")
        item = self._find_curve(object_id)
        self._remember()
        item["points"][point_index] = list(self._point(point))  # type: ignore[index]

    def remove_curve_object(self, object_id: str) -> bool:
        for layer in self._layers:
            objects = layer.get("objects", [])
            for index, item in enumerate(objects):  # type: ignore[arg-type]
                if item.get("id") == object_id:
                    self._remember()
                    del objects[index]  # type: ignore[index]
                    return True
        return False

    def nearest_curve(
        self,
        point: Point,
        maximum_distance: float = 24.0,
    ) -> str | None:
        """Find the nearest visible curve using sampled rendered geometry."""
        target = self._point(point)
        best: tuple[float, str] | None = None
        for layer in self._layers:
            if not layer["visible"]:
                continue
            for item in layer.get("objects", []):  # type: ignore[union-attr]
                if item.get("type") != "curve":
                    continue
                distance = min(
                    math.dist(target, sample)
                    for sample in self._curve_points(item, 40)
                )
                identifier = str(item["id"])
                if distance <= maximum_distance and (
                    best is None or distance < best[0]
                ):
                    best = (distance, identifier)
        return best[1] if best else None

    def nearest_curve_point(self, object_id: str, point: Point) -> int:
        item = self._find_curve(object_id)
        target = self._point(point)
        return min(
            range(3),
            key=lambda index: math.dist(target, item["points"][index]),  # type: ignore[index]
        )

    def curve_points(self, object_id: str) -> tuple[Point, Point, Point]:
        item = self._find_curve(object_id)
        return tuple(
            (int(point[0]), int(point[1]))
            for point in item["points"]  # type: ignore[union-attr]
        )  # type: ignore[return-value]

    def _remember(self) -> None:
        self._history.append(self._copy_layers())
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
        draw = ImageDraw.Draw(self._active_image())
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

    def effect_brush(
        self,
        points: Iterable[Point],
        colour: Colour,
        size: int = 8,
        effect: str = "solid",
        mirror_horizontal: bool = False,
    ) -> None:
        """Paint a deterministic solid, soft, textured, or scattered stroke."""
        path = [self._point(point) for point in points]
        if not path:
            return
        if effect == "solid" and not mirror_horizontal:
            self.brush(path, colour, size)
            return
        if effect not in {"soft", "texture", "scatter"}:
            if effect != "solid":
                raise ValueError(f"unknown brush effect: {effect}")
        paths = [path]
        if mirror_horizontal:
            paths.append([(self.width - 1 - x, y) for x, y in path])
        self._remember()
        overlay = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        radius = max(1, int(size) // 2)
        for stroke in paths:
            if effect == "solid":
                draw.line(stroke, fill=(*colour, 255), width=max(1, size), joint="curve")
                for x, y in (stroke[0], stroke[-1]):
                    draw.ellipse(
                        (x - radius, y - radius, x + radius, y + radius),
                        fill=(*colour, 255),
                    )
            elif effect == "soft":
                draw.line(
                    stroke,
                    fill=(*colour, 150),
                    width=max(2, int(size)),
                    joint="curve",
                )
                for x, y in stroke:
                    draw.ellipse(
                        (x - radius, y - radius, x + radius, y + radius),
                        fill=(*colour, 90),
                    )
            else:
                spacing = max(1, radius // 2)
                for path_index, (x, y) in enumerate(stroke):
                    for dab in range(7 if effect == "scatter" else 5):
                        angle = (path_index * 137 + dab * 83) * math.pi / 180
                        reach = (
                            radius * (0.35 + (dab % 4) * 0.22)
                            if effect == "scatter"
                            else radius * (0.15 + (dab % 3) * 0.18)
                        )
                        px = round(x + math.cos(angle) * reach)
                        py = round(y + math.sin(angle) * reach)
                        dot = max(1, spacing - (dab % 2))
                        alpha = 145 if effect == "scatter" else 105 + dab * 18
                        draw.ellipse(
                            (px - dot, py - dot, px + dot, py + dot),
                            fill=(*colour, min(230, alpha)),
                        )
        if effect == "soft":
            overlay = overlay.filter(ImageFilter.GaussianBlur(max(1, radius // 2)))
        self._active_image().alpha_composite(overlay)

    def line(
        self,
        start: Point,
        end: Point,
        colour: Colour,
        size: int = 6,
    ) -> None:
        self._remember()
        ImageDraw.Draw(self._active_image()).line(
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
        draw = ImageDraw.Draw(self._active_image())
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
        draw = ImageDraw.Draw(self._active_image())
        draw.ellipse(
            box,
            fill=colour if filled else None,
            outline=colour,
            width=max(1, size),
        )

    def fill(self, point: Point, colour: Colour) -> None:
        self._remember()
        ImageDraw.floodfill(self._active_image(), self._point(point), (*colour, 255))

    def polygon(
        self,
        points: Sequence[Point],
        colour: Colour,
        size: int = 4,
        filled: bool = False,
    ) -> None:
        vertices = [self._point(point) for point in points]
        if len(vertices) < 3:
            raise ValueError("polygon requires at least three points")
        self._remember()
        ImageDraw.Draw(self._active_image()).polygon(
            vertices,
            fill=colour if filled else None,
            outline=colour,
            width=max(1, size),
        )

    def bezier(
        self,
        start: Point,
        control: Point,
        end: Point,
        colour: Colour,
        size: int = 4,
        steps: int = 32,
    ) -> None:
        if steps < 2:
            raise ValueError("bezier steps must be at least two")
        points = []
        for index in range(steps + 1):
            t = index / steps
            one_minus = 1 - t
            points.append(
                (
                    round(one_minus * one_minus * start[0] + 2 * one_minus * t * control[0] + t * t * end[0]),
                    round(one_minus * one_minus * start[1] + 2 * one_minus * t * control[1] + t * t * end[1]),
                )
            )
        self.brush(points, colour, size)

    def gradient(
        self,
        start_colour: Colour,
        end_colour: Colour,
        *,
        vertical: bool = True,
    ) -> None:
        self._remember()
        layer = self._active_image()
        draw = ImageDraw.Draw(layer)
        extent = self.height if vertical else self.width
        for index in range(extent):
            ratio = index / max(1, extent - 1)
            colour = tuple(
                round(start + (end - start) * ratio)
                for start, end in zip(start_colour, end_colour)
            )
            if vertical:
                draw.line((0, index, self.width, index), fill=(*colour, 255))
            else:
                draw.line((index, 0, index, self.height), fill=(*colour, 255))

    def linear_gradient(
        self,
        start: Point,
        end: Point,
        start_colour: Colour,
        end_colour: Colour,
    ) -> None:
        """Fill the active layer with a directional two-colour gradient."""
        x1, y1 = self._point(start)
        x2, y2 = self._point(end)
        dx, dy = x2 - x1, y2 - y1
        length_squared = dx * dx + dy * dy
        if length_squared == 0:
            raise ValueError("gradient drag must have non-zero length")
        self._remember()
        gradient = Image.new("RGBA", (self.width, self.height))
        pixels = gradient.load()
        for y in range(self.height):
            for x in range(self.width):
                ratio = ((x - x1) * dx + (y - y1) * dy) / length_squared
                ratio = min(1.0, max(0.0, ratio))
                colour = tuple(
                    round(first + (second - first) * ratio)
                    for first, second in zip(start_colour, end_colour)
                )
                pixels[x, y] = (*colour, 255)
        self._layers[self.active_layer]["image"] = gradient

    def smudge(self, start: Point, end: Point, radius: int = 12) -> None:
        """Move a softly blurred patch along a short stroke."""
        self._remember()
        layer = self._active_image()
        x1, y1 = self._point(start)
        x2, y2 = self._point(end)
        box = (
            max(0, x1 - radius),
            max(0, y1 - radius),
            min(self.width, x1 + radius + 1),
            min(self.height, y1 + radius + 1),
        )
        patch = layer.crop(box).filter(ImageFilter.GaussianBlur(max(1, radius // 3)))
        layer.alpha_composite(
            patch,
            (
                min(self.width - patch.width, max(0, x2 - patch.width // 2)),
                min(self.height - patch.height, max(0, y2 - patch.height // 2)),
            ),
        )

    def clear(self) -> None:
        self._remember()
        self._layers = [
            {
                "name": "Background",
                "visible": True,
                "image": Image.new(
                    "RGBA",
                    (self.width, self.height),
                    (*self.background, 255),
                ),
                "objects": [],
            }
        ]
        self.active_layer = 0

    def undo(self) -> bool:
        if not self._history:
            return False
        self._layers = self._history.pop()
        self.active_layer = min(self.active_layer, len(self._layers) - 1)
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
            "history": [
                self._encode(self._composite_layers(layers))
                for layers in self._history
            ],
            "layer_history": [
                [
                    {
                        "name": layer["name"],
                        "visible": layer["visible"],
                        "image": self._encode(layer["image"]),  # type: ignore[arg-type]
                        "objects": copy.deepcopy(layer.get("objects", [])),
                    }
                    for layer in layers
                ]
                for layers in self._history
            ],
            "layers": [
                {
                    "name": layer["name"],
                    "visible": layer["visible"],
                    "image": self._encode(layer["image"]),  # type: ignore[arg-type]
                    "objects": copy.deepcopy(layer.get("objects", [])),
                }
                for layer in self._layers
            ],
            "active_layer": self.active_layer,
            "next_object_id": self._next_object_id,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> "CanvasModel":
        model = cls(
            width=int(payload["width"]),
            height=int(payload["height"]),
            background=tuple(payload["background"]),  # type: ignore[arg-type]
            max_history=int(payload["max_history"]),
        )
        layers = payload.get("layers")
        if isinstance(layers, list) and layers:
            model._layers = [
                {
                    "name": str(value["name"]),
                    "visible": bool(value["visible"]),
                    "image": cls._decode(str(value["image"])).convert("RGBA"),
                    "objects": copy.deepcopy(value.get("objects", [])),
                }
                for value in layers
            ]
            model.active_layer = min(
                int(payload.get("active_layer", 0)),
                len(model._layers) - 1,
            )
            model._next_object_id = int(payload.get("next_object_id", 1))
        else:
            model.image = cls._decode(str(payload["image"]))
        layer_history = payload.get("layer_history")
        if isinstance(layer_history, list):
            model._history = [
                [
                    {
                        "name": str(value["name"]),
                        "visible": bool(value["visible"]),
                        "image": cls._decode(str(value["image"])).convert("RGBA"),
                        "objects": copy.deepcopy(value.get("objects", [])),
                    }
                    for value in snapshot
                ]
                for snapshot in layer_history
            ]
        else:
            model._history = [
                [
                    {
                        "name": "Background",
                        "visible": True,
                        "image": cls._decode(str(value)).convert("RGBA"),
                        "objects": [],
                    }
                ]
                for value in payload.get("history", [])  # type: ignore[union-attr]
            ]
        return model

    def _active_image(self) -> Image.Image:
        return self._layers[self.active_layer]["image"]  # type: ignore[return-value]

    def _copy_layers(self) -> list[dict[str, object]]:
        return [
            {
                "name": layer["name"],
                "visible": layer["visible"],
                "image": layer["image"].copy(),  # type: ignore[union-attr]
                "objects": copy.deepcopy(layer.get("objects", [])),
            }
            for layer in self._layers
        ]

    def _composite_layers(self, layers: list[dict[str, object]]) -> Image.Image:
        composite = Image.new("RGBA", (self.width, self.height), (*self.background, 255))
        for layer in layers:
            if layer["visible"]:
                composite = Image.alpha_composite(
                    composite,
                    self._render_layer(layer),
                )
        return composite.convert("RGB")

    def _render_layer(self, layer: dict[str, object]) -> Image.Image:
        rendered = layer["image"].copy()  # type: ignore[union-attr]
        draw = ImageDraw.Draw(rendered)
        for item in layer.get("objects", []):  # type: ignore[union-attr]
            if item.get("type") != "curve":
                continue
            points = self._curve_points(item, 48)
            colour = tuple(int(value) for value in item["colour"])
            size = max(1, int(item.get("size", 4)))
            draw.line(points, fill=(*colour, 255), width=size, joint="curve")
        return rendered

    def _find_curve(self, object_id: str) -> dict[str, object]:
        for layer in self._layers:
            for item in layer.get("objects", []):  # type: ignore[union-attr]
                if item.get("type") == "curve" and item.get("id") == object_id:
                    return item
        raise KeyError(f"curve object does not exist: {object_id}")

    @staticmethod
    def _curve_points(
        item: dict[str, object],
        steps: int,
    ) -> list[Point]:
        start, control, end = item["points"]  # type: ignore[misc]
        points: list[Point] = []
        for index in range(steps + 1):
            t = index / steps
            one_minus = 1 - t
            points.append(
                (
                    round(
                        one_minus * one_minus * start[0]
                        + 2 * one_minus * t * control[0]
                        + t * t * end[0]
                    ),
                    round(
                        one_minus * one_minus * start[1]
                        + 2 * one_minus * t * control[1]
                        + t * t * end[1]
                    ),
                )
            )
        return points

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
