"""Brief completeness: which scorecard metrics a brief can and cannot satisfy, before any model call.

A brief with only the required fields is valid, but the drafter will not invent facts, so every metric that depends on a
fact the brief lacks will score 0 (or block publishing). This module makes that visible: it maps metrics to the brief fields
that feed them, estimates the composite ceiling, and ranks the fields to add by how much they would lift the score.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from ..metrics.spec import Spec, load_spec
from .brief import HiringBrief

# metric id -> (brief fields that feed it, human hint). Order inside a tuple = preferred fix first.
FEEDS: dict[str, tuple[tuple[str, ...], str]] = {
    "structure.minimum_content": (("responsibilities", "must_have"), "At least one responsibility and one requirement, or the ad is not ready to publish."),
    "structure.sections_present": (("company.about", "purpose", "responsibilities", "must_have", "nice_to_have", "pay", "location", "process.steps"), "Each missing section lowers this."),
    "specific.responsibility_concreteness": (("responsibilities", "success_measures", "tools"), "Concrete duties: what, for whom, how much, measured how."),
    "specific.must_have_count": (("must_have",), "Three to six must-haves."),
    "specific.nice_to_have_split": (("nice_to_have",), "Separate nice-to-haves from must-haves."),
    "specific.requirement_traceability": (("must_have",), "Add a justification to each specific requirement: which duty needs it."),
    "pay.range_present": (("pay",), "A salary or range. The strongest apply-rate driver in the evidence."),
    "pay.range_width": (("pay",), "Keep the range within 30% of the minimum."),
    "pay.context_present": (("pay.basis",), "What decides placement in the range."),
    "evp.why_this_role": (("purpose", "success_measures", "responsibilities"), "What the person will own, build, learn or grow into."),
    "evp.benefits_specific": (("benefits",), "Named benefits with amounts or days, not 'competitive'."),
    "evp.team_context": (("team.reports_to", "team.size", "team.notes"), "Who they report to, or the team size."),
    "evp.work_mode_clarity": (("work_mode", "work_mode_detail"), "Remote, hybrid or on-site; office days if hybrid."),
    "process.steps_and_timeline": (("process.steps", "process.closing_date"), "Interview steps and a response or closing date."),
    "process.contact_or_link": (("process.contact",), "How to apply, unless the board has its own Apply button (hosted_apply)."),
    "compliance.popia_notice": (("statements.popia",), "Your POPIA / personal-information notice."),
    "compliance.ee_statement": (("statements.ee",), "Your Employment Equity statement; a hard gate when designated_employer is true."),
    "inclusive.accessibility_statement": (("statements.accessibility",), "How to request accommodation during the process."),
    "seo.key_terms_early": (("location",), "Location near the top helps search."),
}
# brief field -> number of metrics it unlocks is derived from FEEDS; weights come from the spec's dimensions.


class FieldSuggestion(BaseModel):
    field: str
    unlocks: list[str] = Field(description="metric ids this field feeds")
    estimated_lift: float = Field(description="approximate composite points if the metrics it feeds reached full score")
    hint: str


class Completeness(BaseModel):
    valid: bool = True
    would_be_not_ready: bool = Field(description="True if the draft would come back 'not_ready' with must-fix reasons (no duties or requirements, or a designated employer without an EE statement)")
    not_ready_reasons: list[str]
    unattainable_metrics: list[str] = Field(description="metrics that must score 0 because the brief lacks their facts")
    attainable_metrics: int
    total_scored_metrics: int
    estimated_ceiling: float = Field(description="approximate maximum composite this brief can reach (0–100)")
    suggestions: list[FieldSuggestion] = Field(description="fields to add, highest estimated lift first")


def _present(b: HiringBrief, path: str) -> bool:
    cur: object = b
    for part in path.split("."):
        if cur is None:
            return False
        cur = getattr(cur, part, None)
    if cur is None:
        return False
    if isinstance(cur, (list, str)):
        return len(cur) > 0
    if path == "pay":
        return bool(cur and (getattr(cur, "min", None) or getattr(cur, "max", None)))
    return True


def check(brief: HiringBrief, spec: Optional[Spec] = None) -> Completeness:
    spec = spec or load_spec()
    scored = [m for m in spec.metrics if not spec.dimensions[m.dimension].gate and m.id != "seo.title_matches_taxonomy"]
    # which metrics cannot be satisfied: every feeding field absent (and not excused by context)
    unattainable: list[str] = []
    for m in scored:
        feeds = FEEDS.get(m.id)
        if not feeds:
            continue
        fields, _ = feeds
        if m.id == "process.contact_or_link" and brief.hosted_apply:
            continue
        if m.id == "compliance.ee_statement" and brief.designated_employer is False:
            continue
        if m.id == "pay.range_width" and not _present(brief, "pay"):
            continue  # not_applicable without pay, excluded from the composite rather than scored 0
        if not any(_present(brief, f) for f in fields):
            unattainable.append(m.id)
    blocking = []
    if not brief.responsibilities:  # unreachable for a validated v0.3 brief; kept for callers that build briefs by other means
        blocking.append("no responsibilities")
    if not brief.must_have and not brief.nice_to_have:
        blocking.append("no requirements")
    if brief.designated_employer is True and not (brief.statements and brief.statements.ee):
        blocking.append("designated employer without an Employment Equity statement")

    # ceiling: dimension means with unattainable metrics at 0, others at 1, weighted as the spec does
    per_dim: dict[str, list[float]] = {}
    for m in scored:
        if m.id == "pay.range_width" and not _present(brief, "pay"):
            continue
        per_dim.setdefault(m.dimension, []).append(0.0 if m.id in unattainable else 1.0)
    wsum = sum(spec.dimensions[d].weight for d in per_dim)
    ceiling = round(sum(spec.dimensions[d].weight * (sum(v) / len(v)) for d, v in per_dim.items()) / wsum * 100, 1) if wsum else 0.0

    # suggestions: per absent field, the composite lift if its metrics went 0 -> 1
    lifts: dict[str, FieldSuggestion] = {}
    for mid in unattainable:
        fields, hint = FEEDS[mid]
        m = spec.metric(mid); n_dim = len(per_dim[m.dimension])
        lift = spec.dimensions[m.dimension].weight / wsum * 100 / n_dim
        for f in fields:
            if _present(brief, f):
                continue
            s = lifts.setdefault(f, FieldSuggestion(field=f, unlocks=[], estimated_lift=0.0, hint=hint))
            if mid not in s.unlocks:
                s.unlocks.append(mid); s.estimated_lift = round(s.estimated_lift + lift, 1)
            break  # credit the preferred field only, so lifts are not double-counted across alternatives
    suggestions = sorted(lifts.values(), key=lambda s: -s.estimated_lift)
    return Completeness(would_be_not_ready=bool(blocking), not_ready_reasons=blocking, unattainable_metrics=unattainable, attainable_metrics=len([m for m in scored if m.id not in unattainable]),
                        total_scored_metrics=len(scored), estimated_ceiling=0.0 if blocking else ceiling, suggestions=suggestions)
