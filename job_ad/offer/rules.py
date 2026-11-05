"""Statutory rule engine. Loads docs/offer-contract-drafter/compliance-rules.yaml and evaluates the terms against it.

Every finding carries the Act section as evidence. Figures with status 'verify' are applied and reported in figures_to_verify.
Nothing here calls a model; nothing here gates — the client decides."""
from __future__ import annotations

import json
import re
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional

import yaml
from pydantic import BaseModel, Field

from ..metrics.text import count_hits
from .terms import OfferRequest, Terms

RULES_PATH = Path(__file__).resolve().parents[2] / "docs" / "offer-contract-drafter" / "compliance-rules.yaml"
LEXICON_PATH = Path(__file__).resolve().parents[1] / "metrics" / "lexicons" / "exclusionary.json"

Severity = Literal["must_fix", "should_fix", "could_improve"]
Level = Literal["compliant", "review", "not_compliant"]

HOURS_WEEKS_PER_YEAR = 52
MONTHS_PER_YEAR = 12
FIXED_TERM_DAYS = 92  # "longer than three months" (LRA s198B(1))


@lru_cache(maxsize=1)
def load_rules() -> dict:
    with open(RULES_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


RULES_VERSION: str = load_rules()["version"]


@lru_cache(maxsize=1)
def _gate_terms() -> list[str]:
    return json.loads(LEXICON_PATH.read_text())["gate"]


@lru_cache(maxsize=1)
def _contextual() -> list[re.Pattern]:
    return [re.compile(p, re.IGNORECASE) for p in json.loads(LEXICON_PATH.read_text())["contextual"]]


class Finding(BaseModel):
    severity: Severity
    rule: str
    message: str
    evidence: str = Field(description="Act section and the figure used")
    clause: Optional[str] = None


class CheckedAgainst(BaseModel):
    rules_version: str = RULES_VERSION
    sector: str
    earnings_threshold_applies: bool
    hourly_equivalent_zar: float
    annual_equivalent_zar: float
    figures_to_verify: list[str]


class Compliance(BaseModel):
    level: Level
    summary: str
    findings: list[Finding]
    checked_against: CheckedAgainst


class Consistency(BaseModel):
    title_matches_ad: bool = True
    pay_in_ad_range: Optional[bool] = None
    employment_type_matches: Optional[bool] = None
    location_matches: Optional[bool] = None
    notes: list[str] = Field(default_factory=list)


# ---- arithmetic

def hourly_equivalent(t: Terms) -> float:
    p, h = t.pay, t.hours
    if p.period == "hour":
        return p.amount
    if p.period == "day":
        return p.amount / h.daily
    if p.period == "week":
        return p.amount / h.per_week
    if p.period == "month":
        return p.amount * MONTHS_PER_YEAR / HOURS_WEEKS_PER_YEAR / h.per_week
    return p.amount / HOURS_WEEKS_PER_YEAR / h.per_week


def annual_equivalent(t: Terms) -> float:
    return hourly_equivalent(t) * t.hours.per_week * HOURS_WEEKS_PER_YEAR


def to_period(hourly: float, period: str, t: Terms) -> float:
    h = t.hours
    return {"hour": hourly, "day": hourly * h.daily, "week": hourly * h.per_week, "month": hourly * h.per_week * HOURS_WEEKS_PER_YEAR / MONTHS_PER_YEAR,
            "year": hourly * h.per_week * HOURS_WEEKS_PER_YEAR}[period]


def consecutive_leave_days(t: Terms) -> Optional[float]:
    lv = t.leave
    if lv.annual_days is None:
        return None
    if lv.annual_basis == "consecutive_days":
        return lv.annual_days
    return lv.annual_days * 21 / (18 if t.hours.days_per_week >= 6 else 15)


def _in_force(effective_from, today: Optional[date] = None) -> bool:
    """True when a figure's effective date has arrived (or it has none)."""
    if not effective_from:
        return True
    try:
        return date.fromisoformat(str(effective_from)) <= (today or date.today())
    except ValueError:
        return False


def _figure(rule: dict, key: str = "min", today: Optional[date] = None):
    """Return (value, evidence, status) for a figure-bearing rule.

    Uses `next` once its effective date has arrived and it has a value. When `next` is due but
    still blank, the current figure is out of date: it is returned with status `verify`, so an
    old rate is never reported as confirmed.
    """
    cur = rule[key] if isinstance(rule.get(key), dict) else {"value": rule.get(key), "status": "confirmed"}
    nxt = rule.get("next") or {}
    has_next = nxt.get("value") is not None or nxt.get("amount") is not None
    if has_next and _in_force(nxt.get("effective_from"), today):
        cur = nxt
    elif not has_next and nxt.get("effective_from") and _in_force(nxt.get("effective_from"), today):
        cur = {**cur, "status": "verify"}
    val = cur.get("value", cur.get("amount"))
    ev = f"{rule['ref']}; {val} {cur.get('unit', rule.get('unit', ''))} effective {cur.get('effective_from', '?')} ({cur.get('source', 'no source')}; status: {cur.get('status', 'verify')})"
    return val, ev, cur.get("status", "verify")


def _by_id(rules: dict, *path: str) -> dict[str, dict]:
    node = rules
    for p in path:
        node = node[p]
    return {r["id"]: r for r in node}


# ---- the check

def check(req: OfferRequest) -> tuple[Compliance, Consistency]:
    R = load_rules()
    t, b = req.terms, req.brief
    F: list[Finding] = []
    verify: list[str] = []

    def add(sev: Severity, rule: str, msg: str, ev: str, clause: Optional[str] = None):
        F.append(Finding(severity=sev, rule=rule, message=msg, evidence=ev, clause=clause))

    pay_rules = _by_id(R, "floors", "pay"); thr_rules = _by_id(R, "floors", "thresholds"); hour_rules = _by_id(R, "floors", "hours")
    leave_rules = _by_id(R, "floors", "leave"); term_rules = _by_id(R, "floors", "termination"); ft_rules = _by_id(R, "floors", "fixed_term")
    other = _by_id(R, "floors", "other"); prob = _by_id(R, "floors", "probation"); parts = _by_id(R, "particulars")

    hourly = hourly_equivalent(t); annual = annual_equivalent(t)

    # earnings threshold (BCEA s6(3)) decides whether hours/overtime sections apply
    thr_val, thr_ev, thr_status = _figure(thr_rules["earnings_threshold"], "value")
    if thr_status != "confirmed":
        verify.append("thresholds.earnings_threshold")
    applies = (annual <= thr_val) if t.earnings_threshold_override is None else (not t.earnings_threshold_override)

    # --- pay
    if t.sector in ("epwp", "learnership") or t.contract_type == "learnership":
        add("should_fix", "pay.nmw_sector_rate", "Learnership / EPWP rates (NMW Act Schedules) are not loaded; the national minimum wage was not applied.", pay_rules["nmw_learnership"]["ref"] + "; status: verify", "remuneration")
        verify.append("pay.nmw_learnership")
    else:
        nmw, nmw_ev, nmw_status = _figure(pay_rules["nmw_hourly"])
        if nmw_status != "confirmed":
            verify.append("pay.nmw_hourly")
        if hourly < nmw - 1e-9:
            add("must_fix", "pay.nmw_hourly", f"Hourly equivalent R{hourly:,.2f} is below the national minimum wage of R{nmw:,.2f}.", nmw_ev, "remuneration")
    if t.pay.pay_day is None:
        add("could_improve", "particulars.pay_frequency", "State the pay day as well as the frequency.", parts["pay_frequency"]["ref"], "remuneration")
    for pik in t.pay.payments_in_kind:
        if pik.value_zar is None:
            add("must_fix", "particulars.payments_in_kind", f"Payment in kind '{pik.description}' has no stated value.", parts["payments_in_kind"]["ref"], "remuneration")
    # deductions (s34) and UIF
    for d in t.deductions:
        if re.search(r"loan|advance|damage|shortage|breakage|uniform|training cost", d, re.I):
            add("should_fix", "pay.no_unlawful_deductions", f"Deduction '{d}' needs the employee's written agreement for a specific debt (BCEA s34(1)).", pay_rules["no_unlawful_deductions"]["ref"], "deductions")
    if t.contract_type != "learnership" and not any("uif" in d.lower() for d in t.deductions):
        add("should_fix", "other.uif_deduction", "UIF contribution (1% employee) is not listed among deductions.", other["uif_deduction"]["ref"], "deductions")

    # --- hours (only when the BCEA sections apply)
    if applies:
        if t.hours.per_week > hour_rules["ordinary_hours_week"]["max"]:
            add("must_fix", "hours.ordinary_hours_week", f"{t.hours.per_week:g} ordinary hours a week exceeds the 45-hour maximum.", hour_rules["ordinary_hours_week"]["ref"], "hours")
        cap = hour_rules["ordinary_hours_day_5days"] if t.hours.days_per_week <= 5 else hour_rules["ordinary_hours_day_6days"]
        if t.hours.daily > cap["max"] + 1e-9:
            add("must_fix", f"hours.{cap['id']}", f"{t.hours.daily:g} ordinary hours a day exceeds the {cap['max']}-hour maximum for a {t.hours.days_per_week}-day week.", cap["ref"], "hours")
        if t.pay.overtime_rate is None:
            add("must_fix", "particulars.overtime_rate", "The rate of pay for overtime is not stated.", parts["overtime_rate"]["ref"], "overtime")
        elif t.pay.overtime_rate < hour_rules["overtime_rate"]["min"]:
            add("must_fix", "hours.overtime_rate", f"Overtime at {t.pay.overtime_rate:g}× is below the 1.5× floor.", hour_rules["overtime_rate"]["ref"], "overtime")
    else:
        add("could_improve", "thresholds.earnings_threshold", f"Annual equivalent R{annual:,.0f} is above the BCEA s6(3) threshold: the hours, overtime, meal-interval and Sunday/public-holiday pay sections do not apply; the contract states the agreed hours instead.", thr_ev, "hours")
    mi = t.hours.meal_interval_min
    if mi is not None and mi < 30:
        add("must_fix", "hours.meal_interval", f"A {mi}-minute meal interval is below the 30-minute minimum (60 unless reduced by written agreement).", hour_rules["meal_interval"]["ref"], "hours")
    elif mi is not None and mi < 60:
        add("should_fix", "hours.meal_interval", f"A {mi}-minute meal interval requires a written agreement (default is 60 minutes).", hour_rules["meal_interval"]["ref"], "hours")

    # --- leave
    cons = consecutive_leave_days(t)
    if cons is None:
        add("must_fix", "particulars.leave", "Annual leave entitlement is not stated.", parts["leave"]["ref"], "leave")
    elif cons < leave_rules["annual_leave"]["min"] - 1e-9:
        add("must_fix", "leave.annual_leave", f"Annual leave of {t.leave.annual_days:g} {t.leave.annual_basis.replace('_', ' ')} is below the 21-consecutive-day floor (15 working days on a 5-day week, 18 on a 6-day week).", leave_rules["annual_leave"]["ref"], "leave")
    sick_floor = 36 if t.hours.days_per_week >= 6 else 30
    if t.leave.sick_cycle_days is not None and t.leave.sick_cycle_days < sick_floor:
        add("must_fix", "leave.sick_leave_cycle", f"Sick leave of {t.leave.sick_cycle_days:g} days per 36-month cycle is below the {sick_floor}-day floor.", leave_rules["sick_leave_cycle"]["ref"], "leave")
    if t.leave.maternity_months is not None and t.leave.maternity_months < 4:
        add("must_fix", "leave.maternity_leave", f"Maternity leave of {t.leave.maternity_months:g} months is below the 4-month floor.", leave_rules["maternity_leave"]["ref"], "leave")
    if t.leave.parental_days is not None and t.leave.parental_days < 10:
        add("must_fix", "leave.parental_leave", f"Parental leave of {t.leave.parental_days:g} days is below the 10-day floor.", leave_rules["parental_leave"]["ref"], "leave")
    if t.leave.family_responsibility_days is not None and t.hours.days_per_week >= 5 and t.leave.family_responsibility_days < 3:
        add("must_fix", "leave.family_responsibility", f"Family responsibility leave of {t.leave.family_responsibility_days:g} days is below the 3-day floor.", leave_rules["family_responsibility"]["ref"], "leave")
    for k, rid in (("sick_cycle_days", "sick_leave_cycle"), ("maternity_months", "maternity_leave"), ("parental_days", "parental_leave"), ("family_responsibility_days", "family_responsibility")):
        if getattr(t.leave, k) is None:
            add("could_improve", f"leave.{rid}", f"{rid.replace('_', ' ').capitalize()} is not stated; the statutory entitlement is written into the contract.", leave_rules[rid]["ref"], "leave")

    # --- termination / term
    if t.contract_type == "fixed_term":
        days = (t.fixed_term.end_date - t.start_date).days
        if days > FIXED_TERM_DAYS and applies and not (t.fixed_term.justification or "").strip():
            add("must_fix", "fixed_term.fixed_term_justification", f"A {days}-day fixed term for an employee below the earnings threshold needs a written justifiable reason (unless the employer has fewer than 10 employees, or fewer than 50 and is under 2 years old).", ft_rules["fixed_term_justification"]["ref"], "term")
    else:
        if t.notice.weeks is None and not t.notice.statutory_ladder:
            add("must_fix", "particulars.notice_or_term", "Notice period is not stated.", parts["notice_or_term"]["ref"], "termination")
        elif t.notice.weeks is not None and not t.notice.statutory_ladder:
            floor = 4
            if t.notice.weeks < floor:
                add("must_fix", "termination.notice_gt_12_months", f"A single notice period of {t.notice.weeks:g} week(s) falls below the 4-week floor that applies after a year of service; state 4 weeks or the statutory ladder.", term_rules["notice_gt_12_months"]["ref"], "termination")
    if t.probation_months is not None and t.probation_months > 6:
        add("should_fix", "probation.probation_reasonable", f"A {t.probation_months}-month probation is long; state the purpose and why the job needs it.", prob["probation_reasonable"]["ref"], "probation")

    # --- particulars that depend on supplied data
    if not t.employer.address:
        add("must_fix", "particulars.employer_name_address", "The employer's address is not stated.", parts["employer_name_address"]["ref"], "parties")
    if t.sector != "none":
        add("should_fix", "sectoral.rates_not_loaded", f"Sector '{t.sector}' has a sectoral determination; its floors are not loaded, so only the national floors were checked.", next(s["instrument"] for s in R["sectoral"] if s["sector"] == t.sector) + "; status: verify", "council_or_sd")
        verify.append(f"sectoral.{t.sector}")
    if t.bargaining_council:
        add("should_fix", "sectoral.council_not_loaded", f"Bargaining council '{t.bargaining_council}' agreement terms are not loaded; only the national floors were checked.", parts["council_or_sd"]["ref"], "council_or_sd")

    # --- other
    if t.employee_is_15_or_older is False:
        add("must_fix", "other.child_labour", "The employee is under 15; employment is prohibited.", other["child_labour"]["ref"], "parties")
    elif t.employee_is_15_or_older is None:
        add("should_fix", "other.child_labour", "The client has not attested that the employee is 15 or older.", other["child_labour"]["ref"], "parties")
    free_text = " ".join(filter(None, [t.pay.basis, t.hours.schedule, t.prior_service, t.fixed_term.justification if t.fixed_term else None, *t.pay.other_payments, *t.deductions, *t.documents]))
    n, hits = count_hits(free_text, _gate_terms())
    hits += [m.group(0) for pat in _contextual() for m in pat.finditer(free_text)]
    n = len(hits)
    if n:
        add("must_fix", "other.no_discriminatory_terms", f"Terms contain wording tied to a listed ground: {', '.join(sorted(set(hits)))}.", other["no_discriminatory_terms"]["ref"])
    r = t.clauses.restraint_of_trade
    if r and (r.months > 12 or not r.area):
        add("could_improve", "other.restraint_reasonableness", "Restraint longer than 12 months or without a defined area is hard to enforce; narrow it to the interest it protects.", other["restraint_reasonableness"]["ref"], "restraint_of_trade")

    # --- roll-up
    order = {"must_fix": 0, "should_fix": 1, "could_improve": 2}
    F.sort(key=lambda f: order[f.severity])
    level: Level = "not_compliant" if any(f.severity == "must_fix" for f in F) else "review" if any(f.severity == "should_fix" for f in F) else "compliant"
    n_must = sum(f.severity == "must_fix" for f in F); n_should = sum(f.severity == "should_fix" for f in F)
    summary = (f"{n_must} must-fix, {n_should} should-fix finding(s). " if F else "All BCEA s29 particulars present and every checked floor met. ") + \
              (f"Hourly equivalent R{hourly:,.2f}; BCEA hours/overtime sections {'apply' if applies else 'do not apply (above the earnings threshold)'}.") + \
              (f" Figures to verify: {', '.join(sorted(set(verify)))}." if verify else "")
    comp = Compliance(level=level, summary=summary, findings=F, checked_against=CheckedAgainst(sector=t.sector, earnings_threshold_applies=applies, hourly_equivalent_zar=round(hourly, 2), annual_equivalent_zar=round(annual, 2), figures_to_verify=sorted(set(verify))))

    # --- consistency with the ad's brief
    C = Consistency()
    if b.pay and (b.pay.min is not None or b.pay.max is not None):
        offered = to_period(hourly, b.pay.period, t)
        lo = b.pay.min if b.pay.min is not None else -1; hi = b.pay.max if b.pay.max is not None else float("inf")
        C.pay_in_ad_range = lo - 1e-6 <= offered <= hi + 1e-6
        if not C.pay_in_ad_range:
            C.notes.append(f"Offered pay is R{offered:,.0f} per {b.pay.period}; the ad said R{b.pay.min or '…'}–R{b.pay.max or '…'}.")
            comp.findings.append(Finding(severity="should_fix", rule="consistency.pay_in_ad_range", message=C.notes[-1], evidence="brief.pay", clause="remuneration"))
    if b.employment_type:
        mapping = {"permanent": {"permanent"}, "fixed_term": {"fixed_term", "contract"}, "contract": {"fixed_term", "contract"}, "part_time": {"part_time"}, "internship": {"internship"}, "learnership": {"learnership"}, "temporary": {"temporary", "fixed_term"}}
        C.employment_type_matches = t.contract_type in mapping.get(b.employment_type, {b.employment_type})
        if not C.employment_type_matches:
            C.notes.append(f"Ad said {b.employment_type}; contract is {t.contract_type}.")
            comp.findings.append(Finding(severity="should_fix", rule="consistency.employment_type_matches", message=C.notes[-1], evidence="brief.employment_type", clause="term"))
    if b.location:
        toks = [w for w in re.findall(r"[a-z]{4,}", b.location.lower()) if w not in ("south", "africa", "province", "western", "eastern", "northern")]
        C.location_matches = any(w in t.place_of_work.lower() for w in toks) if toks else None
        if C.location_matches is False:
            C.notes.append(f"Ad location '{b.location}' does not appear in the place of work '{t.place_of_work}'.")
            comp.findings.append(Finding(severity="should_fix", rule="consistency.location_matches", message=C.notes[-1], evidence="brief.location", clause="place_of_work"))
    if any(f.rule.startswith("consistency.") for f in comp.findings):
        comp.findings.sort(key=lambda f: order[f.severity])
        comp.level = "not_compliant" if any(f.severity == "must_fix" for f in comp.findings) else "review"
    return comp, C
