# Contracts

## Request: `POST /v1/shortlist-jobs` (async) · `POST /v1/shortlists/rank` (sync, small pools)

```jsonc
{
  "job": {
    "brief": { /* HiringBrief v0.3 — the same object the ad was drafted from; must_have[].justification matters here */ },
    "knockouts": [                                        // optional: legally inherent requirements; failing one marks the candidate "does_not_meet_inherent_requirement" (still listed, never deleted)
      { "text": "Code 10 licence with PDP", "declared_key": "has_code_10_pdp" },   // with declared_key: decided from candidates[].declared, no model; without: judged from the application text
      "Registered with SAPC"                               // a bare string is allowed
    ],
    "facts": [                                            // optional: decide a must-have / nice-to-have from a declared form fact instead of the judge
      { "requirement": "Working knowledge of Sage", "declared_key": "uses_sage", "required_value": true }
    ],
    "weights": { "requirements": 0.45, "skills_test": 0.40, "nice_to_have": 0.15 }   // optional; defaults from ranking-spec.yaml; components a job lacks are dropped and the rest renormalised
  },
  "candidates": [
    {
      "candidate_id": "c_8f3a",                             // the frontend's id; the only identifier the service keeps
      "application": {
        "answers": [ { "question": "Years in a creditors role", "answer": "3 years at Spar DC" } ],   // structured form answers, verbatim
        "cv_text": "…",                                     // optional, plain text; the service redacts identifiers before any model sees it
        "cover_note": "…"                                   // optional
      },
      "assessment": { /* AssessmentResult, below */ },
      "declared": { "has_licence_code_10": true }           // optional yes/no facts the form asked directly; used for knockouts and nice-to-haves without a model
    }
  ],
  "options": {
    "top_n": 10,
    "judge": true,                 // false = deterministic only (declared facts + graded items): free, instant; text requirements come back "unclear", rubric items ungraded
    "judge_model": "claude-sonnet-5",
    "explain_all": true,           // false keeps reasons only for the top_n
    "require_assessment": true     // false ranks candidates without a test on the application alone (test weight redistributed)
  }
}
```

The service never receives, and the contract has no field for: name, surname, ID or passport number, date of birth, age, gender, race, photo, home address, nationality, marital status, religion, health. If any of these appear inside `cv_text` or free-text answers, the redaction step removes what it can detect (ID numbers, dates of birth, email addresses, phone numbers, honorifics, pronoun-bearing phrases) and the recruiter-facing response flags that redaction ran.

## `AssessmentResult` — the test contract the frontend fills

Designed for "timed, reusable, low-data": a result is a list of items, each either already graded (deterministic) or carrying an answer plus rubric (judged).

```jsonc
{
  "assessment_id": "ap-clerk-v3",                           // the reusable test's id and version
  "taken_at": "2026-11-20T09:12:00Z",
  "time_limit_s": 1200, "time_used_s": 1043,
  "max_points": 40,
  "items": [
    { "item_id": "q1", "skill": "reconciliation", "type": "mcq",      "max_points": 2, "points": 2 },
    { "item_id": "q7", "skill": "excel",          "type": "numeric",  "max_points": 3, "points": 0 },
    { "item_id": "q9", "skill": "communication",  "type": "short_text", "max_points": 5, "answer": "I would call the supplier…", "rubric": "Full marks: identifies the discrepancy, proposes a check against the PO, and sets a follow-up date." },
    { "item_id": "q12", "skill": "sage",          "type": "code",     "max_points": 10, "answer": "=VLOOKUP(…)", "rubric": "…" }
  ],
  "flags": ["tab_switch_detected"]                         // optional integrity signals from the test runner; shown, never scored
}
```

Rules: items with `points` are taken as graded; items with `answer` + `rubric` and no `points` are graded by the judge against the rubric (0..max_points, with quoted evidence); items with neither are unanswered (0); with `options.judge=false` rubric items are left out of the denominator and listed under `needs_human_check`. The sum of item `max_points` is authoritative (a differing `max_points` is noted). `time_used_s` is **reported, not scored** (speed penalises candidates with disabilities or slow connections — the low-data audience). A per-skill breakdown is derived from `skill` tags. Any test the frontend builds later only has to produce this shape; if it cannot, an adapter normalises its output into it.

## Response

```jsonc
{
  "job_id": "…", "spec_version": "0.1.0", "ranked_at": "…",
  "shortlist": [
    {
      "rank": 1, "candidate_id": "c_8f3a", "score": 84.2,
      "tier": "strong",                                       // strong | possible | weak | does_not_meet_inherent_requirement
      "components": {
        "requirements":  { "score": 0.90, "weight": 0.45, "matched": 3, "unclear": 0, "unmet": 0, "of": 3 },   // met=1, unclear=0.5, unmet=0; justified must-haves count double
        "skills_test":   { "score": 0.78, "weight": 0.40, "points": 31, "max": 40, "by_skill": { "reconciliation": 1.0, "excel": 0.5, "communication": 0.8 },
                           "judged_items": 2, "ungraded_items": [], "time_limit_s": 1200, "time_used_s": 1043, "flags": [] },
        "nice_to_have":  { "score": 0.50, "weight": 0.15, "matched": 1, "unclear": 0, "unmet": 1, "of": 2 }   // null when the job has no nice-to-haves
      },
      "reasons": [                                            // ordered: knockouts, must-haves (unmet, met, unclear), test strengths/gaps and judged items, nice-to-haves, flags, redaction
                                                              // kinds: knockout_failed | knockout_unclear | requirement_met|unclear|unmet | nice_to_have_met|unclear|unmet | test_strength | test_gap | test_item_judged | test_item_ungraded | test_missing | integrity_flag | redaction
        { "kind": "requirement_met",    "requirement": "Working knowledge of Sage", "evidence": "\"three years capturing supplier invoices in Sage 300\"", "source": "cv_text" },
        { "kind": "requirement_unclear", "requirement": "Two or more years in a creditors role", "evidence": "\"3 years at Spar DC\"", "source": "answers", "note": "role at Spar DC not stated as creditors; recruiter to confirm" },
        { "kind": "test_strength", "skill": "reconciliation", "evidence": "4/4 items correct" },
        { "kind": "test_gap", "skill": "excel", "evidence": "1/3 items correct; q7 (pivot tables) wrong" }
      ],
      "needs_human_check": ["requirement_unclear: creditors experience"],
      "redactions_applied": 2
    }
  ],
  "excluded_from_ranking": [],                                // never silently: candidates with unusable data are listed here with the reason (e.g. no assessment)
  "meta": { "spec_version": "0.1.0", "judge_prompt_version": "0.1.0", "pool_size": 23, "ranked": 22, "judged_candidates": 22, "judged_items": 46, "judge_model": "claude-sonnet-5",
            "weights": {...}, "usage": {...}, "cost_usd": 0.91, "latency_s": 84.2,
            "fairness_check": { "ran": true, "redaction_clean": true, "residual_patterns": 0, "note": "…" } }   // redaction_clean: no identifier pattern survived in any text a model saw
}
```

Every candidate gets a full explanation (`explain_all`), not only the top N: a recruiter must be able to see why someone ranked 15th.

Tiers: `strong` ≥ 75, `possible` 55–74, `weak` < 55; `does_not_meet_inherent_requirement` only from an explicit `job.knockouts` entry with evidence it is **not** met (declared false, or the judge finds an explicit statement). An unclear knockout never demotes; it goes to `needs_human_check`. Order: knocked-out candidates after everyone else, then score, then requirements, test, nice-to-have, candidate_id — deterministic for the same input.

## Endpoints

| Method | Path | Notes |
|---|---|---|
| `POST` | `/v1/shortlists/rank` | synchronous; ≤ 10 candidates when `options.judge` is true (one judge call per candidate with text, ~3–8 s each) |
| `POST` | `/v1/shortlist-jobs` | asynchronous, 202 + `job_id`; body = the same request plus optional `callback_url`; poll `status_url`; result is the `RankResult` |
| `GET` | `/v1/shortlist-jobs/{job_id}` | job status; kept 24 h |

Spend: one Sonnet call per candidate that has text requirements or rubric items (~$0.01–0.03 each); counted against the daily cap. Deterministic-only requests are free.
