"""HiringBrief v0.3 — the service's request contract.

Required: title, company.name, at least one responsibility, at least one must-have — without these no prompt can produce a
publishable ad, so a draft would be money spent on a not_ready result. Everything else is optional: absent = not provided,
and the drafter may not fill the gap; the completeness check (/v1/briefs/check) says what each missing field is worth."""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator

from ..metrics.types import JobAd, Source, ScoringContext

BRIEF_SCHEMA_VERSION = "0.3"


class Requirement(BaseModel):
    text: str = Field(min_length=1)
    justification: Optional[str] = None  # which duty needs it; feeds traceability and the EE inherent-requirement defence


class PayBrief(BaseModel):
    min: Optional[float] = Field(default=None, ge=0)
    max: Optional[float] = Field(default=None, ge=0)
    currency: str = Field(default="ZAR", min_length=3, max_length=3)
    period: Literal["year", "month", "hour", "day", "week"]
    basis: Optional[str] = None


class CompanyBrief(BaseModel):
    name: str = Field(min_length=1)
    about: Optional[str] = None
    website: Optional[str] = Field(default=None, description="Employer website; when set, web enrichment is restricted to this domain")


class TeamBrief(BaseModel):
    reports_to: Optional[str] = None
    size: Optional[int] = Field(default=None, gt=0)
    notes: Optional[str] = None


class ProcessBrief(BaseModel):
    steps: Optional[str] = None
    closing_date: Optional[date] = None
    contact: Optional[str] = None
    reference: Optional[str] = None


class Statements(BaseModel):
    ee: Optional[str] = None
    popia: Optional[str] = None
    accessibility: Optional[str] = None


class HiringBrief(BaseModel):
    schema_version: Literal["0.3"] = BRIEF_SCHEMA_VERSION
    # the role
    title: str = Field(min_length=1)
    seniority: Optional[Literal["entry", "junior", "mid", "senior", "lead", "manager", "head", "executive"]] = None
    employment_type: Optional[Literal["permanent", "fixed_term", "contract", "part_time", "internship", "learnership", "temporary"]] = None
    purpose: Optional[str] = None
    success_measures: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(min_length=1, description="At least one duty; the drafter rewrites, it does not add duties")
    tools: list[str] = Field(default_factory=list)
    must_have: list[Requirement] = Field(min_length=1, description="At least one requirement")
    nice_to_have: list[Requirement] = Field(default_factory=list)
    # where, when, how much
    location: Optional[str] = None
    work_mode: Optional[Literal["remote", "hybrid", "onsite"]] = None
    work_mode_detail: Optional[str] = None
    hours: Optional[str] = None
    start_date: Optional[date] = None
    positions: Optional[int] = Field(default=None, gt=0)
    pay: Optional[PayBrief] = None
    benefits: list[str] = Field(default_factory=list)
    # the people
    company: CompanyBrief
    team: Optional[TeamBrief] = None
    # the process
    process: Optional[ProcessBrief] = None
    statements: Optional[Statements] = None
    # scoring context
    jurisdiction: str = Field(default="ZA", pattern=r"^(ZA|EU|US|US-[A-Z]{2})$")
    designated_employer: Optional[bool] = None
    hosted_apply: bool = False
    channel: Literal["default", "linkedin", "indeed"] = "default"

    @field_validator("must_have", "nice_to_have", mode="before")
    @classmethod
    def _coerce_requirements(cls, v):
        return [{"text": x} if isinstance(x, str) else x for x in (v or [])]


def render_brief(b: HiringBrief) -> str:
    """The single SOURCE block the drafter and the grounding judge both see."""
    L: list[str] = []

    def add(k, v):
        if v is not None and str(v).strip():
            L.append(f"{k}: {str(v).strip()}")

    def lst(k, xs):
        if xs:
            L.append(f"{k}:\n" + "\n".join(f"  - {x}" for x in xs))

    def reqs(k, xs: list[Requirement]):
        lst(k, [f"{r.text} (needed because: {r.justification})" if r.justification else r.text for r in xs])

    add("Title", b.title); add("Seniority", b.seniority); add("Employment type", b.employment_type.replace("_", " ") if b.employment_type else None); add("Positions", b.positions)
    add("Company", b.company.name); add("About the company", b.company.about); add("Purpose of the role", b.purpose)
    lst("What success looks like", b.success_measures); lst("Responsibilities (hiring manager's notes)", b.responsibilities); lst("Tools and systems", b.tools)
    reqs("Must-have requirements", b.must_have); reqs("Nice-to-have", b.nice_to_have)
    add("Location", b.location)
    add("Work mode", f"{b.work_mode}{f' ({b.work_mode_detail})' if b.work_mode_detail else ''}" if b.work_mode else None)
    add("Hours", b.hours); add("Start date", b.start_date)
    if b.pay:
        rng = f"{b.pay.currency} {b.pay.min if b.pay.min is not None else ''}{f' – {b.pay.max}' if b.pay.max is not None and b.pay.max != b.pay.min else ''} per {b.pay.period}"
        add("Pay", rng + (f"; basis: {b.pay.basis}" if b.pay.basis else ""))
    lst("Benefits", b.benefits)
    if b.team:
        add("Reports to", b.team.reports_to); add("Team size", b.team.size); add("Team notes", b.team.notes)
    if b.process:
        add("Application process", b.process.steps); add("Closing date", b.process.closing_date); add("Reference", b.process.reference); add("How to apply / contact", b.process.contact)
    if b.statements:
        add("Employment equity statement", b.statements.ee); add("POPIA notice", b.statements.popia); add("Accessibility statement", b.statements.accessibility)
    if b.hosted_apply:
        L.append("Note: the ad will be published on a job board with its own Apply button.")
    return "\n".join(L)


def _d(s: Optional[str]) -> Optional[date]:
    """Parse the closing-date strings real SA ads use. Day-first: '09/11/26' is 9 November, not September 11."""
    if not s:
        return None
    t = re.sub(r"[,\s]+\d{1,2}:\d{2}.*$", "", s.strip())  # drop a trailing time ("05 November 2026, 23:59")
    t = re.sub(r"^(?:mon|tues|wednes|thurs|fri|satur|sun)day,?\s+", "", t, flags=re.I)
    for fmt in ("%Y-%m-%d", "%d/%m/%y", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d %B %Y", "%d %b %Y", "%B %d, %Y", "%d %B, %Y", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(t, fmt).date()
        except ValueError:
            continue
    return None


def brief_from_job_ad(ad: JobAd, *, jurisdiction: str = "ZA", hosted_apply: bool = False, channel: str = "default") -> HiringBrief:
    """Derive a brief from a structured real ad (old-ad intake, and the Phase 1 eval). Facts only, not the real ad's prose."""
    u = lambda s: (s.strip() if s and s.strip() else None)
    pay = None
    if ad.pay and (ad.pay.min or ad.pay.max) and ad.pay.period:
        pay = PayBrief(min=ad.pay.min, max=ad.pay.max if ad.pay.max is not None else ad.pay.min, currency=ad.pay.currency if ad.pay.currency and len(ad.pay.currency) == 3 else "ZAR", period=ad.pay.period, basis=u(ad.pay.basis))
    return HiringBrief(
        title=ad.title, company=CompanyBrief(name=(ad.company.name if ad.company and ad.company.name else "Unnamed employer"), about=u(ad.company.about) if ad.company else None),
        purpose=u(ad.summary), responsibilities=ad.responsibilities, must_have=[Requirement(text=x) for x in ad.must_have], nice_to_have=[Requirement(text=x) for x in ad.nice_to_have],
        location=u(ad.location), work_mode=ad.work_mode if ad.work_mode and ad.work_mode != "unspecified" else None, work_mode_detail=u(ad.work_mode_detail), pay=pay, benefits=ad.benefits,
        team=TeamBrief(notes=ad.team) if ad.team else None,
        process=ProcessBrief(steps=u(ad.process), closing_date=_d(ad.closing_date), contact=u(ad.apply_contact)) if (ad.process or ad.closing_date or ad.apply_contact) else None,
        statements=Statements(ee=u(ad.ee_statement), popia=u(ad.popia_notice), accessibility=u(ad.accessibility_statement)) if (ad.ee_statement or ad.popia_notice or ad.accessibility_statement) else None,
        jurisdiction=jurisdiction, hosted_apply=hosted_apply, channel=channel,
    )


def scoring_context_for(brief: HiringBrief, brief_text: Optional[str] = None) -> ScoringContext:
    """The brief is the only source: grounding is judged against it."""
    return ScoringContext(jurisdiction=brief.jurisdiction, channel=brief.channel, designated_employer=brief.designated_employer, hosted_apply=brief.hosted_apply,
                          sources=[Source(id="brief", text=brief_text or render_brief(brief))])
