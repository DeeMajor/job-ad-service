"""Model path: offer letter + explanations from the model, contract from the clause library. One call."""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Optional

import anthropic
from pydantic import BaseModel

from ..costs import usage_cost_usd
from ..metrics.text import flesch_kincaid_grade
from .clauses import Clause, build_contract_clauses, render_markdown
from .draft import ClauseOut, Document, Explanation, OfferDraft, OfferMeta, PLACEHOLDERS, READABILITY_TARGET, _doc
from .prompts import OFFER_PROMPT_VERSION, OFFER_SYSTEM, OFFER_SYSTEM_LETTER_ONLY, render_offer_input
from .rules import Finding, check
from .terms import OfferRequest

DEFAULT_OFFER_MODEL = "claude-opus-5"  # EXP-401: 0 unsupported claims in 220 vs Sonnet 3 in 161 (2 briefs); pre-registered rule → Opus


class Paragraph(BaseModel):
    heading: str
    text: str


class ExplanationOut(BaseModel):
    clause_id: str
    explanation: str


class OfferOut(BaseModel):
    offer_letter: list[Paragraph]
    explanations: list[ExplanationOut]


class LetterOut(BaseModel):
    offer_letter: list[Paragraph]


def _usage(res) -> dict[str, int]:
    u = res.usage.model_dump()
    return {k: int(u.get(k) or 0) for k in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")}


def draft_with_model(req: OfferRequest, *, client: Optional[anthropic.Anthropic] = None, model: str = DEFAULT_OFFER_MODEL, thinking: bool = False, effort: str = "medium",
                     model_explanations: bool = False) -> OfferDraft:
    """model_explanations=False (default since EXP-401): the model writes the offer letter only; the plain-language explanations come from the
    clause library (faithful by construction, 94% at grade ≤ 10 vs 72–75% for model-written ones)."""
    client = client or anthropic.Anthropic()
    t0 = time.time()
    comp, cons = check(req)
    contract = build_contract_clauses(req, comp.checked_against.earnings_threshold_applies)
    sampling = {"thinking": {"type": "adaptive"}, "output_config": {"effort": effort}} if thinking else {"thinking": {"type": "disabled"}}
    system = OFFER_SYSTEM if model_explanations else OFFER_SYSTEM_LETTER_ONLY
    res = client.messages.parse(model=model, max_tokens=6000, output_format=OfferOut if model_explanations else LetterOut, **sampling,
                                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                                messages=[{"role": "user", "content": render_offer_input(req, contract)}])
    if res.stop_reason == "refusal" or res.parsed_output is None:
        raise RuntimeError("offer model refused or failed to parse")
    out = res.parsed_output
    letter = [Clause(id=f"p{i+1}", heading=p.heading, text=p.text, source="model") for i, p in enumerate(out.offer_letter)]
    by_id = {e.clause_id: e.explanation for e in out.explanations} if model_explanations else {c.id: c.explanation for c in contract}
    expl = [Explanation(id=c.id, explanation=by_id.get(c.id, ""), grade=round(flesch_kincaid_grade(by_id.get(c.id, "")), 1) if by_id.get(c.id) else 0.0) for c in contract]
    missing = [c.id for c in contract if not by_id.get(c.id)]
    if missing:
        comp.findings.append(Finding(severity="should_fix", rule="plain_language.explanation_present", message=f"Model gave no explanation for: {', '.join(missing)}.", evidence="BCEA s29(3)"))
        if comp.level == "compliant":
            comp.level = "review"
    hard = [c.id for c in contract if flesch_kincaid_grade(c.text) > READABILITY_TARGET]
    if hard:
        comp.findings.append(Finding(severity="could_improve", rule="plain_language.clause_readability", message=f"Clause text above grade {READABILITY_TARGET:g}: {', '.join(hard)}; the plain-language explanations cover them.", evidence="Flesch-Kincaid; BCEA s29(3)"))
    usage = _usage(res)
    return OfferDraft(drafted_at=datetime.now(timezone.utc), offer_letter=_doc(letter, f"Offer of employment — {req.brief.title}", False),
                      contract=_doc(contract, f"Contract of employment — {req.brief.title}", True), plain_language=expl, compliance=comp, consistency=cons,
                      meta=OfferMeta(mode="model", model=model, prompt_version=OFFER_PROMPT_VERSION, usage=usage, cost_usd=round(usage_cost_usd(model, usage), 4), latency_s=round(time.time() - t0, 2)))
