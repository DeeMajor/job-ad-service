"""OfferBrief — the request contract for /v1/offers/* (docs/offer-contract-drafter/01-contract.md).

No field for the employee's name, ID number, address, date of birth, bank details or any protected attribute: the document carries
placeholders the client merges. The one age-related fact the law needs (BCEA s43, no employment under 15) is a yes/no attestation."""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

from ..drafter.brief import HiringBrief

ContractType = Literal["permanent", "fixed_term", "part_time", "temporary", "learnership", "internship"]
Sector = Literal["none", "domestic", "farm", "wholesale_retail", "contract_cleaning", "private_security", "hospitality", "taxi", "forestry", "epwp", "learnership"]
PayPeriod = Literal["hour", "day", "week", "month", "year"]


class FixedTerm(BaseModel):
    end_date: date
    justification: Optional[str] = Field(default=None, description="LRA s198B(3)-(4) reason; required when the term exceeds 3 months and pay is below the earnings threshold")


class Hours(BaseModel):
    per_week: float = Field(gt=0, le=168)
    per_day: Optional[float] = Field(default=None, gt=0, le=24)
    days_per_week: int = Field(default=5, ge=1, le=7)
    schedule: Optional[str] = None
    meal_interval_min: Optional[int] = Field(default=None, ge=0)

    @property
    def daily(self) -> float:
        return self.per_day if self.per_day is not None else self.per_week / self.days_per_week


class PaymentInKind(BaseModel):
    description: str
    value_zar: Optional[float] = Field(default=None, ge=0, description="BCEA s29(1)(j): the value must be stated")


class Pay(BaseModel):
    amount: float = Field(gt=0)
    period: PayPeriod
    currency: str = "ZAR"
    basis: Optional[str] = Field(default=None, description="e.g. basic salary; cost to company")
    pay_day: Optional[str] = None
    method: Optional[str] = None
    overtime_rate: Optional[float] = Field(default=None, ge=0, description="multiple of the hourly wage; BCEA s10(2) floor 1.5")
    other_payments: list[str] = Field(default_factory=list)
    payments_in_kind: list[PaymentInKind] = Field(default_factory=list)


class Leave(BaseModel):
    annual_days: Optional[float] = Field(default=None, ge=0)
    annual_basis: Literal["consecutive_days", "working_days"] = "working_days"
    sick_cycle_days: Optional[float] = Field(default=None, ge=0, description="days per 36-month cycle")
    family_responsibility_days: Optional[float] = Field(default=None, ge=0)
    maternity_months: Optional[float] = Field(default=None, ge=0)
    parental_days: Optional[float] = Field(default=None, ge=0)


class Notice(BaseModel):
    weeks: Optional[float] = Field(default=None, ge=0, description="a single stated period; must be at least the s37 floor for the longest service band")
    statutory_ladder: bool = Field(default=False, description="true = the contract states the s37 ladder (1/2/4 weeks by service) instead of one figure")


class Restraint(BaseModel):
    months: int = Field(gt=0)
    area: Optional[str] = None


class Clauses(BaseModel):
    confidentiality: bool = False
    restraint_of_trade: Optional[Restraint] = None
    ip_assignment: bool = False
    retirement_age: Optional[int] = Field(default=None, ge=50)


class Employer(BaseModel):
    registration_number: Optional[str] = None
    address: Optional[str] = Field(default=None, description="registered/physical address — BCEA s29(1)(a) particular; distinct from place of work")


class Terms(BaseModel):
    contract_type: ContractType
    fixed_term: Optional[FixedTerm] = None
    start_date: date
    probation_months: Optional[int] = Field(default=None, ge=0)
    place_of_work: str = Field(min_length=1)
    various_places: bool = False
    hours: Hours
    pay: Pay
    deductions: list[str] = Field(default_factory=list)
    leave: Leave = Field(default_factory=Leave)
    notice: Notice = Field(default_factory=Notice)
    sector: Sector = "none"
    bargaining_council: Optional[str] = None
    clauses: Clauses = Field(default_factory=Clauses)
    employer: Employer = Field(default_factory=Employer)
    earnings_threshold_override: Optional[bool] = Field(default=None, description="true = treat as above the BCEA s6(3) threshold regardless of pay")
    prior_service: Optional[str] = Field(default=None, description="BCEA s29(1)(p): previous employment that counts towards service, if any")
    documents: list[str] = Field(default_factory=list, description="BCEA s29(1)(q): other documents forming part of the contract")
    employee_is_15_or_older: Optional[bool] = Field(default=None, description="BCEA s43 attestation by the client; no age or date of birth is accepted")

    @model_validator(mode="after")
    def _fixed_term_needs_end(self):
        if self.contract_type == "fixed_term" and self.fixed_term is None:
            raise ValueError("fixed_term contracts need terms.fixed_term.end_date")
        if self.fixed_term and self.fixed_term.end_date <= self.start_date:
            raise ValueError("fixed_term.end_date must be after start_date")
        return self


class OfferTerms(BaseModel):
    expires: Optional[date] = None
    contact: Optional[str] = None
    documents_required: list[str] = Field(default_factory=list)


class OfferRequest(BaseModel):
    brief: HiringBrief
    terms: Terms
    offer: OfferTerms = Field(default_factory=OfferTerms)
