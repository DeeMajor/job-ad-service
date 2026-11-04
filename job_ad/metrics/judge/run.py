"""Claude-as-judge: one structured-output call; counts and ratios derived in code from the lists it returns."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Optional

import anthropic

from ..text import render_ad
from ..types import JobAd, MetricResult, ScoringContext
from .prompt import JUDGE_SYSTEM, render_judge_input
from .schema import JudgeOutput

DEFAULT_JUDGE_MODEL = "claude-sonnet-5"  # never the model under test


@dataclass
class JudgeRun:
    results: list[MetricResult]
    parsed: JudgeOutput
    model: str
    usage: Any
    latency_s: float


def _ratio(num: int, den: int) -> float:
    return 1.0 if den <= 0 else min(1.0, num / den)


def run_judge(ad: JobAd | str, ctx: ScoringContext, *, client: Optional[anthropic.Anthropic] = None, model: Optional[str] = None,
              effort: str = "medium") -> JudgeRun:
    client = client or anthropic.Anthropic()
    model = model or DEFAULT_JUDGE_MODEL
    ad_text = ad if isinstance(ad, str) else render_ad(ad)
    user = render_judge_input(ad_text, ctx.sources)

    def call():
        return client.messages.parse(
            model=model,
            max_tokens=8000,
            thinking={"type": "adaptive"},
            output_config={"effort": effort},
            output_format=JudgeOutput,
            system=[{"type": "text", "text": JUDGE_SYSTEM, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
        )

    t0 = time.time()
    try:
        res = call()
    except Exception as e:  # one retry on a malformed structured output (seen ~1 in 600 calls)
        if "parse" in str(e).lower() or "json" in str(e).lower():
            res = call()
        else:
            raise
    latency = time.time() - t0
    if res.stop_reason == "refusal":
        raise RuntimeError(f"judge refused: {getattr(res.stop_details, 'explanation', '')}")
    parsed: JudgeOutput | None = res.parsed_output
    if parsed is None:
        raise RuntimeError("judge output failed to parse")

    results: list[MetricResult] = []

    def pf(id: str, j) -> None:
        results.append(MetricResult(id=id, status="ok", raw=1.0 if j.pass_ else 0.0, pass_=j.pass_, evidence=j.evidence, reasoning=j.reasoning))

    pf("structure.title_matches_content", parsed.title_matches_content)
    r = parsed.responsibilities
    results.append(MetricResult(id="specific.responsibility_concreteness", status="not_applicable" if r.total == 0 else "ok",
                                raw=_ratio(len(r.concrete), r.total), evidence=r.concrete, reasoning=f"{len(r.concrete)}/{r.total} concrete. {r.reasoning}"))
    q = parsed.specific_requirements
    traced = [i for i in q.items if i.supporting_responsibility.strip()]
    results.append(MetricResult(id="specific.requirement_traceability", status="not_applicable" if not q.items else "ok",
                                raw=_ratio(len(traced), len(q.items)), evidence=[f"{i.requirement} ← {i.supporting_responsibility or '(none)'}" for i in q.items],
                                reasoning=f"{len(traced)}/{len(q.items)} specific requirements traceable (generic education and experience bands excluded). {q.reasoning}"))
    pf("pay.context_present", parsed.pay_context_present)
    g = parsed.grounding
    has_sources = bool(ctx.sources)
    results.append(MetricResult(id="honesty.grounding", status="ok" if has_sources else "not_applicable",
                                raw=_ratio(max(0, g.factual_claims_total - len(g.unsupported_claims)), g.factual_claims_total) if has_sources else 1.0,
                                evidence=[f'unsupported: {c.claim} — "{c.sentence}"' for c in g.unsupported_claims],
                                reasoning=f"{len(g.unsupported_claims)}/{g.factual_claims_total} unsupported. {g.reasoning}" if has_sources else "no sources provided; grounding not assessable"))
    px = parsed.proxy_requirements
    results.append(MetricResult(id="inclusive.proxy_requirements", status="ok", raw=float(len(px.items)), evidence=px.items, reasoning=px.reasoning))
    pf("compliance.protected_grounds", parsed.protected_grounds_ok)
    pf("compliance.no_prohibited_requests", parsed.no_prohibited_requests)
    draw = parsed.why_this_role.role_specific_draw.strip()
    results.append(MetricResult(id="evp.why_this_role", status="ok", raw=1.0 if draw else 0.0, pass_=bool(draw), evidence=[draw] if draw else [], reasoning=parsed.why_this_role.reasoning))
    pf("evp.benefits_specific", parsed.evp_benefits_specific)
    tc = parsed.team_context
    team_pass = bool(tc.reports_to.strip()) or any(ch.isdigit() for ch in tc.team_size)
    ev = [x for x in (f"reports to: {tc.reports_to}" if tc.reports_to else "", f"team size: {tc.team_size}" if tc.team_size else "") if x]
    results.append(MetricResult(id="evp.team_context", status="ok", raw=1.0 if team_pass else 0.0, pass_=team_pass, evidence=ev, reasoning=tc.reasoning))
    pf("evp.work_mode_clarity", parsed.evp_work_mode_clarity)
    pf("process.steps_and_timeline", parsed.process_steps_and_timeline)
    return JudgeRun(results=results, parsed=parsed, model=res.model, usage=res.usage, latency_s=latency)
