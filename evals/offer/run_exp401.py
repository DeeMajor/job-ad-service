"""EXP-401: Sonnet 5 vs Opus 5 drafting the offer letter + explanations on 10 briefs; cross-model judge; deterministic checks.
  .venv/bin/python -m evals.offer.run_exp401 --cap 1.60"""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

import anthropic

from bench.offer.run import compliant_terms
from bench.shortlist.synth import load_briefs
from job_ad.metrics.text import flesch_kincaid_grade
from job_ad.offer.clauses import build_contract_clauses
from job_ad.offer.judge import judge_offer
from job_ad.offer.model import draft_with_model
from job_ad.offer.prompts import render_offer_input
from job_ad.offer.rules import check
from job_ad.offer.terms import OfferRequest

OUT = Path(__file__).resolve().parents[1] / "runs" / "offer-exp401"
ARMS = {"claude-sonnet-5": "claude-opus-5", "claude-opus-5": "claude-sonnet-5"}  # drafter → judge


def numbers(s: str) -> set[str]:
    return {n.replace(",", "") for n in re.findall(r"\d[\d,]*(?:\.\d+)?", s)}


def main(n: int, cap: float):
    client = anthropic.Anthropic(); OUT.mkdir(parents=True, exist_ok=True)
    briefs = load_briefs()[:n]; spent = 0.0; rows = []
    for b in briefs:
        terms = compliant_terms(b["brief"]); terms["clauses"] = {"confidentiality": True}
        req = OfferRequest.model_validate({"brief": b["brief"], "terms": terms, "offer": {"expires": "2026-11-30", "contact": "hr@example.co.za", "documents_required": ["ID", "qualifications"]}})
        comp, _ = check(req); src = render_offer_input(req, build_contract_clauses(req, comp.checked_against.earnings_threshold_applies))
        src_nums = numbers(src)
        for drafter, judge_model in ARMS.items():
            if spent >= cap:
                print("CAP REACHED", spent); break
            t0 = time.time()
            d = draft_with_model(req, client=client, model=drafter)
            j = judge_offer(src, d, client=client, model=judge_model)
            spent += d.meta.cost_usd + j.cost_usd
            letter_grades = [flesch_kincaid_grade(c.text) for c in d.offer_letter.clauses]
            expl_grades = [e.grade for e in d.plain_language if e.explanation]
            row = {"brief": b["prompt_id"], "drafter": drafter, "judge": judge_model, "draft_cost": d.meta.cost_usd, "judge_cost": j.cost_usd, "latency_s": d.meta.latency_s,
                   "faithful": j.faithful, "explanations": j.explanations_total, "unsupported": [c.model_dump() for c in j.unsupported], "claims": j.claims_total,
                   "novel_numbers": sorted(numbers(d.offer_letter.markdown) - src_nums), "letter_grade_mean": round(sum(letter_grades) / len(letter_grades), 1),
                   "expl_grade_le10_share": round(sum(g <= 10 for g in expl_grades) / len(expl_grades), 2) if expl_grades else None, "missing_expl": sum(1 for e in d.plain_language if not e.explanation),
                   "level": d.compliance.level}
            rows.append(row)
            (OUT / f"{b['prompt_id']}-{drafter}.json").write_text(json.dumps({"draft": d.model_dump(mode="json"), "judge": j.model_dump()}, indent=1, default=str))
            print(f"{row['brief']} {drafter:<15} faithful {j.faithful}/{j.explanations_total} unsupported {len(j.unsupported)}/{j.claims_total} novel_nums {row['novel_numbers']} grade {row['letter_grade_mean']} expl≤10 {row['expl_grade_le10_share']} ${d.meta.cost_usd + j.cost_usd:.3f} {time.time()-t0:.0f}s")
        if spent >= cap:
            break
    summ = {}
    for arm in ARMS:
        R = [r for r in rows if r["drafter"] == arm]
        if R:
            summ[arm] = {"n": len(R), "faithful_share": round(sum(r["faithful"] for r in R) / max(1, sum(r["explanations"] for r in R)), 3), "unsupported_total": sum(len(r["unsupported"]) for r in R),
                         "claims_total": sum(r["claims"] for r in R), "briefs_with_unsupported": sum(1 for r in R if r["unsupported"]), "novel_numbers_total": sum(len(r["novel_numbers"]) for r in R),
                         "letter_grade_mean": round(sum(r["letter_grade_mean"] for r in R) / len(R), 1), "expl_le10_mean": round(sum(r["expl_grade_le10_share"] or 0 for r in R) / len(R), 2),
                         "missing_expl": sum(r["missing_expl"] for r in R), "cost_usd": round(sum(r["draft_cost"] for r in R), 3), "judge_cost_usd": round(sum(r["judge_cost"] for r in R), 3), "latency_mean_s": round(sum(r["latency_s"] for r in R) / len(R), 1)}
    summ["spent_usd"] = round(spent, 3)
    (OUT / "summary.json").write_text(json.dumps({"summary": summ, "rows": rows}, indent=1))
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--n", type=int, default=10); ap.add_argument("--cap", type=float, default=1.60)
    a = ap.parse_args(); main(a.n, a.cap)
