# SciDLC plan — scientific development lifecycle for the drafter

## The loop

Every change to the module, from a prompt edit to a new retrieval source, goes through the same loop and leaves a row in the experiment log.

```
Observe ──► Hypothesise ──► Pre-register ──► Experiment ──► Measure ──► Analyse ──► Decide ──► Record
   ▲         (H: "X will      (metric id,      (baseline vs   (full eval   (vs noise    (ship /     (experiments.md,
   │          raise M by Δ")   success Δ,       variant,       set, R reps) floor,       iterate /    frozen outputs)
   │                           what else may    one change)                 cost,        kill)
   └───────────────────────────not regress)                                 regressions)
```

Rules that keep it scientific:

1. **One variable per experiment.** Prompt text, retrieval set, model, effort, lexicon version, rubric: change one.
2. **Pre-register.** Write the hypothesis, the primary metric, the success threshold and the guard metrics *before* running. No post-hoc metric shopping.
3. **Frozen baseline.** Baseline outputs are saved to disk once. Pairwise comparisons always judge against the frozen files, never a regenerated baseline.
4. **Known noise floor.** Run the baseline 3× before the first experiment. A change smaller than the rep-to-rep spread is not a result. **Ship rule (amended 2026-11-04 after EXP-103):** a variant that claims a composite effect must beat the baseline by more than the composite noise floor on validation; a variant that targets one metric ships when that metric moves beyond its own rep-to-rep spread, the composite does not fall, and no must-fix or guard regresses.
5. **Train / validation / test split** of briefs (roughly 50/20/30). Tune on train, pick on validation, report on test. Test is scored every round and is the headline.
6. **Cost and latency are guard metrics**, recorded on every row as absolute numbers (tokens, dollars, seconds) before any percentage.
7. **Kill is a valid outcome.** A source or feature that does not move its target metric beyond noise is removed, and the log says so.

## Phases

### Phase 0 — Instrument before you generate (the scorer benchmark)
No human labelling. The benchmark is built from real ads pulled from the internet and labelled by code and models.

Deliverables: `services/job-ad/metrics/` implementing `metrics.yaml`; lexicon files; judge prompt; `bench/` with a fetcher, a perturbation suite and a runner that writes a versioned `bench/data/out/<version>/` report.

How the scorer is validated without humans:
1. **Deterministic metrics are their own truth.** Word count, readability, salary math, lexicon hits and section presence are verified by unit tests on hand-built fixtures.
2. **Contrastive perturbations.** Every real ad is degraded along one metric at a time (strip pay, widen the range, inflate must-haves, inject masculine-coded words, add an exclusionary phrase, insert a benefit the source never mentioned, delete the application process, bloat sentences). The scorer must score the original above the degraded copy on the targeted metric. Detection rate per perturbation is the headline number for that metric.
3. **Judge agreement.** For LLM-judged metrics, a stronger reference model (`claude-opus-5`) labels once; the production judge (`claude-sonnet-5`) is compared against it (Cohen's κ). Self-consistency: the judge runs three times on the same ad.
4. **Null and oracle probes.** Empty ad, "I don't know", and a confident ad for the wrong role must trip gates and score < 20. The top decile of real ads by composite must contain no gate failures.

Corpus: a few hundred South African ads pulled, without keys, from the public job-board APIs of named SA employers (Workday tenants such as Absa, Old Mutual and FirstRand filtered to South Africa; Greenhouse boards such as Ozow, Luno, OfferZen), configured in `bench/boards.za.json`; a generic JSON-LD extractor for any career-page URL list; keyless public feeds (Arbeitnow, Remotive) for pipeline testing only. Adzuna was tried first and dropped: its API returns 65-word snippets and its landing pages block automated clients. The corpus is frozen as `bench/data/raw/<version>/ads.jsonl` and never regenerated for a version.

Side benefit: the score distribution of real internet ads is the drafter's later target ("score above the median real ad for the same role"), with no labelling.

Exit criteria (all must hold):
- Unit tests: 100% pass.
- Perturbation detection ≥ 0.90 for every deterministic metric and ≥ 0.85 for every judged metric.
- Judge vs reference: κ ≥ 0.7 on every judged metric; grounding and compliance κ ≥ 0.8.
- Judge self-consistency ≥ 0.9 (same label on 3 runs).
- Null probes fail; oracle decile clean.
- Judge cost and latency per ad recorded.

> **Phase 0 status (2026-11-04): closed.** Scorer validated on 40 real SA ads across five role families; 33 of 36 metrics verified, three judged metrics redefined and deferred to Phase 1 for verification (see `bench/experiments.md` → PHASE 0 EXIT). Real-ad baseline composite ≈ 57. Spend ≈ $34.

> **Phase 1 baseline (2026-11-04): frozen at `evals/runs/baseline/`.** Composite 69.5 vs real ads 52.0; beats the real ad 40/40; grounding gate 40/40; publishable 22%. Noise floor 2.7 points (validation, 3 reps): a variant must gain > 3 on validation to count. H1.2 refuted (no hallucination on Opus 5); the weak metrics are facts the briefs lacked, which is Phase 2's job. H1.0: two of three deferred judge metrics verified; `evp.why_this_role` improved to κ 0.58 under rubric 0.5.1 (EXP-102) and is marked advisory. EXP-103 (grade-8 prompt 0.2.0) shipped as the default drafter prompt. Spend ≈ $7.0 + $1.4. Details: `bench/experiments.md` → EXP-101.

### Phase 1 — Baseline drafter, no retrieval
Built 2026-11-04: `job_ad/drafter/` (brief → `JobAd` via structured output on `claude-opus-5`, rubric in the system prompt v0.1.1, no RAG, no revision loop), `job_ad/api/` (headless FastAPI service) and `evals/` (case builder + runner). Ported from TypeScript to Python the same day with exact scorer parity.

**HiringBrief v0.3** (the request contract, `job_ad/drafter/brief.py`; full spec in `04-service-api.md`): title; company {name, about}; location; work_mode (+detail); team {reports_to, size, notes}; responsibilities[]; must_have[]; nice_to_have[]; pay {min, max, currency, period, basis}; benefits[]; process {steps, closing_date, contact}; statements {ee, popia, accessibility}; jurisdiction; designated_employer; hosted_apply; channel. Empty = not provided, and the drafter may not fill gaps.

**Eval cases** come from Phase 0's 40 normalised real ads: each brief is derived from a real ad (facts only, no prose), so every draft has a head-to-head opponent — `beats_real` = draft composite > the real ad's. Splits are deterministic (test / validation / train ≈ 20/20/60%), tags carry role family and thin/rich. The 60-brief hand-written set with trades, healthcare and non-ZA cases is deferred with the v2 corpus.

- **H1.0** (carried from Phase 0) On the first 20 drafts, `evp.team_context`, `evp.why_this_role` and `specific.requirement_traceability` under judge 0.5.0 agree with a claude-opus-5 reference (κ ≥ 0.7 / MAE ≤ 0.2). Until this holds, report them as advisory.
- **H1.1** A rubric-aware prompt with structured output reaches composite ≥ 70 on validation (real SA ads sit at ≈ 57) but fails `honesty.grounding` on > 30% of cases (it will invent benefits). Guard: cost per draft.
- Record: cost, latency, composite distribution, gate-failure reasons. This is the number everything else is measured against.

### Phase 2 — Web enrichment (revised 2026-11-04: the client owns employer data; the service drafts from the contract)
Add an optional, cited web-search step (`options.enrich`): Anthropic's server-side `web_search` tool, restricted to the employer's own domain when `company.website` is given, retrieves public employer context — about, values, locations, published benefits. Retrieved passages become SOURCE blocks alongside the brief; the drafter may use them; the grounding judge checks every claim against brief + sources; the response lists `sources[]` with URLs. Pay and legal statements are never taken from the web.
- **H2.0** With enrichment on, grounding stays at 1.0 on every draft (web facts are cited, not invented) and the judge's unsupported-claim list stays empty.
- **H2.1** `evp.benefits_specific`, `evp.why_this_role` and `structure.sections_present` (company about) rise on briefs that lacked them; composite +3 or more on validation beyond noise. Guard: cost per draft ≤ $0.20 including search; latency ≤ 60 s.
- **H2.2** Recruiter-facing risk check: on the 40 cases, zero web-sourced facts about pay or legal statements appear in drafts (deterministic scan of the ad against the brief for pay figures and statement fields).
- Kill test: if enrichment moves no metric beyond noise on employers with public career pages, it is dropped and the brief stays the only source.

(The earlier plan below — a per-tenant profile store with pgvector — is kept for reference; it is the client's concern now.)

#### Earlier Phase 2 design (profile store; client-side now)
Add the tenant profile store and citation rule.
- **H2.1** `honesty.grounding` gate-pass rate rises from baseline to ≥ 95%; `evp.benefits_specific` and `compliance.ee_statement` pass ≥ 95%. Guard: composite does not fall; context tokens per draft ≤ 4k.
- **H2.2** Retrieval recall@12 on the gold chunk set ≥ 0.9 without a reranker. If not, add a reranker as the next single-variable experiment.
- Kill test: if grounding was already ≥ 95% from the brief alone on realistic briefs, the store still stays for compliance text, but the "paste past ads" ingestion is dropped.

### Phase 3 — Role knowledge for any role (taxonomy RAG)
Add ESCO/OFO retrieval and show the recruiter the matched occupation at brief time.
- **H3.1** On the 30 long-tail briefs (roles outside software/marketing), `specific.responsibility_concreteness` rises by ≥ 0.15 and `specific.requirement_traceability` by ≥ 0.1 over Phase 2. Guard: `clarity.word_count` stays in band; `specific.must_have_count` does not rise.
- **H3.2** Occupation top-1 match ≥ 0.85 on 100 human-coded briefs. Coverage test: sample 50 random ESCO occupations, generate briefs, confirm no gate failures and composite ≥ 70 on ≥ 90% of them. This is the "whatever role" acceptance test.

### Phase 4 — Exemplars, revision pass, cost tuning
Three separate experiments:
- **H4.1 Exemplars**: adding 3 role-family exemplars raises composite ≥ 3 points on validation beyond noise. Guard: pairwise judge sees no cross-case style collapse (set-level diversity metric: mean pairwise similarity of generated ads must not rise above baseline + 10%).
- **H4.2 Revision pass**: one scorecard-guided revision raises publishable rate (gates pass and composite ≥ 75) by ≥ 10 points at ≤ 1.6× cost per draft. Otherwise drop it.
- **H4.3 Effort and model**: `claude-opus-5` at effort `low`/`medium`/`high` and `claude-sonnet-5` at `high` on the same test set. Pick the cheapest configuration whose composite is within noise of the best and whose gate-pass rate is not lower. Caching hit rate (`cache_read_input_tokens`) must be > 0 on repeated tenant drafts; zero means a silent invalidator.

### Phase 5 — Online validation (the only phase that tests the proxies)
Ship behind a flag to a few tenants. Every published ad carries `variant_id` (human-written, AI draft, AI draft edited) and the scorecard at publish time.
- **H5.1** Scorecard composite correlates positively with click-to-apply and qualified-applicant rate across ≥ 200 published ads (Spearman ρ ≥ 0.3). If a dimension shows no correlation, its weight is reduced in `metrics.yaml` and the change logged.
- **H5.2** Recruiter edit distance on AI drafts falls over successive prompt versions.
- **H5.3** Applicant gender share on ads with neutral `inclusive.gender_coding` is closer to the labour-pool share than on masculine-coded ads (replicates Gaucher 2011 in our data).
- A/B where volume allows: same role, two drafts, randomised channel placement; otherwise difference-in-differences against the tenant's own history.

### Ongoing — hillclimb
Once Phases 0–4 are done, improvement is a standing loop: pick the weakest metric on test, hypothesise, change one thing, run, compare to frozen reference, decide. Re-freeze a new reference only when the current one saturates (win rate near 100%), and keep both columns.

## Eval harness contract

```
eval/
  cases/briefs.jsonl          # { id, split, tags:[role_family, seniority, jurisdiction, thin|rich], brief, gold_chunk_ids? }
  cases/labeled-ads.jsonl     # { id, ad, human_scores:{metric_id: value}, rater }
  baseline/results.jsonl      # one row per case per rep: prompt_id, tags, grade:{metric_id: value}, status, model, usage, judge_model, judge_usage, latency_s
  baseline/traces/<id>_rep<k>.json
  v1/ ... vN/                 # + change.md (first line = what changed), change.patch
  _state.json                 # metrics list (headline first), perf_fields, harness_paths
  experiments.md              # the log
```

Runner properties: `--variant`, `--model`, `--reps`, resume on rerun, per-case timeout, served-model assertion (fail if the response's `model` differs from the requested one), failure sidecar `errors.jsonl` so API errors never masquerade as a score of 0.

## Experiment log template (`eval/experiments.md`)

```
## EXP-007  2026-11-20  Exemplars from role family (H4.1)
Change:     retrieve top-3 exemplars by ESCO group + seniority; prompt v0.6 → v0.7 (exemplar block)
Hypothesis: composite on validation +3 beyond noise (noise floor: ±1.8 at 3 reps)
Guards:     cost/draft ≤ $0.09; set diversity ≤ baseline +10%; no gate regressions
Result:     composite 78.1 → 82.4 (+4.3) val; test 77.0 → 80.9; cost $0.071 → $0.084; diversity +6%
Decision:   SHIP. Frozen as reference v7.
Notes:      gains concentrated in evp.* (+0.2) and inclusive.candidate_address; nothing on specificity.
```

## Decision gates summary

| Gate | Criterion |
|---|---|
| Scorer trusted | perturbation detection ≥ 0.9/0.85, judge-reference κ ≥ 0.7 (0.8 for gates), self-consistency ≥ 0.9, null probes fail |
| Baseline frozen | 3 reps run, noise floor recorded |
| Ship a change | primary metric moves beyond noise on test, no guard regression, cost within budget, logged |
| Any-role ready | 90% of 50 random ESCO occupations publishable |
| Pilot ready | publishable rate ≥ 70% on test; compliance gate false-negative rate 0 on the labelled hard negatives |
| Weights trusted | Phase 5 correlation observed on ≥ 200 published ads |

## First two weeks, concretely

1. Scaffold `services/job-ad/metrics` with the deterministic graders and lexicon files; unit tests. Flesch–Kincaid, counts, salary math, candidate-address ratio.
2. Write the judge rubric from `01-job-ad-quality-metrics.md` §4 and `metrics.yaml`; wire `client.messages.parse` with the Zod schema.
3. Pull the corpus, run the perturbation suite and judge agreement. Fix the rubric until the gates hold.
4. Write 60 briefs with splits and tags. Commit `_state.json` with metric ids, headline metric `composite`, and perf fields.
5. Build the Phase 1 drafter, run baseline 3×, freeze. Record the noise floor. Only then start Phase 2.
