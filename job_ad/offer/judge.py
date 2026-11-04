"""Judge for the offer model path: explanation faithfulness and invented terms. Model ≠ the drafting model."""
from __future__ import annotations

from typing import Literal, Optional

import anthropic
from pydantic import BaseModel, Field

from ..costs import usage_cost_usd
from .draft import OfferDraft

OFFER_JUDGE_PROMPT_VERSION = "0.1.0"

OFFER_JUDGE_SYSTEM = """You audit employment paperwork written by another system. You receive the SOURCE (brief, terms, contract clauses) and the OUTPUT (an offer letter and a plain-language explanation per clause).

1. For each explanation: is it faithful to its clause? faithful = states nothing the clause does not, omits no condition or figure the clause has, and does not soften or harden an obligation. If not faithful, quote the offending phrase and say what it adds or drops.
2. For the offer letter: list every factual claim (a figure, date, place, duty, benefit, condition, promise, description of the company or the employee) and mark each supported if it traces to the SOURCE, else unsupported with the sentence quoted. Rewording is fine; new substance is not. Placeholders are not claims.
Output only the structured object."""


class ExplVerdict(BaseModel):
    clause_id: str
    faithful: bool
    issue: str = Field(description='"" when faithful; else the phrase and what it adds/drops')


class Claim(BaseModel):
    claim: str
    sentence: str
    supported: bool


class OfferJudgeOut(BaseModel):
    explanations: list[ExplVerdict]
    letter_claims: list[Claim]


class OfferJudgeResult(BaseModel):
    model: str
    faithful: int
    explanations_total: int
    unsupported: list[Claim]
    claims_total: int
    usage: dict[str, int]
    cost_usd: float


def judge_offer(source_text: str, d: OfferDraft, *, client: Optional[anthropic.Anthropic] = None, model: str = "claude-opus-5") -> OfferJudgeResult:
    client = client or anthropic.Anthropic()
    out_text = "# OUTPUT — OFFER LETTER\n" + d.offer_letter.markdown + "\n\n# OUTPUT — EXPLANATIONS\n" + "\n".join(f"[{e.id}] {e.explanation}" for e in d.plain_language if e.explanation)
    res = client.messages.parse(model=model, max_tokens=6000, thinking={"type": "disabled"}, output_format=OfferJudgeOut,
                                system=[{"type": "text", "text": OFFER_JUDGE_SYSTEM, "cache_control": {"type": "ephemeral"}}],
                                messages=[{"role": "user", "content": "# SOURCE\n" + source_text + "\n\n" + out_text}])
    if res.parsed_output is None:
        raise RuntimeError("offer judge failed to parse")
    o: OfferJudgeOut = res.parsed_output
    u = res.usage.model_dump(); usage = {k: int(u.get(k) or 0) for k in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")}
    return OfferJudgeResult(model=model, faithful=sum(e.faithful for e in o.explanations), explanations_total=len(o.explanations), unsupported=[c for c in o.letter_claims if not c.supported],
                            claims_total=len(o.letter_claims), usage=usage, cost_usd=round(usage_cost_usd(model, usage), 4))
