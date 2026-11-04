"""Shortlist contract (docs/shortlist-ranker/01-contract.md).

Blind by construction: there is no field for name, ID, date of birth, age, gender, race, photo, address, nationality,
marital status, religion or health. Free text (cv_text, answers, cover_note) is redacted before any model sees it."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator

from ..drafter.brief import HiringBrief
from .spec import RANKING_SPEC_VERSION, Weights

Fact = Union[bool, str, int, float]


class Answer(BaseModel):
    question: str = Field(min_length=1)
    answer: str = ""


class Application(BaseModel):
    answers: list[Answer] = Field(default_factory=list, description="structured form answers, verbatim")
    cv_text: Optional[str] = Field(default=None, description="plain text; identifiers are redacted before any model sees it")
    cover_note: Optional[str] = None

    def is_empty(self) -> bool:
        return not any(a.answer.strip() for a in self.answers) and not (self.cv_text or "").strip() and not (self.cover_note or "").strip()


ItemType = Literal["mcq", "numeric", "short_text", "code", "other"]


class AssessmentItem(BaseModel):
    item_id: str = Field(min_length=1)
    skill: str = "general"
    type: ItemType = "other"
    max_points: float = Field(gt=0)
    points: Optional[float] = Field(default=None, description="set when the test runner graded the item (deterministic)")
    answer: Optional[str] = Field(default=None, description="with rubric and no points: graded by the judge against the rubric")
    rubric: Optional[str] = None

    @model_validator(mode="after")
    def _points_in_range(self):
        if self.points is not None and not (0 <= self.points <= self.max_points):
            raise ValueError(f"item {self.item_id}: points {self.points} outside 0..{self.max_points}")
        return self

    @property
    def mode(self) -> Literal["graded", "judged", "unanswered"]:
        if self.points is not None:
            return "graded"
        if (self.answer or "").strip() and (self.rubric or "").strip():
            return "judged"
        return "unanswered"


class AssessmentResult(BaseModel):
    assessment_id: str = Field(min_length=1, description="the reusable test's id and version")
    taken_at: Optional[datetime] = None
    time_limit_s: Optional[int] = Field(default=None, ge=0)
    time_used_s: Optional[int] = Field(default=None, ge=0, description="reported to the recruiter, never scored")
    max_points: Optional[float] = Field(default=None, gt=0, description="optional; the sum of item max_points is authoritative")
    items: list[AssessmentItem] = Field(min_length=1)
    flags: list[str] = Field(default_factory=list, description="integrity signals from the test runner; shown, never scored")

    @field_validator("items")
    @classmethod
    def _unique_ids(cls, v):
        ids = [i.item_id for i in v]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate item_id in assessment")
        return v


class Candidate(BaseModel):
    candidate_id: str = Field(min_length=1, description="the frontend's id; the only identifier the service keeps")
    application: Application = Field(default_factory=Application)
    assessment: Optional[AssessmentResult] = None
    declared: dict[str, Fact] = Field(default_factory=dict, description="yes/no or short facts the form asked directly; matched to knockouts/facts without a model")


class Knockout(BaseModel):
    text: str = Field(min_length=1)
    declared_key: Optional[str] = Field(default=None, description="when set, decided from candidate.declared[declared_key] == required_value; else judged from the application")
    required_value: Fact = True


class FactLink(BaseModel):
    """Lets a must-have / nice-to-have be decided from a declared fact instead of the judge."""
    requirement: str = Field(min_length=1, description="exact text of a brief.must_have or brief.nice_to_have")
    declared_key: str = Field(min_length=1)
    required_value: Fact = True


class JobSpec(BaseModel):
    brief: HiringBrief
    knockouts: list[Knockout] = Field(default_factory=list, description="legally inherent requirements; failing one → tier does_not_meet_inherent_requirement (still listed)")
    facts: list[FactLink] = Field(default_factory=list)
    weights: Optional[Weights] = None

    @field_validator("knockouts", mode="before")
    @classmethod
    def _coerce_knockouts(cls, v):
        return [{"text": x} if isinstance(x, str) else x for x in (v or [])]


class RankOptions(BaseModel):
    top_n: int = Field(default=10, ge=1, le=200)
    judge: bool = Field(default=True, description="false = deterministic only (declared facts + graded items); free, judged items left ungraded")
    judge_model: str = "claude-sonnet-5"
    explain_all: bool = Field(default=True, description="false keeps reasons only for the top_n")
    require_assessment: bool = Field(default=True, description="candidates without an assessment are listed in excluded_from_ranking")


class RankRequest(BaseModel):
    job: JobSpec
    candidates: list[Candidate] = Field(min_length=1, max_length=200)
    options: RankOptions = Field(default_factory=RankOptions)

    @field_validator("candidates")
    @classmethod
    def _unique_candidates(cls, v):
        ids = [c.candidate_id for c in v]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate candidate_id")
        return v


class RankJobRequest(RankRequest):
    callback_url: Optional[str] = None


# ---- response

ReqStatus = Literal["met", "unclear", "unmet"]
Source = Literal["answers", "cv_text", "cover_note", "declared", "assessment", "none"]


class RequirementComponent(BaseModel):
    score: float
    weight: float
    matched: int
    unclear: int
    unmet: int
    of: int


class SkillsTestComponent(BaseModel):
    score: float
    weight: float
    points: float
    max: float
    by_skill: dict[str, float]
    judged_items: int = 0
    ungraded_items: list[str] = Field(default_factory=list)
    time_limit_s: Optional[int] = None
    time_used_s: Optional[int] = None
    flags: list[str] = Field(default_factory=list)


class Components(BaseModel):
    requirements: RequirementComponent
    skills_test: Optional[SkillsTestComponent] = None
    nice_to_have: Optional[RequirementComponent] = None


ReasonKind = Literal["knockout_failed", "knockout_unclear", "requirement_met", "requirement_unclear", "requirement_unmet",
                     "nice_to_have_met", "nice_to_have_unclear", "nice_to_have_unmet", "test_strength", "test_gap", "test_item_judged",
                     "test_item_ungraded", "test_missing", "integrity_flag", "redaction"]


class Reason(BaseModel):
    kind: ReasonKind
    requirement: Optional[str] = None
    skill: Optional[str] = None
    evidence: str = ""
    source: Source = "none"
    note: Optional[str] = None


Tier = Literal["strong", "possible", "weak", "does_not_meet_inherent_requirement"]


class RankedCandidate(BaseModel):
    rank: int
    candidate_id: str
    score: float
    tier: Tier
    components: Components
    reasons: list[Reason]
    needs_human_check: list[str]
    redactions_applied: int


class Excluded(BaseModel):
    candidate_id: str
    reason: str


class FairnessCheck(BaseModel):
    ran: bool
    redaction_clean: bool = Field(description="no identifier pattern survived redaction in any text a model saw")
    residual_patterns: int = 0
    note: str = "protected attributes have no field in the contract; free text is redacted before any model call; time is not scored"


class RankMeta(BaseModel):
    spec_version: str = RANKING_SPEC_VERSION
    judge_prompt_version: Optional[str] = None
    pool_size: int
    ranked: int
    judged_candidates: int
    judged_items: int
    judge_model: Optional[str]
    weights: dict[str, float]
    usage: dict[str, int]
    cost_usd: float
    latency_s: float
    fairness_check: FairnessCheck


class RankResult(BaseModel):
    spec_version: str = RANKING_SPEC_VERSION
    ranked_at: datetime
    shortlist: list[RankedCandidate]
    excluded_from_ranking: list[Excluded]
    meta: RankMeta
