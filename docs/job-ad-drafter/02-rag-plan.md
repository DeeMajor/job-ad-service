# RAG plan for the job-ad drafter

> **Scope change 2026-11-04 (Andile).** The service is a *drafting service that expects the data in the contract*. Employer profiles, persistence and intake belong to the client (the frontend), which supplies employer facts in the HiringBrief. The per-tenant profile store described below is therefore **out of scope for this service**; it remains a reasonable design for the client side. Phase 2 for the service becomes **web enrichment**: an optional, cited web-search step that strengthens the ad with public employer context and role knowledge. Hard rule: the web may supply public employer context (about, values, locations, benefits the employer itself publishes) — **never pay, never legal statements** (EE, POPIA, accessibility); those come only from the brief. Every web-sourced fact is cited and returned in `sources[]` for the recruiter to confirm.


## Why retrieval at all

A model can write a fluent ad for any role from nothing. The failures are not fluency failures; they are **grounding** failures (invented benefits, wrong EE statement, wrong hybrid policy), **specificity** failures on long-tail roles (what does a boilermaker or a claims assessor actually do day to day), **compliance** failures (jurisdiction rules the model half-remembers), and **style drift** from the company's voice. Each failure maps to a knowledge source. If a source does not move a scorecard metric in the Phase 2–3 ablations, it is dropped.

| Failure the scorer catches | Source that fixes it | Scorecard metrics it should move |
|---|---|---|
| Hallucinated company facts | Company profile store (per tenant) | `honesty.grounding`, `evp.benefits_specific`, `compliance.ee_statement`, `compliance.popia_notice` |
| Vague or wrong responsibilities for unusual roles | Occupation taxonomy (ESCO; OFO for South Africa; O*NET for US) | `specific.responsibility_concreteness`, `specific.requirement_traceability`, `seo.title_matches_taxonomy`, `specific.years_inflation` |
| Compliance errors | Curated jurisdiction rule files | all `compliance.*`, `inclusive.proxy_requirements` |
| Generic voice, weak EVP | Exemplar ads: the tenant's past high-scoring ads, plus a global library of ads that scored ≥ 85 and performed well | `evp.*`, `inclusive.candidate_address`, composite |
| Unrealistic or missing pay | Salary benchmarks (tenant-supplied or licensed; optional) | `pay.range_present`, `pay.range_width` |

## Knowledge sources

### 1. Company profile (per tenant) — the grounding store
Structured fields plus free text, each chunk tagged with `tenant_id`, `source_type`, `effective_from`:
- About, mission, values (short)
- Benefits list, each benefit as its own chunk with eligibility
- Locations, work-mode policy per location
- EE / affirmative-action statement, designated-employer flag
- POPIA notice text or link
- Hiring process template (rounds, typical timeline)
- Past published ads (chunked by section) with their scorecard and outcome metrics attached

Ingest: a tenant onboarding form plus a "paste your last five ads" box. Everything the drafter may state as fact must come from here or the brief.

### 2. Occupation taxonomy — the "whatever role" store
- **ESCO** (EU, free, 3,000+ occupations, 13,000+ skills, alt labels, task descriptions). Primary.
- **OFO** (South African Organising Framework for Occupations). Needed for SA employers' EE and skills-development reporting, and for local title conventions. Map ESCO ↔ OFO where codes align; store both.
- **O*NET** (US) as a fallback for task statements with typical experience bands (feeds `specific.years_inflation`).

One chunk per occupation: canonical title, alt titles, description, 8–15 task statements, essential vs optional skills, typical education/experience band. Embedding on title + alt titles + description; tasks and skills kept as structured fields returned with the hit.

### 3. Compliance rules — small, curated, versioned
`rag/compliance/ZA.md`, `EU.md`, `US-<state>.md`. Each a few hundred words of concrete rules with citations. Retrieved whole (no chunking) by jurisdiction filter and also loaded by the post-generation checker. Changing a rule file is a versioned experiment.

### 4. Exemplar library — the closed loop
Ads (ours or tenant's) with `scorecard.composite ≥ 85`, no gate failures, and, once available, above-median click-to-apply and qualified-applicant rate. Tagged by role family (ESCO group), seniority, channel. Two or three are retrieved as few-shot style anchors. Weak exemplars are evicted when outcome data disagrees with the scorecard.

### 5. Salary benchmarks (optional, later)
Tenant-uploaded bands or a licensed feed. Only ever used to *suggest* a range to the recruiter in the brief step; the drafter never invents pay.

## Retrieval design

**Store**: Postgres with `pgvector` (already running on srv-b). One `chunks` table: `id, tenant_id (nullable for global), collection, text, metadata jsonb, embedding vector, tsv tsvector`. Row-level filters on `tenant_id` and `collection` are non-negotiable; a tenant must never see another tenant's benefits. Meilisearch (also on srv-b) is a reasonable alternative for the keyword leg if Postgres FTS proves weak on titles.

**Embeddings**: Anthropic does not ship an embeddings model; use Voyage AI (`voyage-3.5` or `voyage-3-large`, Anthropic's recommended partner) or a self-hosted open model (`bge-m3`) if data must stay on-box. Pin the model name in metadata; a model change requires re-embedding and is an experiment.

**Hybrid retrieval** per collection, then merge:
- Company profile: filter `tenant_id`; BM25 + vector on the brief's key phrases; top 12, then rerank; always include EE statement, POPIA notice and work-mode policy for the brief's location regardless of score (deterministic "must-include" set).
- Taxonomy: vector search on the brief title plus a fuzzy title match on alt labels; take top 3 occupations, show the recruiter the match at brief time so a wrong occupation is caught before drafting.
- Compliance: exact filter by jurisdiction; whole file.
- Exemplars: filter role family and seniority; top 3 by composite × recency.

**Reranking**: start without it. Add a cross-encoder reranker only if Phase 2's retrieval recall@k is below target.

**Chunking**: semantic units, not fixed windows. A benefit, a task statement, an ad section. Max ~300 tokens. Every chunk carries a stable `source_id` used for citations.

## Prompt assembly (cache-aware)

Order matters for prompt caching; stable content first, volatile last:

1. `system[0]` — role, output contract, writing rules, the scoring rubric in plain language (frozen per prompt version) — `cache_control` 1h
2. `system[1]` — jurisdiction compliance rules (changes rarely) — `cache_control` 1h
3. `system[2]` — tenant profile block (changes per tenant, stable across that tenant's drafts) — `cache_control` 5m
4. `user` — the brief, retrieved taxonomy entry, retrieved exemplars, each context block wrapped with its `source_id`

Citation rule in the system prompt: *every factual statement about the employer, pay, benefits, location, process or legal status must carry a `[src:<id>]` marker; a fact with no source is omitted.* The scorer's grounding judge strips the markers and checks each claim against the cited chunk. Markers are removed before the recruiter sees the ad.

Generation uses `client.messages.parse` with a Zod `JobAd` schema (sections as fields, requirements as `must_have[]` / `nice_to_have[]`, `pay: { min, max, currency, period, basis }`), `claude-opus-5`, adaptive thinking at effort `medium` to start, streaming on. Include the server-side `fallbacks` parameter so a safety refusal does not fail the request.

## Draft → score → revise loop

```
brief ──► normalise role (taxonomy) ──► retrieve ──► generate(JobAd) ──► score()
                                                          ▲                 │
                                                          └── revise(ad, scorecard.failures) ◄── if gates fail or composite < 75 (max 1 pass)
```

The revision prompt contains only the failing metric ids, the offending spans the judge quoted, and the instruction to change nothing else. One revision pass maximum; if it still fails, return it flagged for a human. Phase 4 measures whether the pass is worth its cost.

## RAG-specific evaluation

These sit beside the scorecard in the eval harness:

| Metric | How |
|---|---|
| Retrieval recall@k (company) | Gold set: for each brief, the chunk ids a human says the ad needs (benefits, policy, EE). Target ≥ 0.9 at k=12. |
| Occupation match accuracy | 100 briefs with human-assigned ESCO code; top-1 ≥ 0.85, top-3 ≥ 0.95. |
| Groundedness | `honesty.grounding` from the scorecard, on all cases. |
| Citation precision | Share of `[src:]` markers whose chunk actually supports the sentence (judge). Target ≥ 0.95. |
| Context efficiency | Tokens of retrieved context per draft; watch it against groundedness so we do not win by stuffing. |
| Ablation | no-RAG vs company-only vs company+taxonomy vs all. Each is a SciDLC experiment with the full scorecard. |

## Data and privacy notes

- Tenant data stays row-filtered; embed with a provider whose terms permit it, or self-host embeddings.
- Past ads from job boards may be scraped only where terms allow; tenant-uploaded ads are the safe default.
- Applicant data never enters the RAG store. Outcome metrics are aggregated per ad, not per person (POPIA).
