"""Candidate judge: one structured Sonnet call per candidate — requirement evidence (met / unclear / unmet, with a quoted span)
and rubric grading of free-text / code test items. Sees only redacted text. Never the model under test for anything else here."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Optional, Protocol

import anthropic
from pydantic import BaseModel, Field

from .contract import AssessmentItem

JUDGE_PROMPT_VERSION = "0.1.0"  # default; 0.1.1 under test (EXP-302)
DEFAULT_JUDGE_MODEL = "claude-sonnet-5"

JUDGE_SYSTEM_0_1_0 = """You are a blind, evidence-only screening assistant for a South African recruiter. You receive a candidate's application text (form answers, CV text, cover note — identifiers removed) and (a) a list of job requirements, (b) zero or more test items each with the candidate's answer and a grading rubric.

For every requirement, decide exactly one status:
- met: the application STATES the requirement is satisfied. Quote the exact span (verbatim, under 25 words) in `evidence` and name its `source`.
- unclear: the text suggests it but does not state it (related role, adjacent tool, years not given, qualification level unnamed). Quote the closest span; explain the gap in `note` in one sentence. "Likely has" is unclear, never met.
- unmet: the text explicitly says it is not satisfied (e.g. "no licence", "0 years"), or the requirement is a concrete item the text would normally list (licence, registration, named qualification, named system) and it is absent anywhere. Evidence "" and a one-sentence note.
Rules: never infer years of experience from job titles or dates you did not see stated; do not reward generic enthusiasm; do not use anything about who the person is (any demographic detail that survived redaction is to be ignored and never mentioned); judge only against the requirement text as written. Return the requirements in the order given, same text.

For every test item, grade `points` from 0 to max_points against the rubric only (halves allowed). Quote the part of the answer that earned or lost marks in `evidence`; one sentence of `reasoning`. Do not reward length or tone. If the answer is empty, 0.

Output only the structured object."""

JUDGE_SYSTEM_0_1_1 = """You are a blind, evidence-only screening assistant for a South African recruiter. You receive a candidate's application text (form answers, CV text, cover note — identifiers removed) and (a) a list of job requirements, (b) zero or more test items each with the candidate's answer and a grading rubric.

For every requirement, decide exactly one status by this procedure:
1. Is there a span that STATES the requirement is satisfied? → met. Quote it verbatim (under 25 words) in `evidence`, name its `source`.
2. Else, does the text EXPLICITLY say it is not satisfied ("no licence", "0 years", "not registered")? → unmet, evidence "", one-sentence note.
3. Else, is the requirement a CONCRETE, NORMALLY-LISTED item — a licence, a professional registration, a named qualification or certificate, a named system or tool, a stated number of years — and it appears nowhere? → unmet, evidence "", note "not listed".
4. Otherwise → unclear. This covers every soft skill, capability or attribute ("commercial acumen", "stakeholder management", "leadership") that is merely absent, and every related-but-not-stated hint. Quote the closest span if any, else "". One-sentence note.
Absence of a soft skill is never unmet. "Likely has" is unclear, never met. Never infer years of experience from job titles or dates you did not see stated. Do not reward generic enthusiasm. Ignore and never mention anything about who the person is; judge only against the requirement text as written. Return the requirements in the order given, same text.

For every test item, grade `points` from 0 to max_points against the rubric only. Use whole numbers unless the rubric itself names half marks. Award a point only for a rubric element the answer actually contains; an answer that contains none of them scores 0 even if it is sensible. Quote the part of the answer that earned or lost marks in `evidence`; one sentence of `reasoning`. Do not reward length or tone. If the answer is empty, 0.

Output only the structured object."""

PROMPTS = {"0.1.0": JUDGE_SYSTEM_0_1_0, "0.1.1": JUDGE_SYSTEM_0_1_1}
JUDGE_SYSTEM = PROMPTS[JUDGE_PROMPT_VERSION]


class ReqJudgement(BaseModel):
    requirement: str = Field(description="the requirement text exactly as given")
    status: Literal["met", "unclear", "unmet"]
    evidence: str = Field(description='verbatim quote from the application, or "" when nothing relevant appears')
    source: Literal["answers", "cv_text", "cover_note", "none"]
    note: str = Field(description='one sentence on the gap for unclear/unmet; "" for met')


class ItemJudgement(BaseModel):
    item_id: str
    points: float
    evidence: str
    reasoning: str


class CandidateJudgeOut(BaseModel):
    requirements: list[ReqJudgement]
    items: list[ItemJudgement]


@dataclass
class JudgeInput:
    answers: list[tuple[str, str]]          # (question, redacted answer)
    cv_text: str                            # redacted
    cover_note: str                         # redacted
    requirements: list[str]
    items: list[AssessmentItem]


@dataclass
class JudgeResult:
    out: CandidateJudgeOut
    usage: dict[str, int] = field(default_factory=dict)
    model: str = ""
    latency_s: float = 0.0


class Judge(Protocol):
    def __call__(self, inp: JudgeInput) -> JudgeResult: ...


def render_judge_input(inp: JudgeInput) -> str:
    L = ["# APPLICATION"]
    if inp.answers:
        L.append("## Form answers (source: answers)")
        L += [f"Q: {q}\nA: {a}" for q, a in inp.answers]
    if inp.cv_text.strip():
        L += ["## CV text (source: cv_text)", inp.cv_text.strip()]
    if inp.cover_note.strip():
        L += ["## Cover note (source: cover_note)", inp.cover_note.strip()]
    L.append("\n# REQUIREMENTS")
    L += [f"{i+1}. {r}" for i, r in enumerate(inp.requirements)] or ["(none)"]
    L.append("\n# TEST ITEMS TO GRADE")
    if inp.items:
        for it in inp.items:
            L.append(f"item_id: {it.item_id} | skill: {it.skill} | type: {it.type} | max_points: {it.max_points:g}\nRUBRIC: {it.rubric}\nANSWER: {it.answer}")
    else:
        L.append("(none)")
    return "\n".join(L)


def make_claude_judge(client: Optional[anthropic.Anthropic] = None, model: str = DEFAULT_JUDGE_MODEL, effort: str = "medium", prompt_version: str = JUDGE_PROMPT_VERSION) -> Judge:
    client = client or anthropic.Anthropic()
    system = PROMPTS[prompt_version]

    def run(inp: JudgeInput) -> JudgeResult:
        if not inp.requirements and not inp.items:
            return JudgeResult(out=CandidateJudgeOut(requirements=[], items=[]), model=model)
        user = render_judge_input(inp)

        def call():
            return client.messages.parse(model=model, max_tokens=6000, thinking={"type": "adaptive"}, output_config={"effort": effort},
                                         output_format=CandidateJudgeOut,
                                         system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                                         messages=[{"role": "user", "content": user}])

        t0 = time.time()
        try:
            res = call()
        except Exception as e:  # one retry on malformed structured output
            if "parse" in str(e).lower() or "json" in str(e).lower():
                res = call()
            else:
                raise
        if res.stop_reason == "refusal":
            raise RuntimeError(f"judge refused: {getattr(res.stop_details, 'explanation', '')}")
        out = res.parsed_output
        if out is None:
            raise RuntimeError("judge output failed to parse")
        u = res.usage.model_dump()
        usage = {k: int(u.get(k) or 0) for k in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")}
        return JudgeResult(out=out, usage=usage, model=model, latency_s=time.time() - t0)

    return run
