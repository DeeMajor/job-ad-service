# What makes a good shortlist ranking — and how we measure it

A ranking is good when the candidates most likely to succeed in **this** role sit at the top, when the ordering can be explained from the job's own requirements and the test, when nothing that the law protects moved anyone up or down, and when a recruiter would rather start from it than from a pile. Everything below is a proxy for those four.

## 1. Outcome metrics (ground truth, arrive late)

| Metric | Definition |
|---|---|
| Interview hit rate | share of the top-N the recruiter actually interviews (recruiter agreement with the ranking) |
| Recruiter re-ordering | how far the recruiter's final order departs from ours (Spearman ρ, Kendall τ) — the live calibration signal |
| Offer / hire position | rank of the candidate eventually hired; a good ranker has them near the top |
| Time to shortlist | minutes from pool closed to shortlist sent |
| Adverse-impact ratio | selection rate of each EE group in the top-N relative to the pool, where the frontend holds that data (the ranker never sees it) — must stay within the 4/5ths band |
| Overrides with a stated reason | each recruiter overrule is a labelled data point on what the ranker missed |

These need the frontend to store, per candidate, the rank we gave, the score and the spec version, and later the recruiter's decision.

## 2. Scoring components (computed at ranking time)

| Component | Default weight | Grader | What it measures |
|---|---|---|---|
| `requirements` | 0.45 | judge (text) + code (declared facts) | share of the job's must-haves with evidence in the candidate's application; each as met / unclear / unmet with a quoted span |
| `skills_test` | 0.40 | code; judge only for rubric items | normalised points, with a per-skill breakdown; free-text/code items graded against their rubric with quoted evidence; time is reported, never scored |
| `nice_to_have` | 0.15 | judge + code | share of nice-to-haves evidenced |
| knockouts | tiering, not weight | code + judge | an inherent requirement (from the brief's justified must-haves or `job.knockouts`) with evidence it is **not** met → tier `does_not_meet_inherent_requirement`; absent evidence → `unclear`, never a knockout |

`score = 100 × Σ weight × component`. Tiers: strong ≥ 75, possible 55–74, weak < 55, plus the inherent-requirement tier. Weights are a hypothesis to be refit against recruiter re-ordering (Phase 4).

Quality rules for the requirement judge (the part that needs most care):
- Evidence must be quoted from the application; "likely has" is `unclear`, not `met`.
- Generic qualifications and years bands count only when the application states them; the judge never infers years from job titles.
- A requirement the brief marks with a justification is weighed as inherent; one without is weighed as preference.

## 3. Constraints that are not metrics (they are rules)

- **Blind input.** No protected attribute or proxy reaches a model: no name, ID, DOB, age, gender, race, photo, address, nationality, marital status, religion, health, language *as identity* (language *proficiency the role needs* is a requirement like any other). Enforced by the contract (no fields) and by redaction of free text.
- **No speed scoring.** Time used is informative to a recruiter and discriminatory as a score.
- **Nobody disappears.** Every candidate submitted is returned, ranked or in `excluded_from_ranking` with the reason.
- **Advisory.** The response is a recommendation with reasons; the decision and its record are the recruiter's (POPIA s71, EEA s6).

## 4. Validating the ranker without human labels (Phase 0)

Same method as the ad scorer: synthetic pools whose correct ordering we control, perturbations with known direction, invariance tests, and a reference model.

| Check | How | Target |
|---|---|---|
| **Monotonicity** | synthetic candidates generated from the 40 real briefs at four designed levels (strong / adequate / weak / missing) on requirements and test; the ranker must order them by design | Kendall τ ≥ 0.9 vs design order per pool |
| **Perturbation sensitivity** | remove the evidence for one must-have → that candidate's requirements component drops; flip a graded item → test component drops by exactly its weight | 100% deterministic items; ≥ 90% judged |
| **Fairness invariance** | the same candidate text with swapped names, gender markers, ages, suburbs, nationalities injected into free text → identical score after redaction (and, with redaction disabled in the benchmark only, measured drift) | Δscore = 0 with redaction; drift reported |
| **Judge agreement** | requirement met/unclear/unmet vs a claude-opus-5 reference on ~40 candidate–requirement pairs | κ ≥ 0.7; evidence quotes present on every `met` |
| **Self-consistency** | same candidate scored 3× | identical tier; score spread ≤ 2 points |
| **Probes** | empty application + full test; perfect application + no test; application that is the job ad pasted back | sensible tiers; the pasted ad scores `unclear` everywhere (no evidence of the person) |
| **Cost** | per candidate, per judged item | ≤ $0.05 per candidate with text; $0 for fully graded tests |

No real applicant data is needed for Phase 0; the first real data arrives with Phase 4's recruiter re-ordering.
