"""Rendering and text utilities. Hand-rolled on purpose: the Phase 0 benchmark validated these exact
definitions (syllable heuristic, sentence splitting), so a library swap is a logged experiment, not a drop-in."""
from __future__ import annotations

import re
from typing import Iterable

from .types import JobAd, Pay

_WORD_RE = re.compile(r"(?<![a-z0-9])[a-z][a-z'’-]*(?![a-z0-9])")
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_VOWEL_GROUPS = re.compile(r"[aeiouy]{1,2}")


def _bullets(xs: Iterable[str]) -> str:
    return "\n".join(f"• {x}" for x in xs)


def _fmt(n: float) -> str:
    return f"{int(n):,}" if float(n).is_integer() else f"{n:,}"


def render_pay(p: Pay) -> str:
    cur = p.currency or ""
    per = f" per {p.period}" if p.period else ""
    if p.min and p.max:
        rng = f"{cur} {_fmt(p.min)} – {_fmt(p.max)}"
    else:
        rng = f"{cur} {_fmt(p.min or p.max or 0)}"
    return f"Salary: {rng.strip()}{per}{'. ' + p.basis if p.basis else ''}"


def render_ad(ad: JobAd, headings: bool = True) -> str:
    """Plain text the way a candidate reads it. headings=False omits our section labels
    (lexicon and pronoun metrics must not count them)."""

    def h(label: str, body: str) -> str:
        return f"{label}\n{body}" if headings else body

    parts: list[str] = [ad.title]
    if ad.company and ad.company.name:
        parts.append(ad.company.name)
    if ad.location or ad.work_mode:
        bits = [ad.location, ad.work_mode if ad.work_mode and ad.work_mode != "unspecified" else None, ad.work_mode_detail]
        parts.append(" · ".join(b for b in bits if b))
    if ad.pay and (ad.pay.min or ad.pay.max):
        parts.append(render_pay(ad.pay))
    if ad.company and ad.company.about:
        parts.append(h("About us", ad.company.about))
    if ad.summary:
        parts.append(h("About the role", ad.summary))
    if ad.team:
        parts.append(h("Your team", ad.team))
    if ad.responsibilities:
        parts.append(h("What you'll do", _bullets(ad.responsibilities)))
    if ad.must_have:
        parts.append(h("What you need", _bullets(ad.must_have)))
    if ad.nice_to_have:
        parts.append(h("Nice to have", _bullets(ad.nice_to_have)))
    if ad.benefits:
        parts.append(h("What we offer", _bullets(ad.benefits)))
    if ad.process:
        parts.append(h("How to apply", ad.process))
    if ad.closing_date:
        parts.append("Closing date: " + ad.closing_date)
    for extra in (ad.apply_contact, ad.accessibility_statement, ad.ee_statement, ad.popia_notice, ad.other):
        if extra:
            parts.append(extra)
    return "\n\n".join(parts)


def render_markdown(ad: JobAd) -> str:
    """The ad as Markdown for display, copy-paste or conversion to HTML. Deterministic from the structure; the JSON stays canonical."""
    L: list[str] = [f"# {ad.title}"]
    meta = [ad.company.name if ad.company and ad.company.name else None, ad.location, ad.work_mode if ad.work_mode and ad.work_mode != "unspecified" else None, ad.work_mode_detail]
    if any(meta):
        L.append("**" + " · ".join(m for m in meta if m) + "**")
    if ad.pay and (ad.pay.min or ad.pay.max):
        L.append(f"**{render_pay(ad.pay)}**")
    def section(title: str, body: str | None = None, items: list[str] | None = None) -> None:
        if body:
            L.extend(["", f"## {title}", "", body])
        elif items:
            L.extend(["", f"## {title}", "", *[f"- {x}" for x in items]])
    section("About us", ad.company.about if ad.company else None)
    section("About the role", ad.summary)
    section("Your team", ad.team)
    section("What you'll do", items=ad.responsibilities)
    section("What you need", items=ad.must_have)
    section("Nice to have", items=ad.nice_to_have)
    section("What we offer", items=ad.benefits)
    section("How to apply", ad.process)
    tail = []
    if ad.closing_date:
        tail.append(f"**Closing date:** {ad.closing_date}")
    for x in (ad.apply_contact, ad.accessibility_statement, ad.ee_statement, ad.popia_notice, ad.other):
        if x:
            tail.append(x)
    if tail:
        L.extend(["", "---", "", *[t for pair in zip(tail, [""] * len(tail)) for t in pair]])
    return "\n".join(L).rstrip() + "\n"


def prose_paragraphs(ad: JobAd) -> list[str]:
    """Prose paragraphs (not bullet lists), for paragraph-length checks."""
    out: list[str] = []
    for x in (ad.company.about if ad.company else None, ad.summary, ad.team, ad.process, ad.other):
        if x:
            out.extend(p.strip() for p in re.split(r"\n{2,}", x) if p.strip())
    return out


def bullet_items(ad: JobAd) -> list[str]:
    return [*ad.responsibilities, *ad.must_have, *ad.nice_to_have, *ad.benefits]


def words(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


def sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT_SPLIT.split(text.replace("•", "\n")) if words(s.strip())]


def syllables(word: str) -> int:
    """Heuristic English syllable count; adequate for Flesch–Kincaid at document scale."""
    w = re.sub(r"[^a-z]", "", word.lower())
    if len(w) <= 3:
        return 1
    w = re.sub(r"^y", "", w)
    if not re.search(r"[^aeiouy]le$", w):
        w = re.sub(r"(?:es|ed|e)$", "", w)
    groups = _VOWEL_GROUPS.findall(w)
    return max(1, len(groups))


def flesch_kincaid_grade(text: str) -> float:
    ws = words(text)
    ss = sentences(text)
    if not ws or not ss:
        return 0.0
    syl = sum(syllables(w) for w in ws)
    return 0.39 * (len(ws) / len(ss)) + 11.8 * (syl / len(ws)) - 15.59


def longest_sentence(text: str) -> int:
    return max((len(words(s)) for s in sentences(text)), default=0)


def count_hits(text: str, terms: Iterable[str]) -> tuple[int, list[str]]:
    """Stems match word-initially (Gaucher lexicon style); phrases match as whole phrases."""
    lower = text.lower()
    hits: list[str] = []
    for t in terms:
        pat = rf"\b{re.escape(t)}\b" if " " in t else rf"\b{re.escape(t)}[a-z]*"
        hits.extend(m.group(0) for m in re.finditer(pat, lower))
    return len(hits), hits
