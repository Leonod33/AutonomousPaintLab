"""Seeded, reproducible plans for the first visually testable briefs."""

from __future__ import annotations

from dataclasses import dataclass
import random

Point = tuple[int, int]


@dataclass(frozen=True)
class PlanAction:
    tool: str
    colour: str
    start: Point
    end: Point | None
    goal: str
    intent: str


@dataclass(frozen=True)
class ArtPlan:
    prompt: str
    seed: int
    actions: tuple[PlanAction, ...]
    revision_actions: tuple[PlanAction, ...]


def make_plan(prompt: str, seed: int, variant_index: int = 0) -> ArtPlan:
    if not 0 <= variant_index <= 4:
        raise ValueError("variant index must be between zero and four")
    normalized = " ".join(prompt.lower().split())
    if "lighthouse" in normalized:
        return _lighthouse_plan(prompt, seed)
    if "robot" in normalized and "flower" in normalized:
        return _robot_plan(prompt, seed, variant_index)
    raise ValueError(
        "the deterministic starter planner supports lighthouse/storm and "
        "robot/square-flower briefs; use model-vision mode for other prompts"
    )


def _action(
    tool: str,
    colour: str,
    start: Point,
    end: Point | None,
    goal: str,
    intent: str,
) -> PlanAction:
    return PlanAction(tool, colour, start, end, goal, intent)


def _lighthouse_plan(prompt: str, seed: int) -> ArtPlan:
    rng = random.Random(seed)
    tower_x = 355 + rng.randint(-20, 20)
    horizon = 405 + rng.randint(-15, 12)
    actions: list[PlanAction] = [
        _action("fill", "navy", (20, 20), None, "Establish the storm.", "Flood the canvas with navy."),
        _action("line", "storm", (0, horizon), (759, horizon), "Separate sea and sky.", "Draw a firm horizon."),
        _action("fill", "storm", (30, 560), None, "Build the rough sea.", "Fill below the horizon with storm grey."),
        _action("rectangle", "white", (tower_x, 215), (tower_x + 88, 520), "Place the focal structure.", "Outline a tall white lighthouse."),
        _action("fill", "white", (tower_x + 30, 300), None, "Make the lighthouse readable.", "Fill the tower white."),
        _action("rectangle", "yellow", (tower_x - 8, 174), (tower_x + 96, 224), "Add the beacon room.", "Outline the lantern in yellow."),
        _action("fill", "yellow", (tower_x + 30, 195), None, "Light the beacon.", "Fill the lantern yellow."),
        _action("line", "white", (tower_x - 18, 174), (tower_x + 44, 135), "Cap the lighthouse.", "Draw the left roof slope."),
        _action("line", "white", (tower_x + 44, 135), (tower_x + 106, 174), "Cap the lighthouse.", "Draw the right roof slope."),
        _action("line", "yellow", (tower_x + 95, 188), (690, 126), "Project the beacon.", "Send a yellow beam into the storm."),
        _action("line", "yellow", (tower_x + 95, 208), (690, 178), "Project the beacon.", "Give the beam a lower edge."),
    ]
    for index in range(7):
        x = 20 + index * 108 + rng.randint(-12, 12)
        y = horizon + 38 + (index % 3) * 42
        actions.append(
            _action(
                "brush",
                "white",
                (x, y),
                (min(750, x + 80), y - 14),
                "Show a turbulent sea.",
                "Add a bright diagonal wave crest.",
            )
        )
    for index in range(8):
        x = 45 + index * 91 + rng.randint(-18, 18)
        y = 70 + (index % 3) * 72
        actions.append(
            _action(
                "line",
                "storm",
                (x, y),
                (x - 34, y + 62),
                "Make the storm visible.",
                "Add a slanting rain stroke.",
            )
        )
    actions.extend(
        [
            _action("line", "yellow", (138, 80), (105, 151), "Add one dramatic accent.", "Start a lightning bolt."),
            _action("line", "yellow", (105, 151), (145, 143), "Add one dramatic accent.", "Cut the bolt sideways."),
            _action("line", "yellow", (145, 143), (112, 220), "Add one dramatic accent.", "Finish the lightning bolt."),
            _action("rectangle", "yellow", (tower_x + 26, 300), (tower_x + 60, 342), "Give the tower warmth.", "Outline a lit window."),
            _action("fill", "yellow", (tower_x + 42, 320), None, "Give the tower warmth.", "Fill the lit window."),
        ]
    )
    revision = (
        _action(
            "brush",
            "white",
            (tower_x - 50, horizon + 80),
            (tower_x + 135, horizon + 58),
            "Clarify the focal silhouette.",
            "Add one final foreground foam highlight.",
        ),
    )
    return ArtPlan(prompt, seed, tuple(actions), revision)


def _robot_plan(prompt: str, seed: int, variant_index: int = 0) -> ArtPlan:
    rng = random.Random(seed)
    robot_x = 210 + rng.randint(-16, 16)
    ground = 465 + rng.randint(-10, 10)
    if variant_index == 0:
        head_colour = "coral"
        chest_colour = "teal"
    else:
        head_colour = rng.choice(["coral", "teal", "violet"])
        chest_colour = rng.choice(
            [
                colour
                for colour in ("coral", "teal", "violet")
                if colour != head_colour
            ]
        )
    left_hand = (
        (robot_x - 85, 390)
        if variant_index == 0
        else (
            robot_x - 75 - rng.randint(0, 22),
            380 + rng.randint(-12, 16),
        )
    )
    right_hand = (
        (robot_x + 250, 365)
        if variant_index == 0
        else (
            robot_x + 238 + rng.randint(0, 24),
            350 + rng.randint(-8, 24),
        )
    )
    actions: list[PlanAction] = [
        _action("fill", "sky", (20, 20), None, "Set a cheerful scene.", "Fill the sky bright blue."),
        _action("line", "green", (0, ground), (759, ground), "Create a garden floor.", "Draw the ground line."),
        _action("fill", "green", (20, 570), None, "Create a garden floor.", "Fill the garden green."),
        _action("rectangle", "ink", (robot_x, 255), (robot_x + 180, 440), "Build the robot body.", "Outline a square torso."),
        _action("fill", "white", (robot_x + 70, 330), None, "Keep the robot bright.", "Fill the torso white."),
        _action("rectangle", "ink", (robot_x + 18, 150), (robot_x + 162, 267), "Build the robot head.", "Outline a broad square head."),
        _action(
            "fill",
            head_colour,
            (robot_x + 70, 210),
            None,
            "Make the robot cheerful.",
            f"Fill the head {head_colour}.",
        ),
        _action("ellipse", "white", (robot_x + 44, 182), (robot_x + 75, 215), "Give the robot a face.", "Draw the left round eye."),
        _action("ellipse", "white", (robot_x + 105, 182), (robot_x + 136, 215), "Give the robot a face.", "Draw the right round eye."),
        _action("line", "ink", (robot_x + 62, 235), (robot_x + 118, 235), "Give the robot a face.", "Draw a simple smile."),
        _action("line", "ink", (robot_x + 90, 150), (robot_x + 90, 112), "Add a friendly antenna.", "Draw the antenna stem."),
        _action("ellipse", "yellow", (robot_x + 74, 88), (robot_x + 106, 120), "Add a friendly antenna.", "Draw the antenna light."),
        _action(
            "line",
            "ink",
            (robot_x, 305),
            left_hand,
            "Pose the gardener.",
            "Reach one arm toward the flowers.",
        ),
        _action(
            "line",
            "ink",
            (robot_x + 180, 305),
            right_hand,
            "Pose the gardener.",
            "Reach the other arm outward.",
        ),
        _action("line", "ink", (robot_x + 45, 440), (robot_x + 20, ground), "Plant the robot firmly.", "Draw the left leg."),
        _action("line", "ink", (robot_x + 135, 440), (robot_x + 160, ground), "Plant the robot firmly.", "Draw the right leg."),
    ]
    if variant_index == 0:
        flower_xs = [470, 555, 640, 710]
        flower_colours = ["yellow", "coral", "violet", "yellow"]
        flower_tops = [
            ground - 105 - (index % 2) * 25
            for index in range(len(flower_xs))
        ]
    else:
        flower_xs = [
            470 + rng.randint(-8, 7),
            555 + rng.randint(-8, 7),
            640 + rng.randint(-8, 7),
            710 + rng.randint(-5, 4),
        ]
        flower_colours = [
            "yellow",
            "coral",
            "violet",
            rng.choice(["yellow", "teal"]),
        ]
        rng.shuffle(flower_colours)
        flower_tops = [ground - 92 - rng.randint(0, 48) for _ in flower_xs]
    for index, (x, colour) in enumerate(zip(flower_xs, flower_colours)):
        top = flower_tops[index]
        actions.extend(
            [
                _action("line", "ink", (x + 22, ground), (x + 22, top + 42), "Plant square flowers.", "Draw a straight flower stem."),
                _action("rectangle", colour, (x, top), (x + 44, top + 44), "Plant square flowers.", "Outline a square blossom."),
                _action("fill", colour, (x + 22, top + 22), None, "Plant square flowers.", "Fill the square blossom."),
            ]
        )
    actions.extend(
        [
            _action(
                "rectangle",
                chest_colour,
                (robot_x + 54, 298),
                (robot_x + 126, 365),
                "Add a robot detail.",
                f"Outline a {chest_colour} chest panel.",
            ),
            _action(
                "fill",
                chest_colour,
                (robot_x + 88, 330),
                None,
                "Add a robot detail.",
                f"Fill the {chest_colour} chest panel.",
            ),
        ]
    )
    revision = (
        _action(
            "line",
            "yellow",
            (robot_x + 67, 245),
            (robot_x + 113, 245),
            "Strengthen the cheerful expression.",
            "Add a bright smile highlight.",
        ),
    )
    return ArtPlan(prompt, seed, tuple(actions), revision)
