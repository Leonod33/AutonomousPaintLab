"""Shared visual constants for the Paint application."""

from __future__ import annotations

from collections import OrderedDict

WINDOW_SIZE = (1240, 760)
CANVAS_SIZE = (760, 600)
CANVAS_ORIGIN = (20, 136)
CANVAS_BORDER_WIDTH = 4
CANVAS_LOCATOR = (65, 202, 255)

BACKGROUND = (12, 18, 32)
PANEL = (24, 33, 52)
PANEL_LIGHT = (34, 46, 69)
TEXT = (239, 244, 255)
MUTED = (151, 164, 190)
ACCENT = (94, 234, 212)
SELECTED = (52, 211, 153)
BUTTON_BORDER = (73, 88, 116)

TOOLS = (
    "brush",
    "line",
    "rectangle",
    "ellipse",
    "curve",
    "edit",
    "gradient",
    "smudge",
    "fill",
    "eyedropper",
)
STYLE_CONTROLS = ("outline", "filled", "both")
SIZE_CONTROLS = ("size_down", "size_up")
UTILITY_CONTROLS = ("brush_fx", "symmetry", "guides", "undo", "clear", "refs", "save")

# These small, visible fiducials let the deterministic screenshot controller
# find controls from pixels without importing renderer geometry.
TOOL_MARKERS = OrderedDict(
    [
        ("brush", (255, 99, 132)),
        ("line", (120, 190, 255)),
        ("rectangle", (180, 120, 255)),
        ("ellipse", (255, 170, 70)),
        ("curve", (70, 215, 255)),
        ("edit", (255, 125, 210)),
        ("gradient", (115, 140, 255)),
        ("smudge", (190, 155, 125)),
        ("fill", (80, 230, 170)),
        ("eyedropper", (238, 140, 255)),
        ("outline", (255, 150, 190)),
        ("filled", (155, 240, 135)),
        ("both", (255, 188, 105)),
        ("size_down", (120, 225, 245)),
        ("size_up", (245, 170, 120)),
        ("brush_fx", (180, 245, 160)),
        ("symmetry", (245, 150, 225)),
        ("guides", (140, 205, 255)),
        ("undo", (255, 220, 90)),
        ("clear", (255, 120, 80)),
        ("refs", (90, 180, 255)),
        ("save", (110, 240, 250)),
    ]
)

PALETTE = OrderedDict(
    [
        ("white", (245, 247, 250)),
        ("ink", (18, 23, 35)),
        ("navy", (25, 48, 92)),
        ("storm", (91, 110, 132)),
        ("yellow", (255, 213, 79)),
        ("sky", (111, 195, 255)),
        ("green", (72, 166, 105)),
        ("coral", (244, 112, 112)),
        ("teal", (45, 185, 177)),
        ("violet", (147, 112, 219)),
        ("cream", (244, 225, 188)),
        ("tan", (198, 145, 92)),
        ("brown", (105, 68, 50)),
        ("pink", (241, 151, 171)),
    ]
)

PALETTE_MARKERS = OrderedDict(
    (
        name,
        (
            (31 + index * 17) % 256,
            (250 - index * 13) % 256,
            (118 + index * 11) % 256,
        ),
    )
    for index, name in enumerate(PALETTE)
)
