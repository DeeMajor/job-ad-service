# Contracts

## Request: `POST /v1/offers/draft` (sync) · `POST /v1/offer-jobs` (async)

```jsonc
{
  "brief": { /* HiringBrief v0.3 — the ad's brief; supplies title, duties, company, location, work mode */ },
  "terms": {
    "contract_type": "permanent",            // permanent | fixed_term | part_time | temporary | learnership | internship
    "fixed_term": { "end_date": "2027-03-31", "justification": "maternity cover for the incumbent" },   // required when fixed_term (LRA s198B(3) reason)
    "start_date": "2026-12-01",
    "probation_months": 3,                    // optional; LRA Sch 8 item 8: reasonable, purpose stated
    "place_of_work": "14 Loop Street, Cape Town",
    "hours": { "per_week": 40, "per_day": 8, "days_per_week": 5, "schedule": "Mon–Fri 08:00–17:00", "meal_interval_min": 60 },
    "pay": { "amount": 18500, "period": "month", "currency": "ZAR", "basis": "basic salary", "pay_day": "25th", "method": "EFT",
             "overtime_rate": 1.5, "other_payments": ["cellphone allowance R500/month"], "payments_in_kind": [] },
    "deductions": ["PAYE", "UIF 1%", "pension 7.5%"],
    "leave": { "annual_days": 15, "annual_basis": "working_days", "sick_cycle_days": 30, "family_responsibility_days": 3, "maternity_months": 4, "parental_days": 10 },
    "notice": { "weeks": 4 },                  // optional; floors from BCEA s37 apply by length of service regardless
    "sector": "none",                         // none | domestic | farm | wholesale_retail | contract_cleaning | private_security | hospitality | taxi | forestry | epwp | learnership
    "bargaining_council": null,               // name, or null
    "clauses": { "confidentiality": true, "restraint_of_trade": { "months": 6, "area": "Western Cape" }, "ip_assignment": true, "retirement_age": 65 },
    "earnings_threshold_override": null       // optional: if the employee earns above the BCEA s6(3) threshold, hours/overtime sections do not apply; derived from pay unless set
  },
  "offer": { "expires": "2026-11-20", "contact": "hr@acme.co.za", "documents_required": ["ID", "qualifications", "banking details"] },
  "options": { "model": "claude-sonnet-5", "score": true, "effort": "medium" }
}
```

No field exists for the employee's name, ID number, address, date of birth, bank account or any protected attribute. The document uses
placeholders the client merges: `{{employee.full_name}}`, `{{employee.id_number}}`, `{{employee.address}}`, `{{employer.signatory}}`,
`{{date_signed}}`. Employer legal details (registered name, registration number, address) come from `brief.company` plus
`terms.place_of_work`; missing ones are reported, not invented.

## Response: `OfferDraft`

```jsonc
{
  "offer_letter": { "clauses": [ { "id": "position", "heading": "Position", "text": "…" }, … ], "markdown": "…" },
  "contract":     { "clauses": [ { "id": "parties", "heading": "Parties", "text": "…", "particular": "s29(1)(a)" }, … ], "markdown": "…",
                    "placeholders": ["employee.full_name", "employee.id_number", "employee.address", "employer.signatory", "date_signed"] },
  "plain_language": { "clauses": [ { "id": "notice", "explanation": "If either of you wants to end the contract, you must give the other …" } ] },   // BCEA s29(3)
  "compliance": {
    "level": "review",                                       // compliant | review | not_compliant — never a gate
    "summary": "All s29 particulars present. Annual leave stated as 15 working days meets the 21-consecutive-day floor. Pay is below the advertised range.",
    "findings": [
      { "severity": "must_fix",  "rule": "nmw.hourly_rate",        "message": "Hourly equivalent R21.35 is below the national minimum wage.", "evidence": "NMW Act s4(1); rate R… effective 2026-03-01 (status: verify)", "clause": "remuneration" },
      { "severity": "should_fix","rule": "consistency.pay_in_ad_range", "message": "Offered R18 500 is below the advertised R20 000–R24 000.", "evidence": "brief.pay", "clause": "remuneration" },
      { "severity": "could_improve", "rule": "plain.clause_readability", "message": "Restraint clause is grade 14; target ≤ 10.", "evidence": "Flesch-Kincaid", "clause": "restraint_of_trade" }
    ],
    "checked_against": { "rules_version": "0.1.0", "sector": "none", "earnings_threshold_applies": true, "figures_to_verify": ["nmw.hourly_rate"] }
  },
  "consistency": { "title_matches_ad": true, "pay_in_ad_range": false, "work_mode_matches": true, "location_matches": true },
  "disclaimer": "Template generated from the agreed terms and checked against the BCEA, NMW Act and LRA rules in compliance-rules.yaml v0.1.0. Not legal advice; have the clause library reviewed by a labour practitioner.",
  "meta": { "model": "claude-sonnet-5", "prompt_version": "0.1.0", "rules_version": "0.1.0", "usage": {…}, "cost_usd": 0.04, "latency_s": 12.1 }
}
```

`?format=markdown` returns the contract alone as `text/markdown` (headers carry `x-compliance-level`), as `/v1/drafts` does for the ad.

## Pre-draft check: `POST /v1/offers/check`
Runs the compliance rules on the brief and terms **without** a model call (free, instant). Lets the client fix a below-floor term before
spending on a draft. Returns the `compliance` and `consistency` objects above.
