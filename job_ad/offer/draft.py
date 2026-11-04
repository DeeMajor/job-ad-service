"""Assemble an OfferDraft from the clause library (template mode, no model) and the rule engine. Phase 1 adds the model path."""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

from ..metrics.text import flesch_kincaid_grade
from .clauses import CLAUSES_VERSION, PLACEHOLDERS, Clause, build_contract_clauses, build_offer_clauses, render_markdown
from .rules import RULES_VERSION, Compliance, Consistency, Finding, check
from .terms import OfferRequest

DISCLAIMER = (f"Template generated from the agreed terms and checked against the BCEA, NMW Act and LRA rules in compliance-rules.yaml v{RULES_VERSION}. "
              "Not legal advice; the clause library must be reviewed by a labour practitioner before use, and figures marked 'verify' confirmed against the Government Gazette.")
READABILITY_TARGET = 10.0


class ClauseOut(BaseModel):
    id: str
    heading: str
    text: str
    particular: Optional[str] = None
    grade: float = Field(description="Flesch-Kincaid grade of the clause text")


class Document(BaseModel):
    clauses: list[ClauseOut]
    markdown: str
    placeholders: list[str] = Field(default_factory=list)


class Explanation(BaseModel):
    id: str
    explanation: str
    grade: float


class OfferMeta(BaseModel):
    mode: str = "template"
    model: Optional[str] = None
    prompt_version: Optional[str] = None
    clauses_version: str = CLAUSES_VERSION
    rules_version: str = RULES_VERSION
    usage: dict[str, int] = Field(default_factory=dict)
    cost_usd: float = 0.0
    latency_s: float


class OfferDraft(BaseModel):
    drafted_at: datetime
    offer_letter: Document
    contract: Document
    plain_language: list[Explanation]
    compliance: Compliance
    consistency: Consistency
    disclaimer: str = DISCLAIMER
    meta: OfferMeta


def _doc(clauses: list[Clause], title: str, placeholders: bool) -> Document:
    outs = [ClauseOut(id=c.id, heading=c.heading, text=c.text, particular=c.particular, grade=round(flesch_kincaid_grade(c.text), 1)) for c in clauses]
    return Document(clauses=outs, markdown=render_markdown(title, clauses), placeholders=PLACEHOLDERS if placeholders else [])


def draft_template(req: OfferRequest) -> OfferDraft:
    t0 = time.time()
    comp, cons = check(req)
    contract = build_contract_clauses(req, comp.checked_against.earnings_threshold_applies)
    offer = build_offer_clauses(req)
    expl = [Explanation(id=c.id, explanation=c.explanation, grade=round(flesch_kincaid_grade(c.explanation), 1)) for c in contract if c.explanation]
    hard = [c.id for c in contract if flesch_kincaid_grade(c.text) > READABILITY_TARGET]
    if hard:
        comp.findings.append(Finding(severity="could_improve", rule="plain_language.clause_readability", message=f"Clause text above grade {READABILITY_TARGET:g}: {', '.join(hard)}; the plain-language explanations cover them.", evidence="Flesch-Kincaid; BCEA s29(3)"))
    missing_expl = [c.id for c in contract if not c.explanation]
    if missing_expl:
        comp.findings.append(Finding(severity="should_fix", rule="plain_language.explanation_present", message=f"No plain-language explanation for: {', '.join(missing_expl)}.", evidence="BCEA s29(3)"))
        if comp.level == "compliant":
            comp.level = "review"
    return OfferDraft(drafted_at=datetime.now(timezone.utc), offer_letter=_doc(offer, f"Offer of employment — {req.brief.title}", False),
                      contract=_doc(contract, f"Contract of employment — {req.brief.title}", True), plain_language=expl, compliance=comp, consistency=cons,
                      meta=OfferMeta(latency_s=round(time.time() - t0, 3)))
