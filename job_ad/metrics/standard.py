"""The draft standard: a readable verdict with reasons, replacing the old gate/zeroing model.

level     publishable  — no must-fix reasons and composite ≥ publish threshold
          review       — no must-fix reasons, composite between review and publish thresholds
          not_ready    — any must-fix reason, or composite below the review threshold
reasons   must_fix     — legal, honesty or minimum-content problems; publishing with these open is a risk, not a style issue
          should_fix   — scored metrics well below target (normalised < 0.5)
          could_improve— scored metrics somewhat below target (0.5 ≤ normalised < 0.8)
The composite is always computed; nothing is zeroed.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from .spec import MetricSpec, Spec
from .types import MetricResult

Severity = Literal["must_fix", "should_fix", "could_improve"]

# Plain-language labels for every metric id (frontends should still prefer /v1/spec for structure).
LABELS: dict[str, str] = {
    "structure.minimum_content": "Minimum content", "structure.sections_present": "Sections present", "structure.title_matches_content": "Title matches the work",
    "structure.title_quality": "Title quality", "clarity.word_count": "Length", "clarity.reading_grade": "Reading level", "clarity.longest_sentence": "Longest sentence",
    "clarity.scannability": "Scannability", "specific.responsibility_concreteness": "Concrete duties", "specific.must_have_count": "Number of must-haves",
    "specific.nice_to_have_split": "Must-haves vs nice-to-haves", "specific.requirement_traceability": "Requirements justified by duties", "specific.years_inflation": "Years-of-experience inflation",
    "pay.range_present": "Pay disclosed", "pay.range_width": "Pay range width", "pay.context_present": "How pay is set", "honesty.buzzword_density": "Buzzwords",
    "honesty.grounding": "Only facts from the brief", "inclusive.gender_coding": "Gender-neutral wording", "inclusive.exclusionary_terms": "Exclusionary wording",
    "inclusive.proxy_requirements": "Requirements that exclude protected groups", "inclusive.accessibility_statement": "Accessibility statement", "inclusive.candidate_address": "Speaks to the candidate",
    "compliance.protected_grounds": "No discrimination on protected grounds", "compliance.no_prohibited_requests": "No prohibited requests of applicants", "compliance.pay_disclosure_law": "Legally required pay disclosure",
    "compliance.ee_statement": "Employment Equity statement", "compliance.popia_notice": "POPIA notice", "process.steps_and_timeline": "Application steps and timeline", "process.contact_or_link": "How to apply",
    "evp.why_this_role": "Why this role", "evp.benefits_specific": "Specific benefits", "evp.team_context": "Reporting line or team size", "evp.work_mode_clarity": "Work mode",
    "seo.title_matches_taxonomy": "Standard job title", "seo.key_terms_early": "Key terms near the top", "seo.no_stuffing": "No keyword stuffing",
}

MUST_FIX_MESSAGES: dict[str, str] = {
    "structure.minimum_content": "The ad is missing basics ({evidence}). It needs a title, at least one duty and one requirement, and about 100 words before it can be published.",
    "honesty.grounding": "The ad states things the brief does not say. Remove them or add them to the brief: {evidence}",
    "inclusive.exclusionary_terms": "Wording that excludes people on grounds the Employment Equity Act protects: {evidence}. Rephrase or remove.",
    "compliance.protected_grounds": "The ad prefers or excludes people on a protected ground. {reasoning}",
    "compliance.no_prohibited_requests": "The ad asks applicants for information that must not be requested at application stage. {reasoning}",
    "compliance.pay_disclosure_law": "This jurisdiction requires a pay range in the advertisement.",
    "compliance.ee_statement": "A designated employer's ad should carry its Employment Equity statement.",
}


# What to do about a should-fix / could-improve metric, in the recruiter's terms.
HINTS: dict[str, str] = {
    "structure.sections_present": "Add the missing sections (about the company, duties, requirements, pay, location, how to apply).",
    "structure.title_matches_content": "Use a title that names the occupation the duties describe.",
    "structure.title_quality": "Use the plain job title: under 60 characters, no grade codes, no gimmick words.",
    "clarity.word_count": "Aim for 300–650 words.", "clarity.reading_grade": "Shorter sentences and everyday words; aim for a Grade 8 reading level.",
    "clarity.longest_sentence": "Split the longest sentence; keep sentences under 35 words.", "clarity.scannability": "Break long paragraphs into bullets or short paragraphs.",
    "specific.responsibility_concreteness": "Make each duty name a specific activity and its object, with scale or a measure where you can.",
    "specific.must_have_count": "Keep must-haves to three to six; move the rest to nice-to-have.", "specific.nice_to_have_split": "Separate nice-to-haves from must-haves.",
    "specific.requirement_traceability": "Drop requirements no duty needs, or add the duty that needs them.", "specific.years_inflation": "Remove years-of-experience figures above what the role needs.",
    "pay.range_present": "No salary or range in the ad. Add pay to the brief; it is the strongest driver of applications.", "pay.range_width": "Narrow the range to within 30% of the minimum.",
    "pay.context_present": "Say what decides placement in the range.", "honesty.buzzword_density": "Cut the buzzwords (fast-paced, self-starter, competitive salary…).",
    "inclusive.gender_coding": "Balance masculine-coded adjectives (aggressive, dominant, competitive) with neutral wording.", "inclusive.proxy_requirements": "Remove requirements that exclude protected groups unless the work truly needs them.",
    "inclusive.accessibility_statement": "Add how applicants can request accommodation.", "inclusive.candidate_address": "Write to the reader as \"you\"; avoid \"the ideal candidate\".",
    "compliance.popia_notice": "Add your POPIA / personal-information notice.", "compliance.ee_statement": "Add your Employment Equity statement.",
    "process.steps_and_timeline": "Describe the interview steps and when applicants will hear back.", "process.contact_or_link": "Say how to apply.",
    "evp.why_this_role": "Add a sentence on what the person will own, build, learn or grow into.", "evp.benefits_specific": "Name the benefits with amounts or days instead of \"competitive\".",
    "evp.team_context": "Say who the person reports to, or the team size.", "evp.work_mode_clarity": "State remote, hybrid or on-site, and office days if hybrid.",
    "seo.key_terms_early": "Put the job title and location in the first 100 words.", "seo.no_stuffing": "Stop repeating the title keyword.",
}


class Reason(BaseModel):
    severity: Severity
    metric: str
    label: str
    message: str
    evidence: list[str] = Field(default_factory=list)


class Standard(BaseModel):
    level: Literal["publishable", "review", "not_ready"]
    summary: str
    reasons: list[Reason]


def _target(m: MetricSpec) -> str:
    if m.type == "pass_fail":
        return "pass"
    n = m.norm
    if not n:
        return ""
    if n.kind == "linear":
        return f"≥ {n.lo}"
    lo, hi = n.lo, n.hi
    if lo is not None and hi is not None:
        return f"{lo:g}–{hi:g}"
    return f"≥ {lo:g}" if lo is not None else f"≤ {hi:g}"


def build_standard(metrics: list[MetricResult], must_fix_ids: list[str], composite: float, spec: Spec, max_reasons: int = 10) -> Standard:
    reasons: list[Reason] = []
    by_id = {m.id: m for m in metrics}
    for mid in must_fix_ids:
        m = by_id[mid]
        ev = m.evidence[:4]
        tmpl = MUST_FIX_MESSAGES.get(mid, "{label}: {reasoning}")
        msg = tmpl.format(evidence="; ".join(ev) if ev else "see the ad", reasoning=m.reasoning or "", label=LABELS.get(mid, mid)).strip()
        reasons.append(Reason(severity="must_fix", metric=mid, label=LABELS.get(mid, mid), message=msg, evidence=ev))
    scored = sorted((m for m in metrics if m.status == "ok" and m.normalized is not None and m.id not in must_fix_ids and not spec.dimensions[m.dimension].gate),
                    key=lambda m: m.normalized)
    for m in scored:
        if m.normalized >= 0.8 or len(reasons) >= max_reasons:
            break
        ms = spec.metric(m.id)
        sev: Severity = "should_fix" if m.normalized < 0.5 else "could_improve"
        measured = "" if ms.type == "pass_fail" else f"Measured {m.raw:g}, target {_target(ms)}. "
        judge_note = f" {m.reasoning}" if m.reasoning and ms.grader == "judge" else ""
        msg = f"{measured}{HINTS.get(m.id, '')}{judge_note}".strip()
        reasons.append(Reason(severity=sev, metric=m.id, label=LABELS.get(m.id, m.id), message=msg, evidence=m.evidence[:3]))
    must = [r for r in reasons if r.severity == "must_fix"]
    if must:
        level = "not_ready"
        summary = f"Not ready to publish: {len(must)} issue{'s' if len(must) > 1 else ''} to fix first ({', '.join(r.label.lower() for r in must[:3])}{'…' if len(must) > 3 else ''}). Composite {composite:g}."
    elif composite >= spec.publish_threshold:
        level = "publishable"
        summary = f"Publishable. Composite {composite:g} against a bar of {spec.publish_threshold:g}." + (f" {len(reasons)} optional improvement{'s' if len(reasons) != 1 else ''} listed." if reasons else "")
    elif composite >= spec.review_threshold:
        level = "review"
        summary = f"Needs a review pass: composite {composite:g}, publishable from {spec.publish_threshold:g}. Start with: {', '.join(r.label.lower() for r in reasons[:3])}."
    else:
        level = "not_ready"
        summary = f"Not ready: composite {composite:g}, well below the {spec.publish_threshold:g} bar. Start with: {', '.join(r.label.lower() for r in reasons[:3])}."
    return Standard(level=level, summary=summary, reasons=reasons)
