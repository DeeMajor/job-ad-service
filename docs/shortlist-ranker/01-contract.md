# Contracts

## Request: `POST /v1/shortlist-jobs` (async) · `POST /v1/shortlists/rank` (sync, small pools)

```jsonc
{
  "job": {
    "brief": { /* HiringBrief v0.3 — the same object the ad was drafted from; must_have[].justification matters here */ },
    "knockouts": ["Code 10 licence with PDP"],            // optional: must-haves that are legally inherent; failing one marks the candidate "does not meet an inherent requirement" (still listed, never deleted)
    "weights": { "requirements": 0.45, "skills_test": 0.40, "nice_to_have": 0.15 }   // optional; defaults from the spec
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
  "options": { "top_n": 10, "judge_model": "claude-sonnet-5", "explain_all": true }
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

Rules: items with `points` are taken as graded; items with `answer` + `rubric` and no `points` are graded by the judge against the rubric (0..max_points, with quoted evidence); `time_used_s` is **reported, not scored** (speed penalises candidates with disabilities or slow connections — the low-data audience). A per-skill breakdown is derived from `skill` tags. Any test the frontend builds later only has to produce this shape; if it cannot, an adapter normalises its output into it.

## Response

```jsonc
{
  "job_id": "…", "spec_version": "0.1.0", "ranked_at": "…",
  "shortlist": [
    {
      "rank": 1, "candidate_id": "c_8f3a", "score": 84.2,
      "tier": "strong",                                       // strong | possible | weak | does_not_meet_inherent_requirement
      "components": {
        "requirements":  { "score": 0.90, "weight": 0.45, "matched": 3, "of": 3 },
        "skills_test":   { "score": 0.78, "weight": 0.40, "points": 31, "max": 40, "by_skill": { "reconciliation": 1.0, "excel": 0.5, "communication": 0.8 } },
        "nice_to_have":  { "score": 0.50, "weight": 0.15, "matched": 1, "of": 2 }
      },
      "reasons": [                                            // ordered: knockouts, then strongest evidence for and against
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
  "meta": { "pool_size": 23, "judged_items": 46, "judge_model": "…", "usage": {...}, "cost_usd": 0.91, "fairness_check": { "ran": true, "invariance_pass": true } }
}
```

Every candidate gets a full explanation (`explain_all`), not only the top N: a recruiter must be able to see why someone ranked 15th.
