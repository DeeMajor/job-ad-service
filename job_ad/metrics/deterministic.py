"""Deterministic and lexicon graders. Pure functions, no network. Each returns a partial MetricResult;
the scorecard layer adds dimension/grader/normalisation from the spec."""
from __future__ import annotations

import json
import re
from pathlib import Path

from .text import bullet_items, count_hits, flesch_kincaid_grade, longest_sentence, prose_paragraphs, render_ad, words
from .types import JobAd, MetricResult, ScoringContext

_LEX = Path(__file__).parent / "lexicons"


def _lex(name: str) -> dict:
    return json.loads((_LEX / name).read_text(encoding="utf-8"))


GENDERED = _lex("gendered.json")
BUZZ: list[str] = _lex("buzzwords.json")["terms"]
EXCL = _lex("exclusionary.json")
EXCL_CONTEXT = [re.compile(p, re.IGNORECASE) for p in EXCL["contextual"]]
GIMMICK: list[str] = _lex("gimmick_titles.json")["terms"]
STOP = {"and", "the", "for", "with", "of", "in", "to", "senior", "junior", "lead", "head", "manager", "officer", "specialist", "assistant", "intern"}
YEARS_THRESHOLD = 8  # seniority-agnostic placeholder until the taxonomy provides a band (Phase 3)

_SECOND = re.compile(r"\b(you|your|yours|you'll|you’ll|you're|you’re|you've|you’ve|yourself)\b", re.IGNORECASE)
_THIRD = re.compile(r"\b(the (?:ideal|successful|right|suitable|preferred) (?:candidate|applicant|person|incumbent)|the candidate|the applicant|the incumbent|the (?:successful|appointed) (?:individual|employee)|he/she|she/he|s/he|him/her|his/her)\b", re.IGNORECASE)
_YEARS = re.compile(r"(\d{1,2})\s*\+?\s*(?:-\s*\d{1,2}\s*)?(?:years?|yrs?)", re.IGNORECASE)
_LEVEL_WORDS = re.compile(r"\((?:grade|band|level|job level|jl|ic|p|l|m)\s*\d{1,2}\)|\b(?:grade|band|job level|jl)\s*\d{1,2}\b", re.IGNORECASE)
_LEVEL_CODES = re.compile(r"\b(?:P|L|M|IC|JL)\d{1,2}\b")
_GENDER_MARK = re.compile(r"\b(m/w/d|m/f/d|f/m/x)\b", re.IGNORECASE)
_CONTACT = re.compile(r"\b(apply (?:here|now|via|at|online|by)|https?://|www\.|@[a-z0-9.-]+\.[a-z]{2,}|send your (?:cv|resume|application)|email your)\b", re.IGNORECASE)
_ACCESS = re.compile(r"\b(accommodat|reasonable adjustment|accessib)", re.IGNORECASE)
_EE = re.compile(r"\b(employment equity|affirmative action|designated groups|EE (?:plan|targets|candidates))\b", re.IGNORECASE)
_POPIA = re.compile(r"\b(POPIA|protection of personal information|personal information will be|privacy (?:notice|policy))\b", re.IGNORECASE)
_PAY_MANDATED_US = re.compile(r"^US-(CO|CA|NY|WA|IL|HI|MD|MN|NJ|VT)$")


def _r2(n: float) -> float:
    return round(n, 2)


def _ok(id: str, raw: float, evidence: list[str] | None = None, reasoning: str | None = None) -> MetricResult:
    return MetricResult(id=id, status="ok", raw=raw, evidence=evidence or [], reasoning=reasoning)


def _pf(id: str, ok: bool, evidence: list[str] | None = None, reasoning: str | None = None) -> MetricResult:
    return MetricResult(id=id, status="ok", raw=1.0 if ok else 0.0, pass_=ok, evidence=evidence or [], reasoning=reasoning)


def _na(id: str, reasoning: str) -> MetricResult:
    return MetricResult(id=id, status="not_applicable", reasoning=reasoning)


def _ni(id: str, reasoning: str) -> MetricResult:
    return MetricResult(id=id, status="not_implemented", reasoning=reasoning)


def run_deterministic(ad: JobAd, ctx: ScoringContext) -> list[MetricResult]:
    text = render_ad(ad)
    content = render_ad(ad, headings=False)  # lexicon and pronoun metrics must not count our own section headings
    body = words(text)
    n_body = len(body)

    def per100(n: float) -> float:
        return (n / n_body) * 100 if n_body else 0.0

    out: list[MetricResult] = []

    # ---- gate: an ad without the basics is unpublishable
    missing: list[str] = []
    if not (ad.title or "").strip():
        missing.append("title")
    if not ad.responsibilities:
        missing.append("responsibilities")
    if not ad.must_have and not ad.nice_to_have:
        missing.append("requirements")
    if n_body < 100:
        missing.append(f"only {n_body} words")
    out.append(_pf("structure.minimum_content", not missing, missing))

    # ---- D1 clarity & structure
    has_pay = bool(ad.pay and (ad.pay.min or ad.pay.max))
    sections = [
        ("title", bool((ad.title or "").strip())),
        ("about", bool(ad.company and (ad.company.about or "").strip())),
        ("summary", bool((ad.summary or "").strip())),
        ("responsibilities", len(ad.responsibilities) > 0),
        ("must_have", len(ad.must_have) > 0),
        ("nice_to_have", len(ad.nice_to_have) > 0),
        ("pay", has_pay),
        ("location_or_work_mode", bool((ad.location or "").strip()) or bool(ad.work_mode and ad.work_mode != "unspecified")),
        ("process", bool((ad.process or "").strip())),
    ]
    present = sum(1 for _, p in sections if p)
    out.append(_ok("structure.sections_present", present / len(sections), [f"missing: {n}" for n, p in sections if not p]))

    title = ad.title or ""
    problems: list[str] = []
    if not title.strip():
        problems.append("empty title")
    if len(title) > 60:
        problems.append(f"title is {len(title)} chars")
    gim_n, gim_hits = count_hits(title, GIMMICK)
    if gim_n:
        problems.append("gimmick words: " + ", ".join(gim_hits))
    if _LEVEL_WORDS.search(title) or _LEVEL_CODES.search(title):
        problems.append("internal level code in title")
    if _GENDER_MARK.search(title):
        problems.append("gender marker in title")
    out.append(_pf("structure.title_quality", not problems, problems))

    out.append(_ok("clarity.word_count", n_body))
    if n_body < 20:
        out.append(_na("clarity.reading_grade", "too short to measure"))
        out.append(_na("clarity.longest_sentence", "too short to measure"))
    else:
        out.append(_ok("clarity.reading_grade", _r2(flesch_kincaid_grade(text))))
        out.append(_ok("clarity.longest_sentence", longest_sentence(text)))

    paras = prose_paragraphs(ad)
    longest = max((len(words(p)) for p in paras), default=0)
    wall_words = sum(len(words(p)) for p in paras if len(words(p)) > 80)
    wall_share = wall_words / n_body if n_body else 0.0
    bullet_share = sum(len(words(b)) for b in bullet_items(ad)) / n_body if n_body else 0.0
    if n_body < 20:
        out.append(_na("clarity.scannability", "too short to measure"))
    else:
        out.append(_ok("clarity.scannability", round(1 - wall_share, 4), [f"longest paragraph {longest} words"] if longest > 80 else [], f"wall-of-text share {_r2(wall_share)}, bullet share {_r2(bullet_share)}"))

    # ---- D2 specificity & honesty (deterministic part)
    out.append(_ok("specific.must_have_count", len(ad.must_have)))
    out.append(_pf("specific.nice_to_have_split", len(ad.nice_to_have) > 0 or len(ad.must_have) <= 3, [], "nice-to-haves separated" if ad.nice_to_have else "no nice-to-have list"))

    inflated = [r for r in ad.must_have if (m := _YEARS.search(r)) and int(m.group(1)) > YEARS_THRESHOLD]
    out.append(_ok("specific.years_inflation", len(inflated), inflated))

    out.append(_pf("pay.range_present", has_pay))
    if ad.pay and ad.pay.min and ad.pay.max and ad.pay.min > 0:
        out.append(_ok("pay.range_width", _r2((ad.pay.max - ad.pay.min) / ad.pay.min)))
    elif has_pay:
        out.append(_ok("pay.range_width", 0, [], "single figure disclosed"))
    else:
        out.append(_na("pay.range_width", "no pay disclosed"))

    buzz_n, buzz_hits = count_hits(content, BUZZ)
    out.append(_ok("honesty.buzzword_density", _r2(per100(buzz_n)), buzz_hits))

    # ---- D3 inclusivity (lexicon part)
    masc_n, masc_hits = count_hits(content, GENDERED["masculine"])
    fem_n, fem_hits = count_hits(content, GENDERED["feminine"])
    out.append(_ok("inclusive.gender_coding", _r2(per100(masc_n - fem_n)), [f"masculine: {', '.join(masc_hits) or '-'}", f"feminine: {', '.join(fem_hits) or '-'}"]))

    gate_n, gate_hits = count_hits(content, EXCL["gate"])
    ctx_hits = [m.group(0).lower() for re_ in EXCL_CONTEXT for m in re_.finditer(content)]
    _, review_raw = count_hits(content, EXCL["review"])
    review_hits = [h for h in review_raw if not any(h in c for c in ctx_hits)]
    out.append(_ok("inclusive.exclusionary_terms", gate_n + len(ctx_hits), [*gate_hits, *ctx_hits, *[f"review: {h}" for h in review_hits]],
                   "review-only hits are not counted; the judge assesses them in context" if review_hits else None))

    out.append(_pf("inclusive.accessibility_statement", bool((ad.accessibility_statement or "").strip()) or bool(_ACCESS.search(text))))

    second = len(_SECOND.findall(content))
    third = len(_THIRD.findall(content))
    out.append(_ok("inclusive.candidate_address", _r2(per100(second - 2 * third)), [f"second-person {second}", f"third-person-candidate {third}"]))

    # ---- D4 compliance (deterministic part)
    if ctx.jurisdiction == "ZA":
        if ctx.designated_employer is False:
            out.append(_na("compliance.ee_statement", "not a designated employer"))
        else:
            out.append(_pf("compliance.ee_statement", bool((ad.ee_statement or "").strip()) or bool(_EE.search(text))))
        out.append(_pf("compliance.popia_notice", bool((ad.popia_notice or "").strip()) or bool(_POPIA.search(text))))
        out.append(_na("compliance.pay_disclosure_law", "no mandatory pay disclosure in ZA"))
    else:
        out.append(_na("compliance.ee_statement", "ZA only"))
        out.append(_na("compliance.popia_notice", "ZA only"))
        mandated = ctx.jurisdiction == "EU" or bool(_PAY_MANDATED_US.match(ctx.jurisdiction))
        out.append(_pf("compliance.pay_disclosure_law", has_pay) if mandated else _na("compliance.pay_disclosure_law", "no mandate in jurisdiction"))

    # ---- D6 searchability
    out.append(_ni("seo.title_matches_taxonomy", "ESCO/OFO taxonomy arrives in Phase 3"))
    first100 = " ".join(body[:100])
    title_tokens = [w for w in words(title) if len(w) > 2 and w not in STOP]
    title_early = not title_tokens or any(t in first100 for t in title_tokens)
    loc_early = not ad.location or any(t in first100 for t in words(ad.location))
    out.append(_pf("seo.key_terms_early", title_early and loc_early, [], f"title early: {title_early}, location early: {loc_early}"))
    stuff_limit = max(4, -(-n_body * 15 // 1000))  # ceil(n_body * 0.015): > 1.5 per 100 words, and at least 5
    stuffed = [t for t in title_tokens if body.count(t) > stuff_limit]
    out.append(_pf("seo.no_stuffing", not stuffed, [f'"{t}" repeated >{stuff_limit}×' for t in stuffed]))

    # ---- D7 process
    if ctx.hosted_apply:
        out.append(_na("process.contact_or_link", "hosted on a job board with its own apply button"))
    else:
        out.append(_pf("process.contact_or_link", bool((ad.apply_contact or "").strip()) or bool(_CONTACT.search(text))))

    return out
