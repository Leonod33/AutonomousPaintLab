"""Quality profiles, staged action budgets, and save-gate policy."""

from __future__ import annotations

from dataclasses import asdict, dataclass


DETAIL_PASSES = (
    "composition",
    "construction",
    "form",
    "materials",
    "lighting",
    "texture",
    "focal_finish",
)


@dataclass(frozen=True)
class DetailProfile:
    name: str
    minimum_actions: int
    target_actions: int
    maximum_actions: int
    revision_actions: int
    required_passes: tuple[str, ...]
    reference_minimum: int


DETAIL_PROFILES: dict[str, DetailProfile] = {
    "draft": DetailProfile(
        "draft",
        12,
        24,
        50,
        3,
        ("composition", "construction", "focal_finish"),
        0,
    ),
    "standard": DetailProfile(
        "standard",
        35,
        70,
        100,
        10,
        ("composition", "construction", "form", "lighting", "focal_finish"),
        0,
    ),
    "high": DetailProfile(
        "high",
        80,
        140,
        200,
        24,
        DETAIL_PASSES,
        2,
    ),
    "ultra": DetailProfile(
        "ultra",
        140,
        220,
        320,
        40,
        DETAIL_PASSES,
        3,
    ),
}


@dataclass(frozen=True)
class BudgetPolicy:
    """A floor, a planning target, and a hard ceiling for one artwork."""

    detail_level: str
    minimum_actions: int
    target_actions: int
    maximum_actions: int
    revision_actions: int
    review_checkpoints: int
    required_passes: tuple[str, ...]
    reference_minimum: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def resolve_budget_policy(
    *,
    action_budget: int | None = None,
    min_actions: int | None = None,
    target_actions: int | None = None,
    max_actions: int | None = None,
    review_budget: int = 3,
    revision_budget: int | None = None,
    detail_level: str = "standard",
) -> BudgetPolicy:
    """Resolve legacy ``--actions`` and the v2 floor/target/ceiling controls."""
    if detail_level not in DETAIL_PROFILES:
        choices = ", ".join(DETAIL_PROFILES)
        raise ValueError(f"detail level must be one of: {choices}")
    profile = DETAIL_PROFILES[detail_level]
    ceiling = (
        max_actions
        if max_actions is not None
        else action_budget
        if action_budget is not None
        else profile.maximum_actions
    )
    if ceiling < 1:
        raise ValueError("maximum action budget must be positive")
    minimum = (
        min_actions
        if min_actions is not None
        else min(profile.minimum_actions, ceiling)
    )
    target = (
        target_actions
        if target_actions is not None
        else min(profile.target_actions, ceiling)
    )
    revisions = (
        revision_budget
        if revision_budget is not None
        else min(profile.revision_actions, ceiling)
    )
    if review_budget < 1:
        raise ValueError("review budget must be positive")
    if revisions < 0:
        raise ValueError("revision action budget cannot be negative")
    if minimum < 0:
        raise ValueError("minimum actions cannot be negative")
    if not minimum <= target <= ceiling:
        raise ValueError(
            "action budgets must satisfy minimum <= target <= maximum"
        )
    if revisions > ceiling:
        raise ValueError("revision action budget cannot exceed maximum actions")
    return BudgetPolicy(
        detail_level,
        minimum,
        target,
        ceiling,
        revisions,
        review_budget,
        profile.required_passes,
        profile.reference_minimum,
    )


def allocate_pass_actions(
    action_count: int,
    passes: tuple[str, ...] = DETAIL_PASSES,
) -> dict[str, int]:
    """Allocate purposeful actions across an ordered coarse-to-fine workflow."""
    if action_count < 1:
        return {name: 0 for name in passes}
    weights = {
        "composition": 0.10,
        "construction": 0.18,
        "form": 0.18,
        "materials": 0.15,
        "lighting": 0.14,
        "texture": 0.15,
        "focal_finish": 0.10,
    }
    raw = {name: action_count * weights.get(name, 1 / len(passes)) for name in passes}
    allocated = {name: int(value) for name, value in raw.items()}
    remaining = action_count - sum(allocated.values())
    order = sorted(
        passes,
        key=lambda name: (raw[name] - allocated[name], -passes.index(name)),
        reverse=True,
    )
    for name in order[:remaining]:
        allocated[name] += 1
    return allocated
