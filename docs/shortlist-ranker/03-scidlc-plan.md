# SciDLC plan — shortlist ranker

Same loop as the drafter: pre-register, one variable per experiment, frozen baseline, noise floor, log everything in `bench/experiments.md`.

### Phase 0 — contract + ranker + synthetic benchmark (no model cost for most of it) — BUILT 2026-11-04; deterministic benchmark passed (EXP-300); judged run (EXP-301, ≈ $3) pending approval
Build `job_ad/shortlist/`: redaction, deterministic components (test scoring, declared facts, knockouts, weights, tiers), requirement judge (rubric with quoted evidence), explanation builder (`reasons[]`), pool ranking with explicit tiebreakers (requirements → test → nice-to-have → candidate_id for determinism). Spec file `docs/shortlist-ranker/ranking-spec.yaml` (components, weights, tiers) the way `job-ad-metrics.yaml` works.
Benchmark: synthetic pools from the 40 real briefs (≈ 8 candidates each at designed levels), monotonicity, perturbations, fairness invariance (redaction on/off), probes. Deterministic parts cost nothing; judge checks ≈ 40 pairs × Sonnet + Opus reference ≈ $3.
Exit: τ ≥ 0.9 on every pool; deterministic perturbations 100%; invariance Δ = 0 with redaction; judge κ ≥ 0.7; probes pass.

### Phase 1 — service endpoints + frontend contract
`POST /v1/shortlist-jobs` (async, Redis-backed like drafts) and `GET /v1/shortlist-jobs/{id}`; `POST /v1/shortlists/rank` for small pools. Spend cap and metrics shared. Contract page section for the frontend: what to send, what comes back, how to show reasons and `needs_human_check`, how to record the recruiter's final order and reasons for overrides.
Exit: scenario suite through the tunnel on a synthetic pool; cost per candidate measured.

### Phase 2 — real pools, advisory
First real roles. The frontend shows the ranking next to the raw pool; recruiters decide. Every override is stored with a reason.
- **H2.1** Recruiters interview ≥ 60% from our top-N without reordering more than two places.
- **H2.2** Adverse-impact ratio of our top-N stays ≥ 0.8 for every EE group on which the frontend holds data (the ranker never sees it; the frontend computes it).
- Kill: if recruiters reorder at random against us (ρ < 0.3) the components are wrong, not the weights.

### Phase 3 — judged test items and adapters
If tests include free-text or code items: judge rubric per item type, calibration against Opus, and (only if needed) a sandboxed execution step for code. If a test tool emits a different shape: an adapter into `AssessmentResult`, validated by round-trip on its fixtures.

### Phase 4 — refit weights from recruiter behaviour
With ≥ 200 ranked candidates and recruiter outcomes: fit component weights to recruiter re-ordering, check the fairness constraint still holds, bump the spec version, log it.

### Guards throughout
- Protected attributes never in a model call (tested every run by the invariance check).
- Every candidate returned, every score explained.
- Judge model ≠ reference model.
- Cost per candidate quoted and measured before any paid run; Andile's explicit yes before spend.

### First two weeks
1. Agree the contract (01) with the frontend developer — especially `AssessmentResult`, since the test is theirs to build.
2. Build redaction + deterministic components + explanation builder with unit tests (free).
3. Build the synthetic pool generator and run monotonicity, perturbation and invariance checks (free).
4. Judge rubric for requirement matching; one paid calibration run (≈ $3) with approval.
5. Endpoints, contract page section, deploy via the existing pipeline.
