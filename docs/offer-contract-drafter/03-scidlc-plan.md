# SciDLC plan — offer & contract drafter

Same loop as before: pre-register, one variable per experiment, frozen baseline, log in `bench/experiments.md` (EXP-400 series).

### Phase 0 — rule engine + clause library + synthetic benchmark (free) — BUILT 2026-11-05; EXP-400 passed 1200/1200, 0 false findings; `/v1/offers/check` and `/v1/offers/template` live
Build `job_ad/offer/`: `terms.py` (OfferBrief), `rules.py` (loads `compliance-rules.yaml`, evaluates particulars, floors, threshold switch,
sector selection, consistency), `clauses.py` (clause library with slots), `render.py` (clauses → Markdown with placeholders), `plain.py`
(Flesch-Kincaid per clause, reused from `metrics/text.py`). `POST /v1/offers/check` is this phase's endpoint: free, no model.
Benchmark (free): from the 40 real briefs, generate compliant term sets, then one-defect perturbations — each particular removed, each
floor breached by the smallest step (pay at NMW − R0.01, 46 hours, 20 leave days, 3-week notice after a year, fixed term with no reason,
age 14), threshold edge cases (pay just above/below), sector set with rates missing, consistency breaks (pay outside ad range, different title).
Pre-registered pass: 100% of perturbations detected with the right rule id and severity; 0 false findings on the compliant set; the
response lists every `verify` figure used. Cost $0.
Exit also requires: a labour practitioner's one-time review of the clause library (deliverable 2 in 02) is scheduled — not necessarily done.

### Phase 1 — drafting (paid, small)
Prompt 0.1.0: fill the clause library from terms + brief; write the offer letter; write a plain-language explanation per clause. Model
choice is the first experiment: **EXP-401** Sonnet 5 vs Opus 5 on 10 briefs, judged on `explanation_faithful` and `no_invented_terms`
(Opus reference judge where Sonnet drafts, and vice versa); deterministic readability and the rule engine on every output. Quote ≈ $1.50
for both arms. Ship rule: cheaper model wins unless it loses on `no_invented_terms`; readability target grade ≤ 10 on ≥ 90% of clauses.
Then `POST /v1/offers/draft` + `/v1/offer-jobs`, `?format=markdown`, versions in `/healthz`, deploy through the existing pipeline.

### Phase 2 — real offers, reviewed
First real offers go out only after the clause-library review. The client stores the compliance report alongside the signed document.
- **H2.1** ≥ 95% of generated contracts need no wording change from HR beyond merging placeholders.
- **H2.2** 0 `must_fix` findings reach a signed contract (the client either fixed the term or recorded why not).
- Kill: if HR rewrites clauses on most contracts, the clause library is wrong, not the model.

### Phase 3 — sectors and councils
Load the sectoral determinations the client hires in (rates, hours, leave, notice specifics) as dated tables; bargaining-council agreements
as the client supplies them. Each is its own rules version with the free perturbation benchmark re-run.

### Phase 4 — yearly maintenance
Every March (NMW) and April (threshold): update figures, bump rules version, re-run Phase 0, log. A `verify` figure older than 13 months is
reported as `stale` in every response.

### Guards throughout
- No identity in the service: placeholders only.
- Compliance reported with the Act section, never gated; the client decides.
- Figures dated and sourced; `verify` and `stale` surfaced in every response.
- "Not legal advice" in every response; clause library reviewed by a practitioner before Phase 2.
- No paid run without Andile's yes and a quote; Phase 0 costs nothing.

### First steps
1. Agree 01 and the rule table (02 / yaml) — especially the placeholders decision and the sector list.
2. Build the rule engine and `/v1/offers/check` with the perturbation benchmark (free).
3. Draft the clause library; book the practitioner review.
4. EXP-401 with approval (≈ $1.50).
