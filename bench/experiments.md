# Experiment log — job-ad scorer (SciDLC)

One entry per change. Pre-register hypothesis and success criterion before running. Baselines are frozen per version; never regenerate.

## EXP-000  2026-11-04  Smoke run of the scorer benchmark (offline)
Corpus:     `smoke` — 51 keyless ads (Arbeitnow DE 40, Remotive 11); heuristic normaliser; judge off. Pipeline test only, not a Phase 0 result.
Hypothesis: the deterministic graders detect every deterministic perturbation on ≥ 90% of ads.
Result:     FAIL on first run (7 of 13 perturbation→target pairs). Causes and fixes, all single-variable:
  1. Methodology: ads already at 0 on a metric cannot drop. Detection now conditioned on headroom (original > 0); n_eligible and false-improvement count reported.
  2. `clarity.avg_sentence_length` (document mean) could not detect an injected 80-word sentence. Replaced by `clarity.longest_sentence` (spec 0.1.1).
  3. `clarity.scannability` capped at 0.39 once any paragraph > 80 words, so a second wall of text changed nothing. Replaced cap with × (1 − wall-of-text word share) (spec 0.1.2).
  4. `seo.no_stuffing` absolute count (> 4) failed 75% of real 700-word ads. Now > max(4, 1.5 per 100 words).
  5. `inclusive.candidate_address` sentinel 1000 skewed means; capped at 10, band hi 10.
  6. `inflate_must_haves` added 5 items to lists of 1–2, landing inside the 3–6 band and *raising* the score (26 false improvements). Now always overshoots to ≥ 9.
  7. `inject_masculine_coding` one sentence was diluted in long ads (84%). Now one sentence per 200 words.
  8. `third_person_candidate` swapped only four fields; real ads keep "you" in requirements. Now swaps every text field.
  9. Gate metrics with a gate clause and no band normalised backwards (count 1 → 1.0). Fixed in scorecard.
  10. Lexicon audit on real ads: `inclusive.exclusionary_terms` (a hard gate) fired on "young company", "mature product", "single source of truth"; title check flagged "NDT Technician – Level 2" as an internal grade. Lexicon split into gate / contextual-regex / review-only; level-code regex narrowed to (Grade 7), P3, L5, Band 4 forms.
  11. Heuristic normaliser joined lines with spaces, producing 100-word "sentences" and FK grade 13.6. Joins with newlines now; mean grade 10.3. (LLM normaliser is the real path.)
Decision:   fixes applied; rerun. See EXP-001.
Notes:      real-ad distribution on this corpus is not meaningful (EU pay-disclosure gate fails 78% of German ads by design; heuristic parser leaves sections_present at 0.5). Needs the SA Adzuna corpus + LLM normaliser for Phase 0 proper.

## EXP-001  2026-11-04  Smoke rerun after EXP-000 fixes (offline)
Corpus:     `smoke` (same 51 ads); heuristic normaliser; judge off.
Hypothesis: all deterministic perturbation→target pairs with ≥ 5 eligible ads detect at ≥ 90% with zero false improvements; probes pass.
Result:     PASS. 11/11 evaluable pairs at 94–100%, 0 false improvements. Two pairs (`delete_process`) have only 3 eligible ads because the heuristic parser rarely isolates a process section: insufficient data, not a failure. Probes: empty and "I don't know" blocked at 0; good fixture 100 with gates passing.
Extra fixes during the run: `clarity.scannability` redefined as 1 − wall-of-text word share (the bullet-share × wall product let short prose look like an improvement, 8 false improvements); band lo 0.7 (spec 0.1.3). Bloat paragraph lengthened past 80 words. "under 45" (creditors age analysis) tripped the exclusionary gate: bare under/over N moved to age-context regexes.
Decision:   deterministic half of the scorer is trusted on this corpus. Open: judge agreement and judged perturbations need credentials; real-ad distribution needs the SA Adzuna corpus + LLM normaliser (EXP-002).
Unit tests: 52 passing. Spec 0.1.3, judge prompt 0.1.0.

## EXP-002  2026-11-04  First live run: SA corpus v1, LLM normaliser, judge on (pilot 20 ads)
Corpus discovery (logged because it changed the plan):
  - Adzuna ZA API works with the free key but returns ~65-word snippets; its landing pages return CloudFront 403 "suspicious behaviour" to any non-browser client. Dropped as a text source.
  - Node `fetch` failed against api.adzuna.com with ETIMEDOUT while curl succeeded: Node's happy-eyeballs gives each address 250 ms. Fixed with `net.setDefaultAutoSelectFamily(false)` + IPv4-first DNS in fetch.ts.
  - Replacement: public ATS job-board APIs, no keys. Workday CXS (Absa, Old Mutual, FirstRand; Mimecast/Concentrix/SS&C filtered to SA with the `locationCountry` facet) and Greenhouse (Ozow, OfferZen, Luno, 2U). Workable, BambooHR, Ashby, Lever, SmartRecruiters: no SA employers found on probed slugs.
  - v1 corpus: 141 ads, 10 employers, words p10/p50/p90 = 200/619/1148, 100% full text. Banks dominate (112/141); diversify in v2 with more boards.
Pre-flight fixes before spending:
  - Normaliser schema had 20 nullable fields; API caps union-typed fields at 16 → sentinels ("" / 0 / "unspecified") instead of null.
  - Judge returned 1 for `inclusive.proxy_requirements` meaning "pass" on a COUNT metric. Counts and ratios are now derived in code from lists the judge enumerates (judge prompt 0.2.0). Fixtures: GOOD 100 publishable, BAD blocked with 4 proxies, 5 gate failures.
Hypothesis: on real SA ads the 8 judge-detected perturbations reach ≥ 85% detection; judge κ vs claude-opus-5 ≥ 0.7 (0.8 gates); self-consistency ≥ 0.9; judge cost ≤ $0.05 per ad.
Result:     Run r1 (20 ads, agreement 10, 3 reps). 0 errors. Measured cost $0.033 per judge call (1.6k uncached + 2.7k cached in, 2.9k out), 7.8 judge calls per ad, $0.27 per ad all-in.
  Detection: 16/22 pairs pass. FAIL: third_person_candidate 15% (rendered headings "What you'll do" always add 2 "you"; real bank ads use "you" 2–3× so the ratio saturated at the cap), vague_responsibilities→day_to_day 76%, untraceable_requirements 85% with 3 false improvements ("Chartered Accountant (SA)" IS traceable for bank roles), remove_team_and_work_mode→team_context 45% ("stakeholders" read as team context). Too few: popia (15% of real ads have it), work_mode_clarity (20%).
  Agreement: 6/12 FAIL — concreteness κ 0.37 (direction agrees, magnitude differs; κ on binned ratios too harsh), traceability −0.11 (ads with 1 requirement flip), proxy 0 (reference flagged FAIS credit/criminal checks; those are inherent for regulated roles), why_this_role 0 (rare positives), team_context 0.40, day_to_day 0.62. Self-consistency 70–90% on those six, 100% on the rest.
  Real-ad distribution: median composite 0 because compliance.popia_notice gated 85% of ads — ATS-hosted ads carry POPIA on the portal, not in the text. pay disclosed 0%, process steps 0%, contact 0% (apply button, not text), reading grade 13.6, concreteness 0.30.
  Probes: wrong_role_confident not caught — nothing in the rubric compared title to content.
Decision:   ITERATE (EXP-003). Not a corpus problem; a scorer-definition problem on six metrics, one metric formula, and two "our policy vs the law" gates.

## EXP-003  2026-11-04  Rubric 0.3.0 + spec 0.1.4, rerun on the same 20 ads (run r2)
Changes (one iteration, listed so each can be reverted alone):
  1. `inclusive.candidate_address`: (you-mentions − 2×"the candidate") per 100 words, band lo 1.0; computed on content without our section headings. Was a ratio capped at 10 that saturated for impersonal ads.
  2. `compliance.popia_notice`: gate → ordinary pass/fail in the process dimension. `process.contact_or_link`: not applicable when `hosted_apply` (ATS sources).
  3. `clarity.reading_grade` slack 4 → 7 so grade 13 vs 16 still differ.
  4. New judged metric `structure.title_matches_content` (clarity); wrong-role probe now checks it.
  5. Judge prompt 0.3.0: literal "only if" definitions for concrete, day-to-day, traceable, team context, why-this-role; proxy carve-out for regulatory checks (FAIS, registration); ≤ 3 quotes and ≤ 25-word reasoning per metric (cost).
  6. Perturbations: "Chartered Accountant (SA)" → "Forklift operator licence"; team/work-mode scrub now covers every text field incl. responsibilities.
  7. Agreement stat: ratios compared by MAE ≤ 0.2 (κ kept for pass/fail and counts); identical constant labels = agreement; reference and judge reasoning stored per row.
  8. Runner: outputs per run (`out/v1/r2/`), normalised ads shared across runs.
Hypothesis: on the same 20 ads, all detection pairs with n ≥ 5 pass; agreement failures drop from 6 to ≤ 2; judge output tokens fall ≥ 30%; wrong-role probe caught.
Result:     Run r2. 0 errors. Probes all PASS (wrong-role caught by title_matches_content). Real-ad distribution now meaningful: composite median 57.4 (p10 51, p90 62), gates 100%, 16/20 "regenerate" — that is what real SA bank ads score.
  Detection: 17/22 pass. Still FAIL: third_person_candidate 29% — root cause found: ads with zero "you" have headroom (norm 0.33) but the swap is a no-op; untraceable_requirements 100% but 2 false improvements inside judge noise (traceability self-consistency 60%); team_context 36% — judge counts named functions ("works with Everyday Banking") as team context and a bank ad cannot be scrubbed of its functions. day_to_day 11/13 = 84.6% vs 85%.
  Agreement: 6 → 6 FAIL but closer: title κ 1.0; concreteness MAE 0.06 (spread > 0.15 on 3/10, one bullet on an 8-bullet list); traceability MAE 0.22; why_this_role κ 0.62 (judge missed "own and shape the Islamic banking franchise" — ownership of a portfolio); team_context κ 0.60; proxy κ 0 (1/10: reference flags a 3-year experience *ceiling* as an age proxy); day_to_day κ 0.20 — reference reads "typical day" literally, judge reads "concrete recurring tasks".
  Cost: output tokens rose (2.9k → 3.2k) despite the 25-word cap: the new metric plus quoted lists dominate. Cache-read share fell to 46% at concurrency 6 (cold-start misses).
Decision:   ITERATE once more (EXP-004), then stop tuning on these 20 ads to avoid overfitting the rubric to banking.

## EXP-004  2026-11-04  Rubric 0.4.0 + spec 0.1.5 (not yet run — awaiting budget decision)
Changes:
  1. Removed `specific.day_to_day_present`: inherently ambiguous and redundant with concreteness (metrics doc §5 records why).
  2. `evp.team_context` narrowed to "reporting line stated OR immediate team size stated"; functions/stakeholders no longer count. Makes the perturbation cleanly applicable and should lift κ.
  3. Proxy rubric adds "maximum years-of-experience ceiling"; why_this_role adds "ownership of a named portfolio/franchise counts".
  4. third_person_candidate always injects three third-person sentences (impersonal ads had nothing to swap). untraceable_requirements adds 5 unrelated items instead of 3.
  5. Benchmark tolerances: a judged "false improvement" must exceed 0.1 (judge noise); ratio self-consistency spread ≤ 0.2 (one bullet on a short list).
Hypothesis: on the same 20 ads, every detection pair with n ≥ 5 passes; agreement failures ≤ 2 (expect traceability and proxy to remain marginal at n=10).
Cost to test: ~$6 (judged half only; normalised ads reused). Full v1 (242 ads) ≈ $65 — deferred for budget; a 20-ad diverse-sector sample (~$6) is the proposed alternative.
Result:     Run r3. 1 error in ~600 judge calls (truncated JSON; now retried once). Probes PASS. Real-ad median 57.4 again — stable across r1–r3.
  Detection: 17/19 evaluable pass. third_person_candidate 29% → 100% (fix confirmed). Still FAIL: team_context 45% — judge accepts "a team of Business Development consultants" the person *leads* and "squads/tribes" as team context (Opus does not); untraceable_requirements 94% with 1 false improvement beyond noise.
  Agreement: concreteness now passes (MAE 0.13, 90%). Still FAIL: traceability MAE 0.30 — systematic: Opus maps a commerce FETC to a sales role, Sonnet does not; swings 0↔1 on ads with one requirement. team_context κ 0.40 (same stretch as above). proxy κ 0 and why_this_role κ 0.62 are each ONE disagreement in 10 on metrics with 1–2 positives — κ is not meaningful at that prevalence.
Decision:   two definitions still allow stretch → EXP-006 (judge 0.5.0) written but NOT run: budget cap reached.

## EXP-006  2026-11-04  Judge 0.5.0 / spec 0.1.6 — written, not yet run
Changes:
  1. `evp.team_context`: judge must QUOTE a title for reports_to or a NUMBER for team_size; code decides pass. Teams led, squads, tribes, stakeholders cannot satisfy it.
  2. `specific.requirement_traceability`: denominator is specific must-haves only (tools, certifications, licences, languages, domain skills); generic education levels, experience bands and soft traits excluded — they are measured by must_have_count / years_inflation. Judge outputs {requirement, supporting_responsibility} pairs.
  3. Agreement stat: when a categorical metric has ≤ 2 positives in the sample, report percent agreement (≥ 0.9) instead of κ and label it; κ stays for the rest.
  4. Runner: one retry on malformed judge JSON.
Hypothesis: team_context detection ≥ 85% and κ ≥ 0.7; traceability MAE ≤ 0.2 with consistency ≥ 90%; no regression elsewhere.
Cost to test: ~$6 on the 20 bank ads. Awaiting decision.



## EXP-005  2026-11-04  Diverse-role sample (corpus v1d, 20 ads, 4 roles × 5)
Why:        the 20 pilot ads are all Absa sales roles; a rubric tuned on them may hide blind spots. Budget rules out judging the full 242, so 20 ads across 4 other roles, chosen to stress different metrics.
Sourcing:   trades and healthcare roles were the first choice (inherent physical requirements, professional registration) but are not reachable on free boards: AHRI's Workday site lists 0 roles, Diageo/Philips hold 1–2 SA postings, and the boards that carry millwrights and nurses (PNet, MyJobMag, Careers24) have no public API. Recorded as a known gap; revisit with the DPSA circulars or a licensed feed.
Roles used (all from the existing v1 pull, so no fetch cost): tech/data engineers across Ozow, Old Mutual, FirstRand, OfferZen (long must-have lists, hybrid statements); customer-service agents at FirstRand and Concentrix (shift work, language requirements → proxy test); specialist/admin (OHS consultant, fund administrators, quant risk → regulatory carve-out, concreteness on non-sales work); management (strategic, outcome-heavy bullets → concreteness and why-this-role).
Hypothesis: judge prompt 0.4.0 holds on roles it was not tuned on: all detection pairs with n ≥ 5 pass; agreement failures ≤ 2 on the combined 20-ad agreement sample; language requirements for Dutch/French/German support roles are NOT flagged as proxies (they are inherent).
Cost:       estimated ~$6; measured $9.25 (203 Sonnet calls at $0.038 + Opus ×10 + normalise).
Result:     Run v1d/r1 (judge 0.4.0). 0 errors. 20/23 evaluable detection pairs pass on roles the rubric never saw. Language requirements for Dutch/French/German support roles: 0 proxy flags, protected_grounds pass on all 20 — the inherent-requirement carve-out holds. Agreement: 9/12 pass; team_context κ 1.0 here (vs 0.40 on bank ads), concreteness MAE 0.07.
  FAIL: traceability MAE 0.18 but consistency 80% + 1 false improvement (0.5.0 restructure pending); why_this_role κ 0.40 / consistency 70% → now a quoted-sentence extraction in 0.5.0; work_mode_clarity detection 17% (6 eligible) — ads imply on-site via "office is in Rosebank" and the scrub left it; widened. proxy κ 0 = one disagreement, rare positives.
  Finding 1: compliance.ee_statement as a hard gate blocked 4 of 5 tech-company ads (Ozow, OfferZen, Luno carry no EE statement). The Act requires an EE plan of designated employers, not a statement in the ad. Spec 0.1.7: gate only when ctx.designated_employer is known true; otherwise an ordinary pass/fail in the process dimension.
  Finding 2 (from the empty-ad probe once EE stopped gating): an EMPTY ad scored 43 — metrics that reward the absence of bad things (no buzzwords, no gendered words, no stuffing, nice-to-have split trivially true) add up. Spec 0.1.8 adds `structure.minimum_content` as a hard gate (title, ≥1 responsibility, ≥1 requirement, ≥100 words). Masked until now by the EE gate.
  Real-ad distribution by role (0.4.0, before the EE fix): customer service 65, specialist/admin 54, management 49, tech 21 (blocked by EE). Bank sales (v1) 57.
Decision:   rubric generalises; two judged metrics still noisy. 0.5.0 + spec 0.1.8 written and unit-tested, NOT run.

## Spend to date (from recorded usage, Sonnet $2/$10 per MTok, Opus $5/$25)
| run | judge calls | $/call | total |
|---|---|---|---|
| v1/r1 pilot (0.2.0) | 189 | 0.033 | 7.68 |
| v1/r2 (0.3.0) | 189 | 0.038 | 8.27 |
| v1/r3 (0.4.0) | 187 | 0.037 | 8.00 |
| v1d/r1 (0.4.0) | 203 | 0.038 | 9.25 |
| fixtures/debug | ~12 | | ~0.40 |
| **total** | | | **≈ $33.6** |
Estimates ran ~15% under actual on each run (output tokens grew with the quoted-evidence lists). Any further run: quote the measured $8–9 per 20-ad run, not $6.


## PHASE 0 EXIT  2026-11-04  Decision: close (option 1), verify the remaining three judged metrics inside Phase 1
Verified on real SA ads (v1 bank sales ×20, v1d four other roles ×20; judge 0.4.0, spec 0.1.5):
  - Deterministic metrics: all perturbation checks with ≥ 5 eligible ads detect at 95–100%, zero false improvements.
  - Judged metrics agreeing with claude-opus-5 and self-consistent (≥ 90%): title_matches_content, responsibility_concreteness (MAE 0.07–0.13), pay_context_present, protected_grounds, no_prohibited_requests, benefits_specific, work_mode_clarity, steps_and_timeline, team_context (on v1d). Grounding: 100% detection of injected benefits, 40/40 ads.
  - Inherent-requirement carve-out holds: 0 false proxy flags on Dutch/French/German support roles.
  - Probes: all pass. Real-ad baseline: composite ≈ 57 (bank sales), 49–65 by role on v1d.
Deferred to Phase 1 (judge 0.5.0 / spec 0.1.8 written, 55 unit tests pass, NOT run on real ads):
  - evp.team_context and evp.why_this_role as quoted extractions; requirement_traceability over specific requirements only; structure.minimum_content gate; ee_statement gate only for known designated employers.
  - Verification plan: the first Phase 1 drafter eval runs the judge on every draft; compare those three metrics against a claude-opus-5 reference on the first 20 drafts (≈ $1.50 of Opus calls) before trusting them in the composite. Until then weight them as advisory in reports.
Not done, by budget: full v1 (242 ads) distribution; v2 corpus beyond banking/tech/customer service; trades and healthcare roles (no free source found).
Spend: ≈ $33.6. Rule going forward: quote the measured $8–9 per 20-ad run and get an explicit yes before any paid run.
Artefacts: `services/job-ad/metrics` (scorer), `bench/` (benchmark), `bench/data/raw/{v1,v1d}` (frozen corpora), `bench/data/out/*/r*/report.md` (every run), this log.

# Phase 1 — baseline drafter

## EXP-101  2026-11-04  Baseline drafter, pre-registration (not yet run)
Built:      `services/job-ad/drafter/` — HiringBrief contract, system prompt v0.1.0 (rubric rules, brief-is-the-only-source), `draft()` on claude-opus-5 with structured output, no retrieval, no revision. `eval/` — 40 cases derived from Phase 0's real ads (bank sales 20; tech, customer service, specialist/admin, management 5 each; splits test 8 / validation 8 / train 24; 8 thin briefs). Real-ad composite mean on these 40: 52.
Pre-registered hypotheses (judge 0.5.0, spec 0.1.8):
  H1.0  team_context, why_this_role, requirement_traceability agree with a claude-opus-5 reference on the first 20 drafts (κ ≥ 0.7 / MAE ≤ 0.2). Until then: advisory.
  H1.1  Composite mean ≥ 70 on validation (real ads: 52) — the rubric-in-prompt alone lifts clarity, inclusivity and structure.
  H1.2  honesty.grounding gate FAILS on > 30% of drafts — the model fills gaps (benefits, process, team) the brief leaves empty. This is the Phase 2 motivation; a low failure rate here would weaken the case for company-profile RAG.
  H1.3  beats_real ≥ 80% where gates pass.
  Guards: cost per draft incl. judge ≤ $0.20; latency ≤ 60 s; words within 300–650 on ≥ 80%.
Noise floor: 3 reps on the 8 validation cases before any variant is compared.
Cost quote (to be replaced by measured): draft ≈ 1.5k in + ~4k out on Opus 5 ≈ $0.11, judge ≈ $0.04 → ≈ $0.15 per draft. Pilot 5 test cases ≈ $0.75; all 40 ≈ $6; noise floor (8 × 3) ≈ $3.60.
Update 2026-11-04 (before any run): the module is a headless service (`services/job-ad/api/server.ts`: /healthz, /v1/spec, /v1/scores, /v1/drafts). HiringBrief rewritten as v0.2 — optional fields instead of "" sentinels; added seniority, employment_type, purpose, success_measures, tools, hours, start_date, positions, reference; requirements accept {text, justification}; typed dates and team size; schema_version. Drafter prompt 0.1.1 tells the model to use purpose/success measures/justifications. Eval cases rebuilt (40, real mean 52). 65 unit tests. Hypotheses unchanged.
Result:     (pending approval)

## DECISION  2026-11-04  Port from TypeScript to Python
Why:        Andile asked for the technology best for the solution, not the fleet. The project's centre of gravity is measurement — text metrics, model-graded rubrics, agreement statistics, benchmark analysis, later outcome correlation and RAG — where Python's ecosystem (scikit-learn, pandas, textstat, pgvector clients) replaces code we had hand-rolled (syllables, Cohen's κ). The service layer is the thinnest part; FastAPI + Pydantic also gives OpenAPI for free. The Anthropic SDK is first-class in both.
How:        Full port of scorer, judge, benchmark, drafter, service and eval (~1,500 lines). TypeScript kept in `legacy/ts/` for reference.
Parity:     deterministic scorer on 40 real normalised ads × 37 metrics — 0 differences in status, raw or normalised value, composite or gate failures. Offline smoke benchmark (51 ads, 13 detection rows) — identical table. 56 Python tests (metrics, perturbations, brief, API). The Phase 0 results stand: they measured the rubric and lexicons, which did not change.
Found while porting: the TS brief builder parsed "09/11/26" as September 11 (JS `Date`), wrong for SA day-first dates. Python parses day-first and strips trailing times; eval cases rebuilt.
Toolchain:  Python 3.10.12, `uv` (user install; `python3-venv` absent), anthropic 2.4.0, pydantic 2.14, fastapi 0.162, scikit-learn 1.7. Models use `client.messages.parse(..., output_format=PydanticModel)`.
Commands:   `.venv/bin/python -m bench.run …`, `.venv/bin/python -m evals.build_cases`, `.venv/bin/python -m evals.run_drafter …`, `.venv/bin/uvicorn job_ad.api.app:app`.
EXP-101 (Phase 1 pre-registration) unchanged; still awaiting approval to run.

## EXP-101 result — pilot, 5 test cases (2026-11-04)
Run:        `evals/runs/baseline`, split test, limit 5, 1 rep, claude-opus-5/medium drafter, claude-sonnet-5 judge 0.5.0, spec 0.1.8. 0 errors.
Measured:   **$0.077 per draft incl. judge** (quote was $0.15 — Opus output averaged 959 tokens, far below the 4k assumed); drafter latency 13.8 s; 394 words per ad.
Headline:   composite mean 66.0 (median 66.9) vs real ads 56.7 → beats_real 5/5; gates pass 5/5 (grounding gate passed on every draft); publishable 0/5 (threshold 75).
Weakest metrics are the ones the briefs could not supply (pay, benefits, team, work mode, process steps, POPIA): the real bank ads lacked them, the drafter correctly did not invent them, and they score 0. That is the Phase 2 motivation showing up as *absence* rather than as hallucination.
H1.1 (≥ 70): not met on 5 — 66; close. H1.2 (grounding fails > 30%): NOT supported — 0/5 failed; the brief-is-the-only-source rule held. H1.3 (beats real ≥ 80%): met, 100%. Guards: cost ≤ $0.20 ✓, latency ≤ 60 s ✓, words in band 5/5 ✓.
Decision:   proceed to the full 40 + noise floor at the measured price before judging H1.1; revisit H1.2 — grounding may fail more on rich briefs (more facts to misstate) than on thin ones.

## EXP-101 result — full baseline, 40 cases + noise floor + H1.0 cross-check (2026-11-04)  **BASELINE FROZEN: `evals/runs/baseline/`**
Run:        40 cases × 1 rep (all splits) + validation 8 × 3 reps; claude-opus-5/medium, drafter prompt 0.1.1; judge claude-sonnet-5 0.5.0; spec 0.1.8. 0 errors in 56 drafts + 20 Opus reference judgements.
Spend:      drafts incl. judge $4.79 (56 drafts, $0.087 each — output grew to 1.25k tokens on richer briefs); Opus cross-check ≈ $2.25 (20 reference judgements at Opus rates). Phase 1 total ≈ $7.0 (quote $6; the cross-check was under-quoted at $1.50).
Headline:   composite mean 69.5 (sd 5.7) — test 66.5, validation 70.0, train 70.4; real ads 52.0. beats_real 40/40. Gates pass 40/40 — **honesty.grounding = 1.0 on every draft**. Publishable 9/40 (22%): test 0/8, validation 3/8, train 6/24. Words 521, latency 14 s.
By role:    customer service 74.2 (real 65.0), management 70.4 (49.4), tech 69.8 (20.7 — real tech ads were EE-gated), bank sales 68.6 (56.9), specialist/admin 67.4 (53.5).
Noise floor: validation 8 cases × 3 reps — mean composite spread 2.7 points, max 6.1. **Rule: a variant must beat baseline by > 3 points on validation mean (and not lose on test) to count.**
Hypotheses: H1.1 (≥ 70 on validation): 70.0 — met at the boundary. H1.2 (grounding fails > 30%): REFUTED, 0/40 — the brief-is-the-only-source rule holds on Opus 5; Phase 2's motivation is *missing* facts, not invented ones. H1.3 (beats real ≥ 80%): met, 100%. Guards all met ($0.087 ≤ $0.20; 14 s ≤ 60 s; 40/40 in word band).
H1.0 cross-check (20 drafts vs claude-opus-5): 12/13 judged metrics agree. team_context κ 1.0 and traceability MAE 0.04 — both Phase 0 deferrals now VERIFIED. **why_this_role κ 0.42 FAIL**: in 5/20 the reference accepts "what the candidate will learn / the accreditation they gain" as a role-specific draw and the judge returns "" — the judge is not applying the "learn or grow into" clause. Grounding MAE 0.00.
Weakest metrics (mean normalised): process.steps_and_timeline 0.00, pay.range_present 0.10, pay.context 0.12, popia 0.17, team_context 0.17, benefits_specific 0.23, work_mode 0.25 — all facts the ATS-derived briefs lacked; the drafter correctly did not invent them. Then reading_grade 0.54 (drafts read at grade ~11), concreteness 0.55, why_this_role 0.60.
Decision:   Phase 1 baseline established and frozen. Next, each one variable, each vs this baseline:
  EXP-102 judge 0.5.1 — why_this_role rubric: learning/accreditation/qualification gained counts as a draw; re-score the 20 cross-check drafts with Sonnet only (Opus labels already stored) ≈ $0.70. Target κ ≥ 0.7.
  EXP-103 drafter prompt 0.2.0 — reading level: short words, grade-8 target; validation 8 cases ≈ $0.70; target reading_grade norm 0.54 → ≥ 0.8 with composite +3 beyond noise and no gate regressions.
  Phase 2 (company-profile retrieval) is what lifts the seven "missing fact" metrics; nothing in the prompt can.


## EXP-102  2026-11-04  Judge 0.5.1 — why_this_role rubric (pre-registered, running)
Change:     one field description: learning, training, accreditation or a qualification gained count as a role-specific draw, equal to ownership. Nothing else in the judge changed.
Hypothesis: on the 20 cross-check drafts, why_this_role agreement with the stored claude-opus-5 labels rises from 75% (κ 0.42) to ≥ 90% (κ ≥ 0.7); no other judged metric regresses.
Cost:       Sonnet only (Opus labels reused) ≈ $0.70 (measured ≈ $0.70).
Result:     why_this_role 75% → 85%, κ 0.42 → 0.58. Improved, target NOT met. Remaining 3/20: the reference reads an ownership/authority sentence where the judge sees "general role description" — Sonnet is systematically stricter than Opus on this metric. Other metrics unchanged except concreteness MAE 0.07 → 0.16 (still ok; two different Sonnet runs, i.e. run-to-run noise, since that field's rubric did not change).
Decision:   KEEP 0.5.1 (strictly better, no regressions). Do not iterate the wording again — two rounds have shown diminishing returns and the risk is tuning to 20 drafts. Record why_this_role as **advisory** (κ 0.58, judge stricter than reference) in the spec notes; revisit when Phase 2 briefs carry `purpose` and positives stop being rare.

## EXP-103  2026-11-04  Drafter prompt 0.2.0 — reading level (pre-registered, running)
Change:     one bullet of the drafter system prompt: Grade 8 target, sentences under 20 words, everyday-word substitutions, avoid -tion/-ment nouns. Variant `v1-grade8`, validation split (8 cases), vs frozen baseline (validation mean 70.0, noise floor 2.7).
Hypothesis: clarity.reading_grade normalised 0.54 → ≥ 0.8; validation composite +3 or more beyond noise; no gate regressions; word count stays in band; concreteness does not fall (shorter words must not mean vaguer bullets).
Cost:       8 drafts ≈ $0.70 (measured $0.68).
Result:     reading_grade normalised 0.65 → 0.82 on validation (baseline validation was 0.65, not the 0.54 all-split figure); raw Flesch–Kincaid grade 12.2 → 9.9. Target MET. Composite 70.0 → 70.1 (+0.7 paired per case, 6/8 wins) — inside the 2.7 noise floor, target NOT met. Gates 8/8, words 511 (in band), concreteness 0.55 vs 0.55–0.60 (unchanged), publishable 4/8 vs 3/8 (noise). Cost $0.085/draft. Confound: judge was 0.5.1 here vs 0.5.0 on baseline; only why_this_role's rubric differs, so the composite effect is ≤ 1 metric.
Reading:    the change does exactly what it targets with zero collateral damage, but one metric out of seven in a 0.20-weight dimension can move the composite by at most ~0.5 points — the pre-registered "+3 composite" target was unachievable for any single-metric change. The ship rule ("beat baseline by > 3 on validation") was written for composite-level changes and is the wrong test here.
Decision:   PROPOSED (awaiting Andile): adopt 0.2.0 as the default drafter prompt, and amend the ship rule — a variant ships if (a) its targeted metric moves beyond that metric's own rep-to-rep spread AND (b) composite does not fall AND (c) no gate or guard regresses; the "+3 composite" bar stays for changes that claim a composite effect. Readability has independent evidence behind it (grade-8 target, mixed first-language audience), so a free, regression-free gain is worth shipping.
Spend to date (project): Phase 0 ≈ $33.6 · Phase 1 baseline ≈ $7.0 · EXP-102/103 ≈ $1.4 → **≈ $42**.

## DECISIONS  2026-11-04  (Andile)
1. Adopt drafter prompt **0.2.0** (grade-8 reading level) as the default. EXP-103 evidence: reading grade 12.2 → 9.9, no regressions, composite unchanged within noise.
2. Amend the ship rule: single-metric variants ship on their own metric's movement beyond its noise, provided composite does not fall and nothing must-fix regresses; the "+3 composite" bar applies to composite-level claims.
3. **Drop the gate model from the response.** "I don't like having a gate." Spec 0.1.9: the composite is always computed; the scorecard carries a `standard` — level (publishable / review / not_ready), one-line summary, and reasons graded must_fix / should_fix / could_improve, each with a plain-language fix and quoted evidence. The must-fix set equals the old gate set, so nothing is checked less strictly; it is reported usefully instead of as "blocked, 0". Legacy fields `verdict`, `gates_passed`, `gate_failures` are kept as aliases for the benchmark. Completeness check renamed `will_block` → `would_be_not_ready`.
   Effect on frozen numbers: none for the Phase 1 baseline (all 40 drafts had no must-fix reasons). Phase 0 real-ad distributions that reported "blocked" ads at composite 0 would now show their actual composites; the detection and agreement results are unaffected (they compare normalised metric values, not composites).

## DECISION  2026-11-04  HiringBrief v0.3 — four required fields + refuse-before-spend
Andile: "Should we just rather make the most needed fields required?" Split by consequence: fields whose absence always yields not_ready (responsibilities ≥ 1, must_have ≥ 1) become required alongside title and company.name — a 422 beats paying for an unpublishable draft. Fields whose absence only lowers the score stay optional (some are legitimately unavailable; filler is worse than absence; different intake paths fill gaps differently) and are guided by /v1/briefs/check. New `options.allow_not_ready` (default false): the service refuses a draft the completeness check predicts not_ready (designated employer without EE statement) with a structured 422 before any model call. All 40 eval cases satisfy v0.3; no re-run needed.

## DECISION  2026-11-04  Scope: a drafting service that expects the data in the contract; Phase 2 = web enrichment
Andile: employer profiles/persistence are the frontend's job; the service drafts from the HiringBrief. Phase 2 (company-profile RAG inside the service) is replaced by an optional, cited **web enrichment** step. Rule: public employer context only (about, values, locations, published benefits); pay and legal statements never from the web; every web fact cited and returned in `sources[]`. Pre-registration: EXP-201 (to follow once built).

## EXP-201  2026-11-04  Web enrichment v0.1 (pre-registered, NOT run — awaiting approval)
Built:      `job_ad/drafter/enrich.py` — one claude-sonnet-5 call with the server-side `web_search_20260209` tool (≤ 3 searches, `allowed_domains` = employer site when `company.website` is given), structured `EmployerFacts`, pause_turn resumed ≤ 3×; facts that look like pay or legal statements are dropped; on-domain facts preferred. Facts → SOURCE blocks appended to the drafter input (prompt 0.2.1 = 0.2.0 + a sources rule) and to the grounding judge's context. API: `company.website`, `options.enrich`, `options.max_searches`; response `sources[]`, `meta.enrichment`.
Hypotheses (variant `v2-enrich`, validation 8 + test 8, vs frozen baseline):
  H2.0  honesty.grounding = 1.0 on every enriched draft; unsupported-claim list empty (web facts are cited, not invented).
  H2.1  evp.benefits_specific and structure.sections_present (company about) rise beyond their own noise on employers with public career pages; composite +3 or more on validation beyond the 2.7 floor.
  H2.2  Zero pay figures or legal statements in any enriched draft that are not in the brief (deterministic scan).
  Guards: cost per draft ≤ $0.20 incl. search; latency ≤ 60 s; words in band; no must-fix regressions.
Smoke first: one enriched draft on a known employer (Absa, website absa.co.za) to confirm the tool shape, ≈ $0.15.
Smoke result (2026-11-04): the pipeline ran end to end but every web search returned "server tool use limit exceeded"; 0 facts; the drafter fell back to brief-only (prompt 0.2.0), grounding 1.0, no pay/legal leak — the safe failure mode works. Enrichment call: 3 searches attempted, 55 s, ~41k cached input tokens read across the model's retries (≈ $0.03). Diagnosis (3 calls, ~$0.70 — more than the $0.15 quoted for the smoke; reported): web search is enabled and works. All three variants (with/without domain filter, with/without structured output) ran their 3 searches successfully and hit the right pages (absa.co.za/about-us, the employee-benefits page). The fault is the tool version: `web_search_20260209` (dynamic filtering) runs search inside a code sandbox; once `max_uses` was spent the model's filtering code kept calling search, got "Server tool use limit exceeded", and looped on retries (bash sleep 5/30/60/90), ending with zero facts and 67k–121k uncached input tokens per call. The basic `web_search_20250305` returned results directly in one pass in the direct test. Fix: enrich.py uses the basic tool (prompt 0.1.1 also tells the model it has a fixed search budget and must not retry errors). Lesson for the log: a server tool's "latest" version is not automatically the right one for a tightly capped, single-pass call.
Smoke re-run (basic tool, max_tokens 2500): 3 searches, 12 facts from absa.co.za (about, purpose, values, HQ address, footprint, Top Employer awards), 17 s, ≈ $0.05 for enrichment (2.9k cached + 1.5k out + 3 searches); whole enriched draft ≈ $0.14. Draft used prompt 0.2.1: the company "about" was rebuilt from the cited sources (purpose and five values, verbatim); grounding 1.0 with 0/8 unsupported against brief + web sources; no pay, no legal text from the web (ee_statement identical to the brief's). Composite 66.2 vs 67.6 brief-only on the same case — enrichment filled the about section but this bank brief already lacked pay/process, so the composite barely moves; as predicted in the caveat. Benefits: none found on absa.co.za's employee pages (the model correctly excluded workplace-banking *product* pages). Tool shape confirmed; EXP-201 can run.
Cost:       16 enriched drafts ≈ 16 × ($0.09 + ~$0.05) ≈ $2.30; with the smoke ≈ $2.50.
Caveat:     the eval briefs were derived from real ads, so most already carry the employer's "about" text; the lift will show mainly on benefits and on briefs whose about is thin. Real client briefs will be thinner than these, so this under-states the production effect.

## DECISION  2026-11-04  Enrichment off for now; EXP-201 deferred
Andile: "turn off enrichment for now." Smoke proved the tool shape and the safety rule; the 16-draft experiment is deferred (≈ $2.30 when wanted). Enrichment is now a deployment switch (`ENRICH_ENABLED`, default false); `/healthz` reports `features.enrichment`; `enrich:true` while off → 400 `enrichment_disabled`. Code stays in place; the contract page documents it as "currently off".

## DECISION  2026-11-04  Intake endpoint: free text → HiringBrief
Andile: "the front will just have the user describing the role and then the draft service should draft the ad." Built `POST /v1/briefs/extract` (job_ad/drafter/extract.py): one Sonnet call, structured output with sentinels, converted to a HiringBrief; verbatim, nothing invented; returns the brief (or null + missing_required when duties/requirements are absent), brief_partial for form pre-fill, up to five questions for the most valuable gaps, and the completeness check. Flow: describe → extract → confirm → draft. 72 tests. Not yet exercised live (≈ $0.02 per call).

## DECISION  2026-11-04  Response carries both structure and rendered text
Andile asked whether the draft should come back as a written (Markdown) string rather than JSON. Decision: both. `ad` (JSON) stays canonical — scoring, evidence pointers, per-field editing and board publishing depend on it; `rendered.markdown` and `rendered.text` are derived deterministically for display; `?format=markdown` returns text/markdown only, with composite/standard/version headers. 73 tests.

## SCENARIOS  2026-11-04  Live run against the local service (Andile: "run the tests yourself, have different scenarios")
Free paths (all correct): healthz/spec; completeness on a full brief (ceiling 100, no suggestions) and a four-field brief (ceiling 61.4; top suggestions location, accessibility, benefits, reporting line); 422 on an empty brief naming all four required fields; 422 `brief_not_ready` for a designated employer without an EE statement; 400 `enrichment_disabled`; deterministic score of a bad ad → composite 32.5, not_ready, three must-fix reasons with plain-language messages; 422 on a too-short description.
Paid (≈ $0.35 total):
  - extract, full description → valid brief, ceiling 91: title, 3 duties, 2 must-haves, 1 nice-to-have, pay R18k–R22k/month with basis, reports-to + team size 3, onsite, hours, 3 benefits, process steps, closing date 2026-11-30; 5 sensible questions. 10.5 s.
  - extract, thin receptionist description → valid brief; must_have = ["Friendly"] (verbatim from "friendly receptionist" — honest, but a soft trait as the only requirement); questions correctly ask for pay, employment type, qualifications, reporting line, process. 4.4 s.
  - draft from the extracted brief → composite 82, publishable, grounding 1.0 (0/11 unsupported), 193 words (word_count norm 0.47 — the drafter stays short on an 11-fact brief; the 300-word floor costs points but padding would be worse), rendered Markdown correct. 29.6 s; drafter ≈ $0.015 + judge.
  - draft, four-field driver brief, ?format=markdown → text/markdown, x-composite 57.5, x-standard not_ready (composite < 60, no must-fix).
Finding (fixed): the driver draft's location read "Cape Flats, Cape Town"; the brief said only "Cape Flats". The judge passed it (0/4 unsupported): world-knowledge elaboration accepted as support. Drafter prompt 0.2.2 (default; 0.2.3 with sources) forbids adding geographic/world-knowledge detail; judge prompt 0.5.2 defines such elaboration as unsupported. Verified live (≈ $0.12): with drafter 0.2.2 the driver draft leaves location empty and contains no "Cape Town" (grounding 1.0, 0/3). Judge 0.5.2 scoring the OLD leaky ad against the brief now reports 2/5 unsupported — the city qualifier and an embellished licence justification ("so you can legally drive the delivery vehicle") that 0.5.1 had also accepted. Judge 0.5.2 is not yet re-verified against the stored Opus labels (≈ $0.70 when wanted); the change tightens grounding only, so the risk is false positives on legitimate paraphrase — watch the grounding rate on the next eval.
Observation (not changed): extraction will accept a soft trait as the sole must-have because it is in the text; the completeness/traceability metrics and the questions surface it. Consider a "requirements look like traits only" hint later.

## DECISIONS  2026-11-04  Deployment shape
Andile: internal service, no API-key auth; async drafts; Docker; CI builds the image (no test step); GitHub holds the config. Built: `POST /v1/draft-jobs` + `GET /v1/draft-jobs/{id}` (bounded in-process pool, Redis-backed state with TTL 24 h or in-memory fallback, restart marks in-flight jobs failed, best-effort callback); daily spend cap from token-usage estimates (`DAILY_SPEND_CAP_USD`, 429 when reached); `/metrics` (Prometheus) and JSON logs stamped with spec/prompt versions; Dockerfile (python:3.10-slim, uv, non-root, healthcheck) + docker-compose (api + redis, bind address = VPN IP); GitHub Actions builds and pushes `ghcr.io/deemajor/job-ad-service` on push to main (tags latest, sha-*, v*); repo secret ANTHROPIC_API_KEY and variables ALLOWED_ORIGINS, ENRICH_ENABLED, MAX_CONCURRENT_DRAFTS, DAILY_SPEND_CAP_USD, LOG_LEVEL, PORT set via gh. Host details to follow from Andile.

## DEPLOYED  2026-11-04  Contabo VPS, internal, Docker
Host: existing Contabo VPS (Ubuntu 24.04, 8 vCPU/24 GB) that runs the frontend PM2 apps (findjobsza, justibly, theaisle) + nginx + Postgres. Contabo API route abandoned (API password needs an emailed "Send Link" step); SSH with a one-time root password installed a dedicated ed25519 key (~/.ssh/jobad_deploy). Installed Docker 29 + compose v5 from Docker's apt repo. `/opt/job-ad-service/` holds compose + .env; `ghcr.io/deemajor/job-ad-service:latest` (= sha-a9c3f0f) pulled with a read-only package token; API bound to 127.0.0.1:4310 (verified unreachable from the internet); Redis-backed jobs; healthz OK; deterministic scoring OK from the host. No paid call made on the host yet. Runbook: docs/job-ad-drafter/05-deployment.md.
