"""Combine metric results into a Scorecard using the spec."""
from __future__ import annotations

from typing import Optional

from .deterministic import run_deterministic
from .normalize import gate_passes, normalize, pick_norm
from .spec import Spec, load_spec
from .standard import build_standard
from .types import DimensionScore, JobAd, MetricResult, Scorecard, ScoringContext


def build_scorecard(raws: list[MetricResult], ctx: ScoringContext, spec: Optional[Spec] = None) -> Scorecard:
    """Missing metrics are recorded as 'skipped' and excluded from the composite."""
    spec = spec or load_spec()
    by_id = {r.id: r for r in raws}
    ctx_d = ctx.model_dump()
    metrics: list[MetricResult] = []
    gate_failures: list[str] = []
    dim_acc: dict[str, list[float]] = {}

    for m in spec.metrics:
        r = by_id.get(m.id)
        base = MetricResult(id=m.id, dimension=m.dimension, grader=m.grader, status=r.status if r else "skipped",
                            raw=r.raw if r else None, pass_=r.pass_ if r else None, evidence=r.evidence if r else [], reasoning=r.reasoning if r else None)
        if m.jurisdictions and base.status == "ok" and not any(ctx.jurisdiction == j or ctx.jurisdiction.startswith(j + "-") for j in m.jurisdictions):
            base.status = "not_applicable"
            base.reasoning = f"not in jurisdictions {','.join(m.jurisdictions)}"
        if base.status == "ok" and base.raw is not None:
            norm = pick_norm(m, ctx.channel)
            base.normalized = normalize(base.raw, norm, m.type)
            if m.type == "pass_fail":
                base.pass_ = base.raw >= 1
            if spec.is_gate(m, ctx_d):
                passes = gate_passes(base.raw, m.gate) if m.gate else base.raw >= 1
                # a gate with its own clause and no band: pass/fail is the only meaningful normalisation (ratios keep their value)
                if m.gate and norm is None and m.type != "ratio":
                    base.normalized = 1.0 if passes else 0.0
                if not passes:
                    base.gate_failed = True
                    gate_failures.append(m.id)
            if not spec.dimensions[m.dimension].gate:
                dim_acc.setdefault(m.dimension, []).append(base.normalized)
        metrics.append(base)

    dimensions: dict[str, DimensionScore] = {}
    weight_sum = 0.0
    weighted = 0.0
    for d, cfg in spec.dimensions.items():
        vals = dim_acc.get(d, [])
        if not vals:
            dimensions[d] = DimensionScore(score=0.0, n=0)
            continue
        score = sum(vals) / len(vals)
        dimensions[d] = DimensionScore(score=score, n=len(vals))
        weight_sum += cfg.weight
        weighted += cfg.weight * score
    composite = round((weighted / weight_sum) * 1000) / 10 if weight_sum > 0 else 0.0
    standard = build_standard(metrics, gate_failures, composite, spec)
    return Scorecard(spec_version=spec.version, metrics=metrics, composite=composite, dimensions=dimensions, standard=standard,
                     gates_passed=not gate_failures, gate_failures=gate_failures, verdict=standard.level)


def score_deterministic(ad: JobAd, ctx: ScoringContext, spec: Optional[Spec] = None) -> Scorecard:
    """No network. Judge metrics appear as 'skipped'."""
    return build_scorecard(run_deterministic(ad, ctx), ctx, spec)


def score(ad: JobAd, ctx: ScoringContext, *, client=None, judge_model: Optional[str] = None, spec: Optional[Spec] = None):
    """Full scorecard: deterministic + judge. Returns (scorecard, JudgeRun)."""
    from .judge.run import run_judge  # local import keeps the deterministic path free of SDK imports

    det = run_deterministic(ad, ctx)
    judge = run_judge(ad, ctx, client=client, model=judge_model)
    return build_scorecard([*det, *judge.results], ctx, spec), judge
