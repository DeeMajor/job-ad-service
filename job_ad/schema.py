"""JobAdOut: the model-facing output shape (no Optional/Union fields — the API caps union-typed parameters at 16).
Absent text = "", absent number = 0. from_llm_output converts to the natural JobAd."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .metrics.types import Company, JobAd, Pay


class JobAdOut(BaseModel):
    title: str
    company_name: str = Field(description='"" if not stated')
    company_about: str = Field(description='"" if not stated')
    summary: str = Field(description='"" if not stated')
    responsibilities: list[str]
    must_have: list[str]
    nice_to_have: list[str]
    pay_min: float = Field(description="0 if not stated")
    pay_max: float = Field(description="0 if not stated; equal to pay_min for a single figure")
    pay_currency: str = Field(description='ISO code like ZAR, or "" if not stated')
    pay_period: Literal["year", "month", "hour", "day", "week", "unspecified"]
    pay_basis: str = Field(description='what determines placement in the range, or ""')
    location: str = Field(description='"" if not stated')
    work_mode: Literal["remote", "hybrid", "onsite", "unspecified"]
    work_mode_detail: str = Field(description='e.g. "3 days in office", or ""')
    benefits: list[str]
    team: str = Field(description='who the person works with / reports to, or ""')
    process: str = Field(description='application steps, rounds, timeline, or ""')
    closing_date: str = Field(description='"" if not stated')
    accessibility_statement: str = Field(description='"" if not stated')
    ee_statement: str = Field(description='employment equity / affirmative action statement, or ""')
    popia_notice: str = Field(description='personal-information / privacy notice, or ""')
    apply_contact: str = Field(description='URL, email or instruction, or ""')
    other: str = Field(description='text that fits no field, or ""')


def _t(x: str):
    return x.strip() or None


def from_llm_output(p: JobAdOut) -> JobAd:
    has_pay = p.pay_min > 0 or p.pay_max > 0
    return JobAd(
        title=p.title,
        company=Company(name=_t(p.company_name), about=_t(p.company_about)) if (_t(p.company_name) or _t(p.company_about)) else None,
        summary=_t(p.summary), responsibilities=p.responsibilities, must_have=p.must_have, nice_to_have=p.nice_to_have,
        pay=Pay(min=p.pay_min or None, max=p.pay_max or p.pay_min or None, currency=_t(p.pay_currency), period=None if p.pay_period == "unspecified" else p.pay_period, basis=_t(p.pay_basis)) if has_pay else None,
        location=_t(p.location), work_mode=p.work_mode, work_mode_detail=_t(p.work_mode_detail), benefits=p.benefits, team=_t(p.team),
        process=_t(p.process), closing_date=_t(p.closing_date), accessibility_statement=_t(p.accessibility_statement), ee_statement=_t(p.ee_statement),
        popia_notice=_t(p.popia_notice), apply_contact=_t(p.apply_contact), other=_t(p.other),
    )
