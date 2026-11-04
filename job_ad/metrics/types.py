"""Core types: the structured JobAd, scoring context, metric results and the Scorecard."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

WorkMode = Literal["remote", "hybrid", "onsite", "unspecified"]
PayPeriod = Literal["year", "month", "hour", "day", "week"]
Channel = Literal["default", "linkedin", "indeed"]
MetricStatus = Literal["ok", "skipped", "not_implemented", "not_applicable", "error"]
Grader = Literal["deterministic", "lexicon", "judge"]


class Company(BaseModel):
    name: Optional[str] = None
    about: Optional[str] = None


class Pay(BaseModel):
    min: Optional[float] = None
    max: Optional[float] = None
    currency: Optional[str] = None
    period: Optional[PayPeriod] = None
    basis: Optional[str] = None  # how placement in the range is decided, if stated


class JobAd(BaseModel):
    """Structured job ad. Both the drafter's output and the benchmark's normalised form of real ads."""

    title: str
    company: Optional[Company] = None
    summary: Optional[str] = None
    responsibilities: list[str] = Field(default_factory=list)
    must_have: list[str] = Field(default_factory=list)
    nice_to_have: list[str] = Field(default_factory=list)
    pay: Optional[Pay] = None
    location: Optional[str] = None
    work_mode: Optional[WorkMode] = None
    work_mode_detail: Optional[str] = None
    benefits: list[str] = Field(default_factory=list)
    team: Optional[str] = None
    process: Optional[str] = None  # application steps, rounds, timeline
    closing_date: Optional[str] = None
    accessibility_statement: Optional[str] = None
    ee_statement: Optional[str] = None
    popia_notice: Optional[str] = None
    apply_contact: Optional[str] = None
    other: Optional[str] = None  # anything that did not fit a section


class Source(BaseModel):
    id: str
    text: str


class ScoringContext(BaseModel):
    """Facts about the employer and publication the scorer needs (not the ad text)."""

    jurisdiction: str = "ZA"  # ZA | EU | US | US-XX
    channel: Optional[Channel] = None
    designated_employer: Optional[bool] = None  # EEA designated employer
    hosted_apply: Optional[bool] = None  # published on a board with its own Apply button
    sources: Optional[list[Source]] = None  # what factual claims must be grounded in


class MetricResult(BaseModel):
    id: str
    dimension: str = ""
    grader: Grader = "deterministic"
    status: MetricStatus = "ok"
    raw: Optional[float] = None  # count, ratio, number, or 0/1 for pass-fail
    normalized: Optional[float] = None  # 0..1 after normalisation
    pass_: Optional[bool] = Field(default=None, alias="pass")
    gate_failed: Optional[bool] = None
    evidence: list[str] = Field(default_factory=list)
    reasoning: Optional[str] = None

    model_config = {"populate_by_name": True}


class DimensionScore(BaseModel):
    score: float
    n: int


class Scorecard(BaseModel):
    spec_version: str
    metrics: list[MetricResult]
    composite: float  # 0..100, always computed
    dimensions: dict[str, DimensionScore]
    standard: "Standard"  # level + plain-language reasons (must_fix / should_fix / could_improve)
    # Benchmark-facing aliases of the standard (kept so Phase 0 reports and tests keep working):
    gates_passed: bool  # == no must_fix reasons
    gate_failures: list[str]  # == must_fix metric ids
    verdict: Literal["publishable", "review", "not_ready"]  # == standard.level

    def metric(self, id: str) -> MetricResult:
        for m in self.metrics:
            if m.id == id:
                return m
        raise KeyError(id)


from .standard import Standard  # noqa: E402  (after Scorecard: standard.py imports MetricResult from here)

Scorecard.model_rebuild()
