"""Redaction of identifiers and protected attributes from free text, before any model sees it.

Best-effort pattern based: ID/passport numbers, emails, phones, dates of birth, ages, honorific+name, label:value lines for
gender/race/marital status/nationality/religion/health/home language/address, gendered family words, street addresses,
LinkedIn URLs. The contract has no fields for these; redaction covers what candidates paste into cv_text anyway. The frontend
should prefer structured answers over CV dumps. `residual_scan` re-runs the detectors on the redacted text (should be 0)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_LABELS = (r"gender|sex|race|ethnicity|ethnic group|population group|marital status|nationality|citizenship|religion|religious affiliation|"
           r"home language|mother tongue|disability|disabilities|health status|medical condition|id number|identity number|id no\.?|passport number|passport no\.?|"
           r"home address|physical address|postal address|residential address|address|date of birth|d\.?o\.?b\.?|age|place of birth|dependants|children|"
           r"driver's licence no\.?|licence number")

PATTERNS: list[tuple[str, re.Pattern]] = [
    ("sa_id", re.compile(r"\b\d{2}[01]\d[0-3]\d{8}\b")),
    ("long_number", re.compile(r"\b\d{13}\b")),
    ("email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("phone", re.compile(r"(?:\+27|\(?0\d{2}\)?)[\s-]?\d{3}[\s-]?\d{4}\b")),
    ("linkedin", re.compile(r"(?:https?://)?(?:www\.)?linkedin\.com/in/\S+", re.I)),
    ("label_value", re.compile(rf"\b(?:{_LABELS})\s*[:\-–]\s*[^\n.;]*", re.I)),
    ("dob_phrase", re.compile(r"\b(?:born(?: on| in)?|date of birth|d\.o\.b\.?)\s+(?:\d{1,2}(?:st|nd|rd|th)?\s+)?(?:\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}|[A-Za-z]+\s+\d{1,4}(?:,?\s+\d{4})?|\d{4})", re.I)),
    ("age_phrase", re.compile(r"\b(?:aged?\s*[:\-]?\s*\d{1,2}|\d{1,2}[\s-]*(?:years?[\s-]*old|yrs?[\s-]*old|y/o))\b", re.I)),
    ("honorific_name", re.compile(r"\b(?:Mr|Mrs|Ms|Miss|Mx|Dr|Prof|Adv|Rev|Pastor)\.?\s+[A-Z][A-Za-z'\-]+(?:\s+[A-Z][A-Za-z'\-]+){0,2}")),
    ("gendered_family", re.compile(r"\b(?:male|female|he/him|she/her|they/them|husband|wife|married|divorced|widowed|mother of|father of|pregnant|pregnancy|maternity leave|paternity leave)\b", re.I)),
    ("citizen", re.compile(r"\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)?\s(?:citizen|national|passport holder)\b")),
    ("street_address", re.compile(r"\b\d{1,5}[A-Za-z]?\s+[A-Z][A-Za-z]+(?:\s[A-Z][A-Za-z]+)?\s+(?:Street|St|Road|Rd|Avenue|Ave|Drive|Dr|Lane|Crescent|Cres|Close|Boulevard|Blvd|Way)\b[^\n.;]*")),
]

REPLACEMENT = "[REDACTED]"


@dataclass
class Redaction:
    text: str
    count: int = 0
    kinds: dict[str, int] = field(default_factory=dict)


def redact(text: str | None) -> Redaction:
    if not text:
        return Redaction(text="")
    out = text
    kinds: dict[str, int] = {}
    for name, pat in PATTERNS:
        out, n = pat.subn(REPLACEMENT, out)
        if n:
            kinds[name] = kinds.get(name, 0) + n
    out = re.sub(r"(?:\[REDACTED\]\s*){2,}", REPLACEMENT + " ", out)
    return Redaction(text=out, count=sum(kinds.values()), kinds=kinds)


def residual_scan(text: str) -> int:
    """How many detector hits remain in an already-redacted text (0 = clean)."""
    return sum(len(pat.findall(text)) for _, pat in PATTERNS)
