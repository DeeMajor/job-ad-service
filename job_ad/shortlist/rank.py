"""Rank a candidate pool: deterministic where possible, judged where text must be read, explained everywhere.

Per candidate: exclude if unusable → redact free text → decide knockouts and fact-linked requirements from `declared` →
judge the rest (requirements + rubric items) on redacted text → score components → tier → reasons. Then sort with explicit
tiebreakers so the same input always yields the same order. Nobody is dropped silently."""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from ..costs import usage_cost_usd
from ..drafter.brief import HiringBrief, Requirement
from .assess import TestScore, judged_items, score_assessment
from .contract import (Candidate, Components, Excluded, FactLink, FairnessCheck, Knockout, RankMeta, RankRequest, RankResult, RankedCandidate,
                       Reason, RequirementComponent, SkillsTestComponent, Tier)
from .judge import JUDGE_PROMPT_VERSION, Judge, JudgeInput, ReqJudgement
from .redact import redact, residual_scan
from .spec import load_ranking_spec


@dataclass
class ReqOutcome:
    text: str
    status: str                 # met | unclear | unmet
    weight: float
    evidence: str = ""
    source: str = "none"
    note: Optional[str] = None
    inherent: bool = False      # explicit knockout


def _fact_matches(c: Candidate, key: str, required) -> Optional[bool]:
    if key not in c.declared:
        return None
    v = c.declared[key]
    if isinstance(required, bool) and isinstance(v, str):
        return v.strip().lower() in ("yes", "true", "y", "1") if required else v.strip().lower() in ("no", "false", "n", "0")
    return v == required


def _decide_from_facts(c: Candidate, text: str, key: Optional[str], required, weight: float, inherent: bool) -> Optional[ReqOutcome]:
    if not key:
        return None
    m = _fact_matches(c, key, required)
    if m is None:
        return ReqOutcome(text, "unclear", weight, "", "declared", f"form fact '{key}' not provided", inherent)
    return ReqOutcome(text, "met" if m else "unmet", weight, f"{key} = {c.declared[key]!r}", "declared", None if m else f"declared {key} = {c.declared[key]!r}, required {required!r}", inherent)


def _component(outs: list[ReqOutcome], weight: float, values) -> RequirementComponent:
    tot = sum(o.weight for o in outs)
    score = sum(o.weight * getattr(values, o.status) for o in outs) / tot if tot else 0.0
    return RequirementComponent(score=score, weight=weight, matched=sum(o.status == "met" for o in outs), unclear=sum(o.status == "unclear" for o in outs),
                                unmet=sum(o.status == "unmet" for o in outs), of=len(outs))


def _reasons_for(outs: list[ReqOutcome], prefix: str) -> list[Reason]:
    order = {"unmet": 0, "met": 1, "unclear": 2}
    R = []
    for o in sorted(outs, key=lambda o: (order[o.status], -o.weight)):
        kind = f"{prefix}_{o.status}"
        R.append(Reason(kind=kind, requirement=o.text, evidence=f'"{o.evidence}"' if o.evidence and o.source != "declared" else o.evidence, source=o.source, note=o.note))
    return R


def _tier(score: float, knocked: bool, tiers) -> Tier:
    if knocked:
        return "does_not_meet_inherent_requirement"
    return "strong" if score >= tiers.strong else "possible" if score >= tiers.possible else "weak"


def rank_pool(req: RankRequest, judge: Optional[Judge] = None) -> RankResult:
    spec = load_ranking_spec()
    t0 = time.time()
    brief: HiringBrief = req.job.brief
    w = req.job.weights or spec.weights
    facts = {f.requirement.strip().lower(): f for f in req.job.facts}
    values = spec.requirement_status_values
    use_judge = req.options.judge and judge is not None

    ranked: list[tuple[RankedCandidate, tuple]] = []
    excluded: list[Excluded] = []
    usage: dict[str, int] = {}
    judged_candidates = judged_items_total = residual = 0
    judge_model: Optional[str] = None

    for c in req.candidates:
        if c.assessment is None and req.options.require_assessment:
            excluded.append(Excluded(candidate_id=c.candidate_id, reason="no assessment result; set options.require_assessment=false to rank on the application alone")); continue
        if c.assessment is None and c.application.is_empty() and not c.declared:
            excluded.append(Excluded(candidate_id=c.candidate_id, reason="no application content, declared facts or assessment")); continue

        # 1. redact everything a model could see
        ans = [(a.question, redact(a.answer)) for a in c.application.answers]
        cv, note = redact(c.application.cv_text), redact(c.application.cover_note)
        redactions = sum(r.count for _, r in ans) + cv.count + note.count
        residual += residual_scan(cv.text) + residual_scan(note.text) + sum(residual_scan(r.text) for _, r in ans)

        # 2. deterministic decisions: knockouts, fact-linked requirements
        pending: list[tuple[Requirement, bool, bool]] = []  # (requirement, is_must, inherent)
        outcomes: dict[str, ReqOutcome] = {}
        knock_outs: list[ReqOutcome] = []
        for k in req.job.knockouts:
            o = _decide_from_facts(c, k.text, k.declared_key, k.required_value, spec.requirement_weight.justified, True)
            if o:
                knock_outs.append(o)
            else:
                pending.append((Requirement(text=k.text), True, True))
        for r, is_must in [(r, True) for r in brief.must_have] + [(r, False) for r in brief.nice_to_have]:
            wt = spec.requirement_weight.justified if (is_must and r.justification) else spec.requirement_weight.unjustified
            f: Optional[FactLink] = facts.get(r.text.strip().lower())
            o = _decide_from_facts(c, r.text, f.declared_key, f.required_value, wt, False) if f else None
            if o:
                outcomes[r.text] = o
            else:
                pending.append((r, is_must, False))

        # 3. judge what text must decide
        j_items = judged_items(c.assessment) if c.assessment else []
        judged_pts: dict[str, tuple[float, str]] = {}
        item_reasons: list[Reason] = []
        if pending or j_items:
            if use_judge:
                res = judge(JudgeInput(answers=[(q, r.text) for q, r in ans], cv_text=cv.text, cover_note=note.text, requirements=[p[0].text for p in pending], items=j_items))
                judged_candidates += 1; judged_items_total += len(j_items); judge_model = res.model or judge_model
                for k_, v in res.usage.items():
                    usage[k_] = usage.get(k_, 0) + v
                by_text = {j.requirement.strip().lower(): j for j in res.out.requirements}
                for i, (r, is_must, inherent) in enumerate(pending):
                    j: Optional[ReqJudgement] = by_text.get(r.text.strip().lower()) or (res.out.requirements[i] if i < len(res.out.requirements) else None)
                    wt = spec.requirement_weight.justified if (inherent or (is_must and r.justification)) else spec.requirement_weight.unjustified
                    o = ReqOutcome(r.text, j.status, wt, j.evidence, j.source, j.note or None, inherent) if j else ReqOutcome(r.text, "unclear", wt, "", "none", "judge returned no verdict", inherent)
                    if inherent:
                        knock_outs.append(o)
                    else:
                        outcomes[r.text] = o
                item_map = {ij.item_id: ij for ij in res.out.items}
                for it in j_items:
                    ij = item_map.get(it.item_id)
                    if ij:
                        judged_pts[it.item_id] = (ij.points, ij.evidence)
                        item_reasons.append(Reason(kind="test_item_judged", skill=it.skill, evidence=f'{it.item_id}: {max(0.0, min(it.max_points, ij.points)):g}/{it.max_points:g} — "{ij.evidence}"', source="assessment", note=ij.reasoning))
            else:
                for r, is_must, inherent in pending:
                    wt = spec.requirement_weight.justified if (inherent or (is_must and r.justification)) else spec.requirement_weight.unjustified
                    o = ReqOutcome(r.text, "unclear", wt, "", "none", "not judged (options.judge=false)", inherent)
                    if inherent:
                        knock_outs.append(o)
                    else:
                        outcomes[r.text] = o

        # 4. components
        must_outs = [outcomes[r.text] for r in brief.must_have if r.text in outcomes]
        nice_outs = [outcomes[r.text] for r in brief.nice_to_have if r.text in outcomes]
        comp_req = _component(must_outs, w.requirements, values)
        comp_nice = _component(nice_outs, w.nice_to_have, values) if nice_outs else None
        ts: Optional[TestScore] = score_assessment(c.assessment, judged_pts) if c.assessment else None
        comp_test = SkillsTestComponent(score=ts.score, weight=w.skills_test, points=ts.points, max=ts.max, by_skill=ts.by_skill, judged_items=ts.judged_items,
                                        ungraded_items=ts.ungraded, time_limit_s=c.assessment.time_limit_s, time_used_s=c.assessment.time_used_s, flags=c.assessment.flags) if ts else None
        parts = [(comp_req.score, w.requirements)] + ([(comp_test.score, w.skills_test)] if comp_test else []) + ([(comp_nice.score, w.nice_to_have)] if comp_nice else [])
        wsum = sum(p[1] for p in parts)
        score = round(100 * sum(s * wt for s, wt in parts) / wsum, 1) if wsum else 0.0
        knocked = any(o.status == "unmet" for o in knock_outs)
        tier = _tier(score, knocked, spec.tiers)

        # 5. reasons and human checks
        reasons: list[Reason] = []
        for o in knock_outs:
            if o.status == "unmet":
                reasons.append(Reason(kind="knockout_failed", requirement=o.text, evidence=o.evidence, source=o.source, note=o.note or "inherent requirement not met; listed, not ranked above others"))
            elif o.status == "unclear":
                reasons.append(Reason(kind="knockout_unclear", requirement=o.text, evidence=f'"{o.evidence}"' if o.evidence else "", source=o.source, note=o.note or "inherent requirement not confirmed; recruiter to verify"))
            else:
                reasons.append(Reason(kind="requirement_met", requirement=o.text, evidence=o.evidence if o.source == "declared" else f'"{o.evidence}"', source=o.source, note="inherent requirement confirmed"))
        reasons += _reasons_for(must_outs, "requirement")
        if ts:
            for skill, share in ts.by_skill.items():
                s_items = [i for i in ts.items if i.skill == skill and i.mode != "ungraded"]
                ev = f"{sum(i.points for i in s_items):g}/{sum(i.max_points for i in s_items):g} points"
                if share >= spec.test.strength_at:
                    reasons.append(Reason(kind="test_strength", skill=skill, evidence=ev, source="assessment"))
                elif share < spec.test.gap_below:
                    reasons.append(Reason(kind="test_gap", skill=skill, evidence=ev + "; " + ", ".join(f"{i.item_id} {i.points:g}/{i.max_points:g}" for i in s_items if i.points < i.max_points), source="assessment"))
            reasons += item_reasons
            for iid in ts.ungraded:
                reasons.append(Reason(kind="test_item_ungraded", evidence=iid, source="assessment", note="free-text item not graded (judge off); excluded from the test score"))
            for fl in c.assessment.flags:
                reasons.append(Reason(kind="integrity_flag", evidence=fl, source="assessment", note="reported by the test runner; not scored"))
        else:
            reasons.append(Reason(kind="test_missing", evidence="no assessment result", source="none", note="ranked on the application alone; test weight redistributed"))
        reasons += _reasons_for(nice_outs, "nice_to_have")
        if redactions:
            reasons.append(Reason(kind="redaction", evidence=f"{redactions} identifier(s) removed before evaluation", source="none"))
        checks = [f"inherent requirement unclear: {o.text}" for o in knock_outs if o.status == "unclear"]
        checks += [f"requirement unclear: {o.text}" for o in must_outs if o.status == "unclear"]
        if ts and ts.ungraded:
            checks.append("ungraded test items: " + ", ".join(ts.ungraded))
        if ts and ts.notes:
            checks += ts.notes
        if c.assessment and c.assessment.flags:
            checks.append("integrity flags: " + ", ".join(c.assessment.flags))
        if not ts:
            checks.append("no assessment")

        rc = RankedCandidate(rank=0, candidate_id=c.candidate_id, score=score, tier=tier, components=Components(requirements=comp_req, skills_test=comp_test, nice_to_have=comp_nice),
                             reasons=reasons, needs_human_check=checks, redactions_applied=redactions)
        key = (1 if knocked else 0, -score, -comp_req.score, -(comp_test.score if comp_test else 0), -(comp_nice.score if comp_nice else 0), c.candidate_id)
        ranked.append((rc, key))

    ranked.sort(key=lambda x: x[1])
    shortlist: list[RankedCandidate] = []
    for i, (rc, _) in enumerate(ranked, 1):
        rc.rank = i
        if not req.options.explain_all and i > req.options.top_n:
            rc.reasons = []
        shortlist.append(rc)

    cost = usage_cost_usd(judge_model or req.options.judge_model, usage) if usage else 0.0
    meta = RankMeta(judge_prompt_version=JUDGE_PROMPT_VERSION if judged_candidates else None, pool_size=len(req.candidates), ranked=len(shortlist), judged_candidates=judged_candidates,
                    judged_items=judged_items_total, judge_model=judge_model if judged_candidates else None, weights={"requirements": w.requirements, "skills_test": w.skills_test, "nice_to_have": w.nice_to_have},
                    usage=usage, cost_usd=round(cost, 4), latency_s=round(time.time() - t0, 2),
                    fairness_check=FairnessCheck(ran=True, redaction_clean=residual == 0, residual_patterns=residual))
    return RankResult(ranked_at=datetime.now(timezone.utc), shortlist=shortlist, excluded_from_ranking=excluded, meta=meta)
