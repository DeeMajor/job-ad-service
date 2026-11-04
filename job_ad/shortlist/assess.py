"""Deterministic scoring of an AssessmentResult. Items with points are taken as graded; items with answer+rubric need the judge
(points supplied by the caller via `judged`); anything else is unanswered (0). Time is never scored."""
from __future__ import annotations

from dataclasses import dataclass, field

from .contract import AssessmentItem, AssessmentResult


@dataclass
class ItemScore:
    item_id: str
    skill: str
    points: float
    max_points: float
    mode: str  # graded | judged | unanswered | ungraded
    evidence: str = ""


@dataclass
class TestScore:
    score: float            # points / max over counted items (ungraded items excluded from both)
    points: float
    max: float
    by_skill: dict[str, float]
    items: list[ItemScore] = field(default_factory=list)
    judged_items: int = 0
    ungraded: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def judged_items(a: AssessmentResult) -> list[AssessmentItem]:
    return [i for i in a.items if i.mode == "judged"]


def score_assessment(a: AssessmentResult, judged: dict[str, tuple[float, str]] | None = None) -> TestScore:
    """`judged` maps item_id → (points, evidence) for judged items; missing judged items are 'ungraded' and left out of the denominator."""
    judged = judged or {}
    items: list[ItemScore] = []
    for it in a.items:
        m = it.mode
        if m == "graded":
            items.append(ItemScore(it.item_id, it.skill, float(it.points), it.max_points, "graded"))
        elif m == "judged":
            if it.item_id in judged:
                p, ev = judged[it.item_id]
                items.append(ItemScore(it.item_id, it.skill, max(0.0, min(it.max_points, float(p))), it.max_points, "judged", ev))
            else:
                items.append(ItemScore(it.item_id, it.skill, 0.0, it.max_points, "ungraded"))
        else:
            items.append(ItemScore(it.item_id, it.skill, 0.0, it.max_points, "unanswered"))
    counted = [i for i in items if i.mode != "ungraded"]
    pts = sum(i.points for i in counted)
    mx = sum(i.max_points for i in counted)
    by_skill: dict[str, float] = {}
    for skill in sorted({i.skill for i in counted}):
        s_items = [i for i in counted if i.skill == skill]
        smax = sum(i.max_points for i in s_items)
        by_skill[skill] = sum(i.points for i in s_items) / smax if smax else 0.0
    notes: list[str] = []
    declared_max = a.max_points
    if declared_max is not None and abs(declared_max - sum(i.max_points for i in a.items)) > 1e-6:
        notes.append(f"declared max_points {declared_max:g} differs from the sum of item max_points {sum(i.max_points for i in a.items):g}; the sum is used")
    return TestScore(score=pts / mx if mx else 0.0, points=pts, max=mx, by_skill=by_skill, items=items,
                     judged_items=sum(1 for i in items if i.mode == "judged"), ungraded=[i.item_id for i in items if i.mode == "ungraded"], notes=notes)
