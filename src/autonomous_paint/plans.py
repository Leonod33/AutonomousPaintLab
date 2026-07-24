"""Seeded, reproducible plans for the first visually testable briefs."""

from __future__ import annotations

from dataclasses import dataclass, replace
import random

from .quality import DETAIL_PASSES, allocate_pass_actions

Point = tuple[int, int]


@dataclass(frozen=True)
class PlanAction:
    tool: str
    colour: str
    start: Point
    end: Point | None
    goal: str
    intent: str
    pass_name: str = "construction"
    detail_key: str = "subject"
    brush_size: int | None = None
    shape_mode: str = "outline"


@dataclass(frozen=True)
class ArtPlan:
    prompt: str
    seed: int
    actions: tuple[PlanAction, ...]
    revision_actions: tuple[PlanAction, ...]
    pass_allocations: tuple[tuple[str, int], ...] = ()
    detail_ledger: tuple[str, ...] = ()


def make_plan(prompt: str, seed: int, variant_index: int = 0) -> ArtPlan:
    if not 0 <= variant_index <= 4:
        raise ValueError("variant index must be between zero and four")
    normalized = " ".join(prompt.lower().split())
    if "lighthouse" in normalized:
        return _lighthouse_plan(prompt, seed)
    if "robot" in normalized and "flower" in normalized:
        return _robot_plan(prompt, seed, variant_index)
    if "guinea pig" in normalized or "cuddle cup" in normalized:
        return _guinea_pig_plan(prompt, seed, variant_index)
    raise ValueError(
        "the deterministic starter planner supports lighthouse/storm and "
        "robot/square-flower, and guinea-pig/cuddle-cup briefs; use "
        "model-vision mode for other prompts"
    )


def prepare_plan(
    prompt: str,
    seed: int,
    variant_index: int = 0,
    *,
    target_actions: int,
    maximum_actions: int,
    revision_budget: int,
) -> ArtPlan:
    """Expand a seed plan into explicit coarse-to-fine passes near the target."""
    plan = make_plan(prompt, seed, variant_index)
    desired_revisions = min(revision_budget, target_actions)
    main_target = min(maximum_actions - desired_revisions, target_actions - desired_revisions)
    if main_target < len(plan.actions):
        if len(plan.actions) + desired_revisions > maximum_actions:
            raise ValueError("seeded plan exceeds maximum action budget")
        main_target = len(plan.actions)
    actions = list(_stage_actions(plan.actions))
    actions.extend(
        _detail_actions(
            prompt,
            seed,
            variant_index,
            max(0, main_target - len(actions)),
        )
    )
    allocations = allocate_pass_actions(len(actions))
    staged = _rebalance_passes(actions, allocations)
    detail_ledger = tuple(
        dict.fromkeys(action.detail_key for action in staged if action.detail_key)
    )
    revisions = list(_stage_revisions(plan.revision_actions[:desired_revisions]))
    if len(revisions) < desired_revisions:
        extra = _detail_actions(
            prompt,
            seed + 37,
            variant_index,
            desired_revisions - len(revisions),
        )
        revisions.extend(
            replace(
                action,
                pass_name="focal_finish",
                goal="Resolve the strongest visible checkpoint finding.",
            )
            for action in extra
        )
    if len(staged) + len(revisions) > maximum_actions:
        revisions = revisions[: maximum_actions - len(staged)]
    return ArtPlan(
        plan.prompt,
        plan.seed,
        tuple(staged),
        tuple(revisions),
        tuple((name, allocations[name]) for name in DETAIL_PASSES),
        detail_ledger,
    )


def _action(
    tool: str,
    colour: str,
    start: Point,
    end: Point | None,
    goal: str,
    intent: str,
    pass_name: str = "construction",
    detail_key: str = "subject",
    brush_size: int | None = None,
    shape_mode: str = "outline",
) -> PlanAction:
    return PlanAction(
        tool,
        colour,
        start,
        end,
        goal,
        intent,
        pass_name,
        detail_key,
        brush_size,
        shape_mode,
    )


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


def _guinea_pig_plan(
    prompt: str,
    seed: int,
    variant_index: int = 0,
) -> ArtPlan:
    """Build a recognizable resting guinea pig with a soft, enclosing bed."""
    rng = random.Random(seed)
    shift_x = (-34, 0, 30, -12, 18)[variant_index]
    head_x = shift_x + (0, 42, -24, 25, -12)[variant_index]
    background_colour = ("cream", "navy", "cream", "storm", "tan")[variant_index]
    shadow_colour = ("storm", "violet", "brown", "navy", "storm")[variant_index]
    cup_colour = ("teal", "violet", "coral", "navy", "green")[variant_index]
    body_colour = ("tan", "brown", "cream", "tan", "brown")[variant_index]
    cx = 380 + shift_x
    actions: list[PlanAction] = [
        _action(
            "fill", background_colour, (10, 10), None,
            "Establish a warm quiet setting.", "Fill the backdrop warm cream.",
            "composition", "setting",
        ),
        _action(
            "ellipse", shadow_colour, (105, 438), (675, 548),
            "Ground the cuddle cup.", "Place a soft oval cast shadow.",
            "composition", "depth", None, "filled",
        ),
        _action(
            "ellipse", cup_colour, (92, 250), (688, 535),
            "Build the cuddle cup.", "Paint the padded outer cup as a broad oval.",
            "construction", "cuddle_cup", None, "filled",
        ),
        _action(
            "ellipse", "ink", (125, 275), (655, 482),
            "Open the cup around the animal.", "Define the dark inner opening.",
            "construction", "cuddle_cup", None, "filled",
        ),
        _action(
            "ellipse", "cream", (151, 302), (629, 474),
            "Show the plush inner cushion.", "Add a light padded inner oval.",
            "form", "cuddle_cup", None, "filled",
        ),
        _action(
            "ellipse", body_colour, (205 + shift_x, 220), (566 + shift_x, 454),
            "Place the resting guinea pig.", "Paint a low rounded body nestled in the cup.",
            "construction", "guinea_pig", None, "filled",
        ),
        _action(
            "ellipse", body_colour, (185 + head_x, 205), (385 + head_x, 382),
            "Build the guinea pig head.", "Add a round head resting toward the left.",
            "construction", "guinea_pig", None, "filled",
        ),
        _action(
            "ellipse", "coral", (194 + head_x, 190), (264 + head_x, 258),
            "Add the near ear.", "Paint a small folded pink ear.",
            "form", "anatomy", None, "filled",
        ),
        _action(
            "ellipse", "brown", (205 + head_x, 201), (252 + head_x, 247),
            "Give the ear a furred rim.", "Add a smaller brown ear inset.",
            "materials", "fur", None, "filled",
        ),
        _action(
            "ellipse", "white", (225 + head_x, 250), (278 + head_x, 302),
            "Place the visible eye.", "Paint a bright eye surround.",
            "focal_finish", "face", None, "filled",
        ),
        _action(
            "ellipse", "ink", (238 + head_x, 258), (270 + head_x, 292),
            "Focus the expression.", "Add the glossy dark eye.",
            "focal_finish", "face", None, "filled",
        ),
        _action(
            "ellipse", "white", (244 + head_x, 262), (254 + head_x, 272),
            "Make the eye feel alive.", "Place a tiny eye catchlight.",
            "lighting", "face", None, "filled",
        ),
        _action(
            "ellipse", "coral", (164 + head_x, 310), (220 + head_x, 357),
            "Shape the muzzle.", "Add the soft pink nose pad.",
            "form", "face", None, "filled",
        ),
        _action(
            "ellipse", "ink", (171 + head_x, 321), (195 + head_x, 342),
            "Finish the nose.", "Place the small dark nostril.",
            "focal_finish", "face", None, "filled",
        ),
        _action(
            "ellipse", "cream", (284 + shift_x, 235), (420 + shift_x, 423),
            "Create a believable fur patch.", "Add a pale shoulder patch.",
            "materials", "fur", None, "filled",
        ),
        _action(
            "ellipse", "white", (452 + shift_x, 354), (528 + shift_x, 422),
            "Show a tucked hind foot.", "Add a small pale rear paw.",
            "form", "anatomy", None, "filled",
        ),
        _action(
            "ellipse", "white", (270 + shift_x, 386), (344 + shift_x, 442),
            "Show a tucked front foot.", "Add the resting front paw.",
            "form", "anatomy", None, "filled",
        ),
        _action(
            "line", "storm", (126, 411), (654, 411),
            "Clarify the padded front rim.", "Draw a curved-looking seam across the cup front.",
            "materials", "cuddle_cup", 7,
        ),
        _action(
            "line", "white", (142, 398), (640, 398),
            "Light the plush rim.", "Add a soft upper highlight to the cup.",
            "lighting", "cuddle_cup", 5,
        ),
        _action(
            "line", "ink", (180 + head_x, 346), (139 + head_x, 336),
            "Add whiskers.", "Draw the upper whisker.",
            "focal_finish", "face", 2,
        ),
        _action(
            "line", "ink", (181 + head_x, 354), (132 + head_x, 357),
            "Add whiskers.", "Draw the middle whisker.",
            "focal_finish", "face", 2,
        ),
        _action(
            "line", "ink", (184 + head_x, 361), (143 + head_x, 376),
            "Add whiskers.", "Draw the lower whisker.",
            "focal_finish", "face", 2,
        ),
    ]
    revisions = tuple(
        [
            _action(
                "brush", "white", (220 + shift_x + index * 20, 238 + (index % 2) * 12),
                (238 + shift_x + index * 20, 230 + (index % 2) * 12),
                "Resolve the strongest review finding.",
                "Add a controlled fur highlight without changing the silhouette.",
                "focal_finish", "fur", 3,
            )
            for index in range(8)
        ]
        + [
            _action(
                "line", "storm", (180 + index * 48, 455), (205 + index * 48, 465),
                "Resolve the strongest review finding.",
                "Strengthen one short cushion seam on the front rim.",
                "focal_finish", "cuddle_cup", 3,
            )
            for index in range(4)
        ]
    )
    return ArtPlan(prompt, seed, tuple(actions), revisions)


def _stage_actions(actions: tuple[PlanAction, ...]) -> tuple[PlanAction, ...]:
    """Give legacy plans explicit stages without changing their geometry."""
    staged: list[PlanAction] = []
    count = len(actions)
    for index, action in enumerate(actions):
        ratio = index / max(1, count - 1)
        if ratio < 0.12:
            pass_name = "composition"
        elif ratio < 0.34:
            pass_name = "construction"
        elif ratio < 0.52:
            pass_name = "form"
        elif ratio < 0.67:
            pass_name = "materials"
        elif ratio < 0.80:
            pass_name = "lighting"
        elif ratio < 0.92:
            pass_name = "texture"
        else:
            pass_name = "focal_finish"
        staged.append(replace(action, pass_name=pass_name))
    return tuple(staged)


def _stage_revisions(actions: tuple[PlanAction, ...]) -> tuple[PlanAction, ...]:
    return tuple(
        replace(action, pass_name="focal_finish", detail_key=action.detail_key or "revision")
        for action in actions
    )


def _rebalance_passes(
    actions: list[PlanAction],
    allocations: dict[str, int],
) -> list[PlanAction]:
    staged: list[PlanAction] = []
    index = 0
    for pass_name in DETAIL_PASSES:
        for _ in range(allocations[pass_name]):
            staged.append(replace(actions[index], pass_name=pass_name))
            index += 1
    return staged


def _detail_actions(
    prompt: str,
    seed: int,
    variant_index: int,
    count: int,
) -> list[PlanAction]:
    """Generate small, prompt-specific marks instead of budget-filling noise."""
    normalized = prompt.lower()
    rng = random.Random(seed * 7919 + variant_index * 104729)
    actions: list[PlanAction] = []
    for index in range(count):
        if "guinea pig" in normalized or "cuddle cup" in normalized:
            if index % 5 in {0, 1, 2}:
                x = rng.randint(220, 535)
                y = rng.randint(235, 410)
                length = rng.randint(10, 25)
                colour = rng.choice(("brown", "cream", "white", "tan"))
                actions.append(
                    _action(
                        "brush", colour, (x, y), (x + length, y - rng.randint(3, 10)),
                        "Build directional fur texture.",
                        "Add one short fur strand following the rounded body.",
                        "texture", "fur", rng.choice((2, 3, 4)),
                    )
                )
            else:
                x = rng.randint(135, 625)
                y = rng.randint(420, 492)
                colour = rng.choice(("white", "storm", "teal", "violet", "coral"))
                actions.append(
                    _action(
                        "line", colour, (x, y), (min(650, x + rng.randint(14, 34)), y + rng.randint(-5, 7)),
                        "Make the cuddle cup visibly plush.",
                        "Add one short rim seam or fabric highlight.",
                        "materials", "cuddle_cup", rng.choice((2, 3, 4)),
                    )
                )
        elif "lighthouse" in normalized:
            if index % 3:
                x = rng.randint(20, 735)
                y = rng.randint(45, 380)
                actions.append(
                    _action(
                        "line", "storm", (x, y), (x - rng.randint(12, 35), y + rng.randint(25, 55)),
                        "Layer the storm atmosphere.",
                        "Add one varied rain stroke with visible direction.",
                        "texture", "weather", rng.choice((2, 3, 4)),
                    )
                )
            else:
                x = rng.randint(25, 690)
                y = rng.randint(430, 570)
                actions.append(
                    _action(
                        "brush", "white", (x, y), (x + rng.randint(25, 65), y - rng.randint(5, 18)),
                        "Increase depth in the sea.",
                        "Add a small wave highlight at a distinct scale.",
                        "lighting", "sea", rng.choice((2, 3, 4)),
                    )
                )
        else:
            if index % 3 == 0:
                x = rng.randint(430, 735)
                y = rng.randint(420, 555)
                actions.append(
                    _action(
                        "line", "ink", (x, y), (x + rng.randint(-8, 8), y - rng.randint(12, 30)),
                        "Enrich the garden setting.",
                        "Add one varied grass blade behind the flower group.",
                        "texture", "setting", rng.choice((2, 3)),
                    )
                )
            else:
                x = rng.randint(220, 390)
                y = rng.randint(175, 420)
                colour = rng.choice(("teal", "coral", "violet", "yellow", "white"))
                actions.append(
                    _action(
                        "line", colour, (x, y), (x + rng.randint(8, 24), y + rng.randint(-6, 6)),
                        "Add mechanical surface detail.",
                        "Place one controlled panel highlight or joint mark.",
                        "materials", "robot", rng.choice((2, 3, 4)),
                    )
                )
    return actions
