"""Phase 0 benchmark for the offer & contract rule engine — free, deterministic.

From the 40 real briefs: a compliant term set per brief (0 must/should findings expected), then one-defect perturbations, each of which
must be detected with the pre-registered rule id and severity. Writes bench/data/out/offer-det/summary.json.
  .venv/bin/python -m bench.offer.run"""
from __future__ import annotations

import json
import time
from copy import deepcopy
from pathlib import Path

from job_ad.offer.rules import check, hourly_equivalent
from job_ad.offer.terms import OfferRequest
from bench.shortlist.synth import load_briefs

OUT = Path(__file__).resolve().parents[1] / "data" / "out" / "offer-det"
NMW = 28.79


def compliant_terms(brief: dict) -> dict:
    """Terms that satisfy every rule for this brief: pay inside the ad's range when given, above NMW, below the threshold unless the ad pays more."""
    pay = brief.get("pay") or {}
    period = pay.get("period") or "month"
    lo = pay.get("min"); hi = pay.get("max")
    amount = lo if lo else (hi if hi else 18000.0)
    if period == "month" and amount < NMW * 40 * 52 / 12:
        amount = round(NMW * 40 * 52 / 12 + 500, 2)
    if period == "year" and amount < NMW * 40 * 52:
        amount = round(NMW * 40 * 52 + 6000, 2)
    if period == "hour" and amount < NMW:
        amount = NMW + 1
    return {"contract_type": "permanent", "start_date": "2026-12-01", "probation_months": 3, "place_of_work": (brief.get("location") or "Johannesburg") + ", head office",
            "hours": {"per_week": 40, "per_day": 8, "days_per_week": 5, "schedule": "Mon–Fri 08:00–17:00", "meal_interval_min": 60},
            "pay": {"amount": amount, "period": period, "basis": "basic salary", "pay_day": "25th", "method": "EFT", "overtime_rate": 1.5},
            "deductions": ["PAYE", "UIF 1%"], "leave": {"annual_days": 15, "annual_basis": "working_days", "sick_cycle_days": 30, "family_responsibility_days": 3, "maternity_months": 4, "parental_days": 10},
            "notice": {"statutory_ladder": True}, "employer": {"address": "1 Main Road, " + (brief.get("location") or "Johannesburg")}, "employee_is_15_or_older": True}


PERTURBATIONS = [  # (name, mutate(terms) -> None, expected rule id, expected severity)
    ("pay_below_nmw", lambda t: t["pay"].update(amount=NMW - 0.01, period="hour"), "pay.nmw_hourly", "must_fix"),
    ("hours_46", lambda t: t["hours"].update(per_week=46, per_day=9.2), "hours.ordinary_hours_week", "must_fix"),
    ("day_10h", lambda t: t["hours"].update(per_week=40, per_day=10, days_per_week=4), "hours.ordinary_hours_day_5days", "must_fix"),
    ("overtime_missing", lambda t: t["pay"].update(overtime_rate=None), "particulars.overtime_rate", "must_fix"),
    ("overtime_1_2", lambda t: t["pay"].update(overtime_rate=1.2), "hours.overtime_rate", "must_fix"),
    ("meal_20", lambda t: t["hours"].update(meal_interval_min=20), "hours.meal_interval", "must_fix"),
    ("meal_45", lambda t: t["hours"].update(meal_interval_min=45), "hours.meal_interval", "should_fix"),
    ("leave_missing", lambda t: t["leave"].update(annual_days=None), "particulars.leave", "must_fix"),
    ("leave_14_working", lambda t: t["leave"].update(annual_days=14), "leave.annual_leave", "must_fix"),
    ("leave_20_consecutive", lambda t: t["leave"].update(annual_days=20, annual_basis="consecutive_days"), "leave.annual_leave", "must_fix"),
    ("sick_20", lambda t: t["leave"].update(sick_cycle_days=20), "leave.sick_leave_cycle", "must_fix"),
    ("maternity_3", lambda t: t["leave"].update(maternity_months=3), "leave.maternity_leave", "must_fix"),
    ("parental_5", lambda t: t["leave"].update(parental_days=5), "leave.parental_leave", "must_fix"),
    ("family_2", lambda t: t["leave"].update(family_responsibility_days=2), "leave.family_responsibility", "must_fix"),
    ("notice_missing", lambda t: t.update(notice={}), "particulars.notice_or_term", "must_fix"),
    ("notice_2_weeks", lambda t: t.update(notice={"weeks": 2}), "termination.notice_gt_12_months", "must_fix"),
    ("fixed_term_no_reason", lambda t: t.update(contract_type="fixed_term", fixed_term={"end_date": "2027-06-30"}, notice={}), "fixed_term.fixed_term_justification", "must_fix"),
    ("probation_9", lambda t: t.update(probation_months=9), "probation.probation_reasonable", "should_fix"),
    ("employer_address_missing", lambda t: t.update(employer={}), "particulars.employer_name_address", "must_fix"),
    ("in_kind_no_value", lambda t: t["pay"].update(payments_in_kind=[{"description": "accommodation"}]), "particulars.payments_in_kind", "must_fix"),
    ("deduction_loan", lambda t: t.update(deductions=["PAYE", "UIF 1%", "staff loan repayment"]), "pay.no_unlawful_deductions", "should_fix"),
    ("uif_missing", lambda t: t.update(deductions=["PAYE"]), "other.uif_deduction", "should_fix"),
    ("under_15", lambda t: t.update(employee_is_15_or_older=False), "other.child_labour", "must_fix"),
    ("age_not_attested", lambda t: t.update(employee_is_15_or_older=None), "other.child_labour", "should_fix"),
    ("sector_domestic", lambda t: t.update(sector="domestic"), "sectoral.rates_not_loaded", "should_fix"),
    ("council_set", lambda t: t.update(bargaining_council="MIBCO"), "sectoral.council_not_loaded", "should_fix"),
    ("restraint_24m", lambda t: t.update(clauses={"restraint_of_trade": {"months": 24}}), "other.restraint_reasonableness", "could_improve"),
    ("discriminatory_basis", lambda t: t["pay"].update(basis="basic salary for a young energetic man"), "other.no_discriminatory_terms", "must_fix"),
]


def run() -> dict:
    t0 = time.time()
    briefs = load_briefs()
    false_findings, rows, miss = [], [], []
    for b in briefs:
        base = compliant_terms(b["brief"])
        req = OfferRequest.model_validate({"brief": b["brief"], "terms": base})
        comp, cons = check(req)
        bad = [f for f in comp.findings if f.severity in ("must_fix", "should_fix")]
        if bad:
            false_findings.append({"brief": b["prompt_id"], "findings": [f.rule for f in bad]})
        for name, mutate, rule, sev in PERTURBATIONS:
            t = deepcopy(base); mutate(t)
            try:
                r = OfferRequest.model_validate({"brief": b["brief"], "terms": t})
            except Exception as e:  # noqa: BLE001
                miss.append({"brief": b["prompt_id"], "perturbation": name, "error": str(e)[:100]}); continue
            c, _ = check(r)
            hit = any(f.rule == rule and f.severity == sev for f in c.findings)
            if not hit:
                miss.append({"brief": b["prompt_id"], "perturbation": name, "got": [(f.rule, f.severity) for f in c.findings][:6]})
        # threshold edge: pay just above the threshold must switch hours rules off; just below keeps them on
        hi = deepcopy(base); hi["pay"].update(amount=261748.45 / 12 + 1, period="month"); hi["hours"].update(per_week=50, per_day=10)
        c_hi, _ = check(OfferRequest.model_validate({"brief": b["brief"], "terms": hi}))
        lo = deepcopy(base); lo["pay"].update(amount=261748.45 / 12 - 1, period="month"); lo["hours"].update(per_week=50, per_day=10)
        c_lo, _ = check(OfferRequest.model_validate({"brief": b["brief"], "terms": lo}))
        if c_hi.checked_against.earnings_threshold_applies or any(f.rule.startswith("hours.ordinary") for f in c_hi.findings):
            miss.append({"brief": b["prompt_id"], "perturbation": "threshold_above", "got": "hours rules applied above threshold"})
        if not c_lo.checked_against.earnings_threshold_applies or not any(f.rule == "hours.ordinary_hours_week" for f in c_lo.findings):
            miss.append({"brief": b["prompt_id"], "perturbation": "threshold_below", "got": "46h+ not flagged below threshold"})
        rows.append({"brief": b["prompt_id"], "level": comp.level, "hourly": round(hourly_equivalent(req.terms), 2), "pay_in_ad_range": cons.pay_in_ad_range, "verify": comp.checked_against.figures_to_verify})
    total = len(briefs) * (len(PERTURBATIONS) + 2)
    summary = {"n_briefs": len(briefs), "perturbations": total, "detected": total - len(miss), "missed": miss[:20], "false_findings": false_findings[:20], "n_false": len(false_findings),
               "elapsed_s": round(time.time() - t0, 2), "rows": rows}
    OUT.mkdir(parents=True, exist_ok=True); (OUT / "summary.json").write_text(json.dumps(summary, indent=1, default=str))
    print(json.dumps({k: v for k, v in summary.items() if k != "rows"}, indent=1, default=str))
    return summary


if __name__ == "__main__":
    run()
