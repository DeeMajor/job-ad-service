"""Offer drafting prompt. The model writes the OFFER LETTER prose and a PLAIN-LANGUAGE EXPLANATION per contract clause.
It never writes or alters contract clauses: those come from the reviewed clause library."""
from __future__ import annotations

from .clauses import Clause
from .terms import OfferRequest

OFFER_PROMPT_VERSION = "0.1.0"

OFFER_SYSTEM = """You write employment paperwork for a South African employer. You receive (1) the hiring brief, (2) the agreed terms, and (3) the contract clauses exactly as they will be signed.

Produce two things.

A. OFFER LETTER paragraphs: a warm, direct letter offering the job. Use only facts that appear in the brief, the terms or the clauses — every figure, date, place, duty and benefit must trace to them. Do not add benefits, promises, descriptions of the company, or anything about the employee. Keep the placeholders exactly: {{employee.full_name}}, {{date_signed}}. Grade-8 reading level: short sentences, everyday words, active voice. Three to five paragraphs plus a one-line acceptance.

B. PLAIN-LANGUAGE EXPLANATION for every contract clause, keyed by clause_id: say what the clause means for the employee in two or three plain sentences. Add no term that is not in the clause and drop no condition that is. Keep every number. Do not interpret the law beyond what the clause says. If a clause is a signature block, say who signs.

Output only the structured object."""


OFFER_SYSTEM_LETTER_ONLY = OFFER_SYSTEM.split("B. PLAIN-LANGUAGE")[0].replace("Produce two things.\n\nA. OFFER LETTER paragraphs", "Produce the OFFER LETTER paragraphs").rstrip() + "\n\nOutput only the structured object."


def render_offer_input(req: OfferRequest, clauses: list[Clause]) -> str:
    t, b, o = req.terms, req.brief, req.offer
    L = ["# BRIEF", f"Title: {b.title}", f"Company: {b.company.name}", "Duties: " + "; ".join(b.responsibilities)]
    if b.purpose:
        L.append(f"Purpose: {b.purpose}")
    L += ["\n# TERMS", t.model_dump_json(exclude_none=True, indent=None), "\n# OFFER", o.model_dump_json(exclude_none=True, indent=None), "\n# CONTRACT CLAUSES (as signed; do not change)"]
    L += [f"[{c.id}] {c.heading}\n{c.text}" for c in clauses]
    return "\n".join(L)
