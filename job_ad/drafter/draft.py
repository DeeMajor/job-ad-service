"""Phase 1 baseline: brief → structured ad on claude-opus-5, no retrieval, no revision loop; then the scorer."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

import anthropic

from ..metrics.judge.run import JudgeRun
from ..metrics.scorecard import score
from ..metrics.types import JobAd, Scorecard
from ..schema import JobAdOut, from_llm_output
from ..metrics.types import Source
from .brief import HiringBrief, render_brief, scoring_context_for
from .enrich import Enrichment, enrich, render_sources
from .prompts import get_prompt, render_drafter_input

DEFAULT_DRAFTER_MODEL = "claude-opus-5"


@dataclass
class DraftResult:
    ad: JobAd
    model: str
    usage: Any
    latency_s: float
    prompt_version: str
    brief_text: str
    scorecard: Optional[Scorecard] = None
    judge: Optional[JudgeRun] = None
    enrichment: Optional[Enrichment] = None
    sources: list[Source] = field(default_factory=list)


def draft(brief: HiringBrief, *, client: Optional[anthropic.Anthropic] = None, model: Optional[str] = None, effort: str = "medium",
          do_score: bool = True, judge_model: Optional[str] = None, prompt_version: Optional[str] = None,
          do_enrich: bool = False, max_searches: int = 3) -> DraftResult:
    client = client or anthropic.Anthropic()
    model = model or DEFAULT_DRAFTER_MODEL
    enrichment = enrich(brief, client=client, max_searches=max_searches) if do_enrich else None
    sources = enrichment.sources if enrichment else []
    version, system = get_prompt(prompt_version or ("0.2.3" if sources else None))  # 0.2.3 = default + sources rule
    brief_text = render_brief(brief)
    t0 = time.time()
    res = client.messages.parse(
        model=model, max_tokens=8000,
        thinking={"type": "adaptive"}, output_config={"effort": effort}, output_format=JobAdOut,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": render_drafter_input(brief_text, render_sources(sources))}],
    )
    latency = time.time() - t0
    if res.stop_reason == "refusal":
        raise RuntimeError(f"drafter refused: {getattr(res.stop_details, 'explanation', '')}")
    if res.parsed_output is None:
        raise RuntimeError("drafter output failed to parse")
    ad = from_llm_output(res.parsed_output)
    out = DraftResult(ad=ad, model=res.model, usage=res.usage, latency_s=latency, prompt_version=version, brief_text=brief_text, enrichment=enrichment, sources=sources)
    if do_score:
        ctx = scoring_context_for(brief, brief_text)
        ctx.sources = [*(ctx.sources or []), *sources]  # grounding is judged against brief + web sources
        sc, judge = score(ad, ctx, client=client, judge_model=judge_model)
        out.scorecard, out.judge = sc, judge
    return out
