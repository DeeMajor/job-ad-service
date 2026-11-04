"""Contrastive perturbations. Each degrades a structured ad along ONE metric; the scorer must score the
original above the perturbed copy on `targets`."""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from typing import Callable, Optional

from job_ad.metrics.types import Company, JobAd, Pay

_WORDS = re.compile(r"[a-zA-Z][a-zA-Z'’-]*")


def _words_in(ad: JobAd) -> int:
    return len(_WORDS.findall(ad.model_dump_json()))


def _clone(ad: JobAd) -> JobAd:
    return ad.model_copy(deep=True)


@dataclass
class Perturbation:
    name: str
    targets: list[str]
    needs_judge: bool
    apply: Callable[[JobAd], Optional[JobAd]]
    uses_original_as_source: bool = False


def _strip_pay(ad):
    if ad.pay and (ad.pay.min or ad.pay.max):
        c = _clone(ad); c.pay = None; return c
    return None


def _widen_pay(ad):
    if ad.pay and ad.pay.min and ad.pay.max and (ad.pay.max - ad.pay.min) / ad.pay.min <= 0.3:
        c = _clone(ad); c.pay = Pay(**{**ad.pay.model_dump(), "min": round(ad.pay.min * 0.6), "max": round(ad.pay.max * 1.6)}); return c
    return None


EXTRA_REQS = ["Bachelor's degree in a relevant field", "Advanced Excel skills", "Excellent written and verbal communication", "Proven track record of exceeding targets",
              "Valid driver's licence and own reliable transport", "Strong attention to detail", "Ability to work independently and in a team", "Willingness to travel", "Professional registration with the relevant body"]


def _inflate_must(ad):
    if len(ad.must_have) > 6:
        return None
    c = _clone(ad)
    target = max(len(ad.must_have) + 4, 9)  # always overshoot the 3–6 band
    c.must_have = [*ad.must_have, *EXTRA_REQS[: target - len(ad.must_have)]]
    return c


def _merge_nice(ad):
    if not ad.nice_to_have:
        return None
    c = _clone(ad); c.must_have = [*ad.must_have, *ad.nice_to_have]; c.nice_to_have = []; return c


def _inflate_years(ad):
    c = _clone(ad); c.must_have = [*ad.must_have, "Minimum 12+ years of experience in a similar role"]; return c


MASC = "We want an aggressive, competitive, dominant and decisive leader who is independent, assertive, fearless and ambitious, a self-confident and headstrong individual."


def _masc(ad):
    c = _clone(ad); n = max(1, math.ceil(_words_in(ad) / 200))
    c.summary = f"{ad.summary or ''} {' '.join([MASC] * n)}".strip(); return c


def _exclusionary(ad):
    c = _clone(ad); c.must_have = [*ad.must_have, "Young, energetic recent graduate"]; return c


BUZZ = "This is an exciting opportunity for a passionate self-starter and team player who thrives under pressure in our fast-paced, dynamic environment. We work hard play hard, wear many hats, and need a rockstar who can hit the ground running and think outside the box."


def _buzz(ad):
    c = _clone(ad); c.summary = f"{ad.summary or ''} {BUZZ}".strip(); return c


_SWAPS = [(r"\byou will\b", "the ideal candidate will"), (r"\byou'll\b", "the successful applicant will"), (r"\byou are\b", "the ideal candidate is"),
          (r"\byou have\b", "the candidate has"), (r"\byou're\b", "the ideal candidate is"), (r"\byourself\b", "the candidate"), (r"\byour\b", "the candidate's"), (r"\byou\b", "the ideal candidate")]


def _swap(s: str) -> str:
    for pat, rep in _SWAPS:
        s = re.sub(pat, rep, s, flags=re.IGNORECASE)
    return s


THIRD = "The ideal candidate will be responsible for the duties below. The successful applicant must meet all requirements. The candidate will report to the manager."


def _third_person(ad):
    c = _clone(ad)
    c.summary = f"{_swap(c.summary) if c.summary else ''} {THIRD}".strip()  # impersonal ads have no "you"; still introduce third-person language
    c.responsibilities = [_swap(x) for x in c.responsibilities]; c.must_have = [_swap(x) for x in c.must_have]
    c.nice_to_have = [_swap(x) for x in c.nice_to_have]; c.benefits = [_swap(x) for x in c.benefits]
    for k in ("team", "process", "other", "work_mode_detail"):
        if getattr(c, k):
            setattr(c, k, _swap(getattr(c, k)))
    if c.company and c.company.about:
        c.company.about = _swap(c.company.about)
    return c


def _delete_process(ad):
    if not ad.process:
        return None
    c = _clone(ad); c.process = None; c.apply_contact = None; c.closing_date = None; return c


BLOAT = ("Notwithstanding the aforementioned considerations, the organisation's multidimensional operational infrastructure necessitates comprehensive cross-functional collaboration methodologies that facilitate the optimisation of stakeholder-oriented deliverables across heterogeneous institutional environments, thereby engendering sustainable competitive differentiation through the systematic institutionalisation of performance-enhancing organisational capabilities and the concomitant realisation of strategically aligned transformational imperatives in accordance with internationally recognised governance frameworks and contemporary best-practice paradigms that are continuously benchmarked against industry-leading exemplars. "
         "Furthermore, it is incumbent upon all prospective incumbents to internalise the multifaceted strategic imperatives articulated herein, inasmuch as the successful operationalisation of said imperatives constitutes a sine qua non for the attainment of the organisation's overarching objectives, the realisation of which is predicated upon the harmonious integration of disparate functional competencies within a cohesive and synergistic operating model.")


def _bloat(ad):
    c = _clone(ad); n = max(1, math.ceil(_words_in(ad) / 300))
    about = (ad.company.about if ad.company else None) or ""
    c.company = Company(name=ad.company.name if ad.company else None, about="\n\n".join([p for p in [about, *([BLOAT] * n)] if p]))
    return c


def _gimmick(ad):
    c = _clone(ad); c.title = f"{ad.title} Rockstar Ninja (Grade 5)"; return c


def _strip_ee_popia(ad):
    if not (ad.ee_statement or ad.popia_notice):
        return None
    c = _clone(ad); c.ee_statement = None; c.popia_notice = None; return c


def _hallucinate(ad):
    c = _clone(ad); c.benefits = [*ad.benefits, "Fully paid medical aid for you and your whole family, plus a R50,000 annual education bursary and a company car"]; return c


def _vague_resp(ad):
    if not ad.responsibilities:
        return None
    c = _clone(ad); c.responsibilities = ["Support the team with various tasks", "Assist management as required", "Other duties as assigned", "Contribute to the success of the business"]; return c


def _untraceable(ad):
    c = _clone(ad); c.must_have = [*ad.must_have, "Fluent in Mandarin", "Scuba diving certification", "Forklift operator licence", "Grade 2 piano certificate", "Commercial pilot's licence"]; return c


def _proxy(ad):
    c = _clone(ad); c.must_have = [*ad.must_have, "Must be between 25 and 35 years old", "No family commitments that would interfere with overtime", "Must be a practising Christian"]; return c


def _prohibited(ad):
    c = _clone(ad); c.process = f"{ad.process or 'Apply with your CV.'} Attach a recent photograph, a certified copy of your ID, proof of HIV status and your marital certificate."; return c


def _vague_benefits(ad):
    if not ad.benefits:
        return None
    c = _clone(ad); c.benefits = ["Competitive salary", "Market-related benefits", "Great culture"]; return c


_SCRUB = re.compile(r"[^.•\n]*\b(report(?:s|ing)? (?:directly )?(?:to|into)|reporting line|line manager|team of \d+|join(?:s|ing)? (?:the|our) [^.•\n]*team|part of (?:the|our) [^.•\n]*team|hybrid|remote|on-?site|in[- ]the[- ]office|office[- ]based|work from home|days? (?:in|at) the office|(?:our |the )?office is (?:in|located|based)|based (?:in|at) our [^.•\n]*office|from our [^.•\n]*office)\b[^.•\n]*[.•\n]?", re.IGNORECASE)


def _scrub(s: str) -> str:
    return re.sub(r"\s{2,}", " ", _SCRUB.sub(" ", s)).strip()


def _remove_team_mode(ad):
    if not (ad.team or (ad.work_mode and ad.work_mode != "unspecified")):
        return None
    c = _clone(ad); c.team = None; c.work_mode = "unspecified"; c.work_mode_detail = None
    for k in ("summary", "process", "other", "location"):
        if getattr(c, k):
            setattr(c, k, _scrub(getattr(c, k)) or None)
    if c.company and c.company.about:
        c.company.about = _scrub(c.company.about) or None
    c.responsibilities = [x for x in (_scrub(r) for r in c.responsibilities) if x]
    c.benefits = [x for x in (_scrub(b) for b in c.benefits) if x]
    return c


def _remove_timeline(ad):
    if not ad.process:
        return None
    c = _clone(ad); c.process = "Apply now."; c.closing_date = None; return c


PERTURBATIONS: list[Perturbation] = [
    Perturbation("strip_pay", ["pay.range_present", "structure.sections_present"], False, _strip_pay),
    Perturbation("widen_pay_range", ["pay.range_width"], False, _widen_pay),
    Perturbation("inflate_must_haves", ["specific.must_have_count"], False, _inflate_must),
    Perturbation("merge_nice_to_haves", ["specific.nice_to_have_split"], False, _merge_nice),
    Perturbation("inflate_years", ["specific.years_inflation"], False, _inflate_years),
    Perturbation("inject_masculine_coding", ["inclusive.gender_coding"], False, _masc),
    Perturbation("inject_exclusionary_phrase", ["inclusive.exclusionary_terms"], False, _exclusionary),
    Perturbation("inject_buzzwords", ["honesty.buzzword_density"], False, _buzz),
    Perturbation("third_person_candidate", ["inclusive.candidate_address"], False, _third_person),
    Perturbation("delete_process", ["process.contact_or_link", "structure.sections_present"], False, _delete_process),
    Perturbation("bloat_prose", ["clarity.reading_grade", "clarity.longest_sentence", "clarity.scannability"], False, _bloat),
    Perturbation("gimmick_title", ["structure.title_quality"], False, _gimmick),
    Perturbation("strip_ee_popia", ["compliance.ee_statement", "compliance.popia_notice"], False, _strip_ee_popia),
    # ---- judge-detected
    Perturbation("hallucinate_benefit", ["honesty.grounding"], True, _hallucinate, uses_original_as_source=True),
    Perturbation("vague_responsibilities", ["specific.responsibility_concreteness"], True, _vague_resp),
    Perturbation("untraceable_requirements", ["specific.requirement_traceability"], True, _untraceable),
    Perturbation("proxy_requirement", ["inclusive.proxy_requirements", "compliance.protected_grounds"], True, _proxy),
    Perturbation("prohibited_request", ["compliance.no_prohibited_requests"], True, _prohibited),
    Perturbation("vague_benefits", ["evp.benefits_specific"], True, _vague_benefits),
    Perturbation("remove_team_and_work_mode", ["evp.team_context", "evp.work_mode_clarity"], True, _remove_team_mode),
    Perturbation("remove_timeline", ["process.steps_and_timeline"], True, _remove_timeline),
]


def apply_all(ad: JobAd) -> list[tuple[Perturbation, JobAd]]:
    out = []
    for p in PERTURBATIONS:
        pa = p.apply(ad)
        if pa is not None:
            out.append((p, pa))
    return out
