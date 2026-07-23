"""Locate the complete Paint UI and assess the canvas from screenshot pixels."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from .constants import CANVAS_LOCATOR, PALETTE, PALETTE_MARKERS, TOOL_MARKERS

Point = tuple[int, int]


@dataclass(frozen=True)
class LocatedInterface:
    controls: dict[str, Point]
    palette: dict[str, Point]
    canvas_origin: Point
    canvas_size: Point


def locate_interface(screenshot: Path) -> LocatedInterface:
    """Recover all interaction targets from visible fiducial pixels."""
    with Image.open(screenshot) as source:
        image = source.convert("RGB")
        controls = {
            name: _marker_center(image, colour)
            for name, colour in TOOL_MARKERS.items()
        }
        palette = {
            name: _marker_center(image, colour)
            for name, colour in PALETTE_MARKERS.items()
        }
        xs: list[int] = []
        ys: list[int] = []
        pixels = image.load()
        for y in range(image.height):
            for x in range(image.width):
                if pixels[x, y] == CANVAS_LOCATOR:
                    xs.append(x)
                    ys.append(y)
        if not xs:
            raise ValueError("visible canvas border could not be located")
        border = 4
        origin = (min(xs) + border, min(ys) + border)
        size = (
            max(xs) - min(xs) + 1 - border * 2,
            max(ys) - min(ys) + 1 - border * 2,
        )
        if size[0] < 100 or size[1] < 100:
            raise ValueError("located canvas is implausibly small")
        return LocatedInterface(controls, palette, origin, size)


def assess_canvas(screenshot: Path, interface: LocatedInterface) -> str:
    """Return a concise visual assessment based only on visible canvas pixels."""
    with Image.open(screenshot) as source:
        image = source.convert("RGB")
        x, y = interface.canvas_origin
        width, height = interface.canvas_size
        canvas = image.crop((x, y, x + width, y + height))
        counts = canvas.getcolors(maxcolors=width * height) or []
        present = {
            name
            for name, colour in PALETTE.items()
            if any(pixel == colour and count > 80 for count, pixel in counts)
        }
        total = width * height
        light = sum(
            count
            for count, colour in counts
            if sum(colour) / 3 >= 185
        )
        dark = sum(
            count
            for count, colour in counts
            if sum(colour) / 3 <= 90
        )
        balance = "strong light-dark contrast" if light / total > 0.03 and dark / total > 0.08 else "moderate tonal contrast"
        return f"{len(present)} palette colours visible; {balance}; canvas edges remain intact."


def canvas_point(interface: LocatedInterface, local: Point) -> Point:
    x, y = interface.canvas_origin
    width, height = interface.canvas_size
    return (
        x + min(width - 1, max(0, local[0])),
        y + min(height - 1, max(0, local[1])),
    )


def _marker_center(image: Image.Image, colour: tuple[int, int, int]) -> Point:
    pixels = image.load()
    xs: list[int] = []
    ys: list[int] = []
    for y in range(image.height):
        for x in range(image.width):
            if pixels[x, y] == colour:
                xs.append(x)
                ys.append(y)
    if len(xs) < 16:
        raise ValueError(f"visible control marker {colour} could not be located")
    return (round((min(xs) + max(xs)) / 2), round((min(ys) + max(ys)) / 2))

