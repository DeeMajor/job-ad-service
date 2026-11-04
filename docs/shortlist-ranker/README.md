# Shortlist ranker — planning pack

Goal: given a job and a pool of applicants who have applied and taken the skills test (both handled by the frontend), return a **ranked shortlist in which every score carries reasons** a recruiter can read, verify and overrule.

| Doc | What it answers |
|---|---|
| [01-contract.md](01-contract.md) | The request and response contracts: job, candidates, assessment results, ranking output |
| [02-ranking-metrics.md](02-ranking-metrics.md) | What makes a good ranking, the scoring components, fairness and legal constraints, and how we validate without human labels |
| [03-scidlc-plan.md](03-scidlc-plan.md) | Phases, pre-registered hypotheses, synthetic-pool benchmark, costs |

## What we know and what we assume

Known (from Andile, 2026-11-04): apply and skills test live in the frontend; the test is **timed, reusable and low-data** (small structured results, built for low-bandwidth users). Ranking must show reasons for each score.

Assumptions, stated so they can be corrected:
- The application captures structured answers and/or a CV as text. Where only a CV exists, the service extracts what it needs; it never receives a photo.
- Test items are mostly auto-graded (multiple choice, numeric, short exact answers) with a possible minority of free-text or code items that need judgement.
- The ranking is **advisory**: a recruiter sees it and decides. The service never rejects anyone on its own. (POPIA s71 restricts decisions based solely on automated processing; EEA s6 applies to selection.)
- Pools are tens of candidates per role, occasionally a few hundred — pointwise scoring plus a deterministic sort, no pairwise tournament.

## Design stance

- **Blind by construction.** Names, ID numbers, dates of birth, gender markers, photos, addresses and nationality never reach a model. Candidates are pseudonymised before scoring and re-identified only in the response the recruiter sees.
- **Deterministic where possible, judged where necessary.** Test scores, knockout requirements and nice-to-have matches from structured fields are code. Matching free text (CV, written answers) to the job's must-haves is the judge pattern we validated for the drafter: rubric, quoted evidence, agreement with a stronger model.
- **Not an autonomous agent.** The only place "unknown test format" could justify one is an adapter that normalises a new test's output into the `AssessmentResult` contract; the ranker itself stays a workflow. If tests later include code submissions that must be executed, that becomes one tool-using step, nothing more.
- **Same machinery.** Spec-driven components with weights, a `standard`-style explanation per candidate, SciDLC experiments against a frozen baseline, and a benchmark that needs no human labels (synthetic candidate pools derived from the 40 real job briefs we already hold).
- **Same service.** A `job_ad/shortlist/` package exposing `POST /v1/shortlists/rank` (async, like drafts) in the deployed service; shares the brief contract, judge harness, spend cap and metrics.
