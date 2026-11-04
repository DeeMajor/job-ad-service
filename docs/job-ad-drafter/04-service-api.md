# Job-ad service — API contract (no UI)

The drafter and scorer are exposed as a small JSON-over-HTTP service (`job_ad/api/app.py`, FastAPI), run under systemd or PM2 behind nginx. Intake adapters (a form, "paste your old ad", a conversational agent) are separate clients that produce a **HiringBrief**; the service never sees a UI.

```
.venv/bin/uvicorn job_ad.api.app:app --host 127.0.0.1 --port 4310
```

OpenAPI is generated from the Pydantic models at `/openapi.json` (interactive at `/docs`); a committed snapshot is at `docs/job-ad-drafter/openapi.json` for client generation. Browser clients: set `ALLOWED_ORIGINS` (comma-separated) on the service to enable CORS for those origins.

Client-facing notes: `/v1/drafts` blocks 15–45 s (two model calls); set client timeouts ≥ 90 s and never auto-retry a draft. Use `/v1/scores` with `judge:false` for live, free feedback while editing.

| Method | Path | Purpose | Cost |
|---|---|---|---|
| GET | `/healthz` | liveness + versions (spec, judge prompt, drafter prompt, brief schema) | free |
| GET | `/v1/spec` | the metric spec the scorer implements | free |
| POST | `/v1/scores` | score an existing ad (human-written or drafted) | free with `judge:false`; one Sonnet call otherwise |
| POST | `/v1/briefs/extract` | free-text role description → HiringBrief (verbatim, nothing invented) + missing required fields + questions to ask | one cheap Sonnet call (≈ $0.02) |
| POST | `/v1/briefs/check` | which metrics a brief can satisfy, its composite ceiling, and which fields to add first | free |
| POST | `/v1/drafts` | draft an ad from a brief, scored; response also carries `brief_feedback` (the same check); blocks 15–45 s | one Opus call + one Sonnet judge call (measured ≈ $0.09) |
| POST | `/v1/draft-jobs` | the same, asynchronously: `202 { job_id, status_url }` immediately; optional `callback_url` | same |
| GET | `/v1/draft-jobs/{id}` | `queued` → `running` → `done` (with the full `/v1/drafts` response in `result`) or `failed`; kept 24 h | free |
| GET | `/metrics` | Prometheus: drafts, judge calls, tokens, estimated spend, latency, active jobs, cap refusals | free |
| GET | `/v1/platforms` | publishing channels the service can prepare: format, limits (hard vs recommended), required extras | free |
| POST | `/v1/ads/render` | an ad → normalised fields, renderings (HTML, text, Markdown, JSON-LD, teaser) and a per-platform payload with validation | free |

Every response carries `x-request-id`. Errors: `422 {detail:[{loc, msg, type}]}` for validation (FastAPI/Pydantic), `404`, `405`, `502 {error:"upstream"}` when the model API fails, `500`.

## HiringBrief v0.3 (request body for `/v1/drafts`, field `brief`)

**Required:** `title`, `company.name`, `responsibilities` (≥ 1), `must_have` (≥ 1). Without these no prompt can produce a publishable ad, so a draft would be money spent on a `not_ready` result. Everything else is optional: absent means "not provided", the drafter may not fill the gap, and `/v1/briefs/check` says what each missing field is worth.

`company.website` (optional): when set, web enrichment is restricted to that domain.

`options.enrich` (default `false`; **switched off at deployment level for now** — `ENRICH_ENABLED=true` turns it on; while off, `enrich:true` returns `400 {detail:{error:"enrichment_disabled"}}` and `/healthz` reports `features.enrichment: false`): one extra Sonnet call with Anthropic's server-side `web_search` tool (≤ `options.max_searches`, default 3) gathers *public employer context* — about, values, locations, published benefits — from the employer's own site. The facts become cited SOURCE blocks the drafter may use and the grounding judge checks against; they come back in `sources[]` by URL so the recruiter can confirm them. **Never pay, never legal statements** (EE, POPIA, accessibility): those are taken only from the brief, and any web fact that looks like one is dropped before the drafter sees it. Adds roughly $0.03–0.06 and 10–20 s per draft.

`options.allow_not_ready` (default `false`): if the completeness check says the draft would come back `not_ready` (today: a designated employer without an EE statement), the service refuses with `422 {detail: {error: "brief_not_ready", not_ready_reasons, suggestions}}` before any model call. Pass `true` to draft anyway.

```jsonc
{
  "schema_version": "0.3",
  "title": "Accounts Payable Clerk",
  "seniority": "junior",                       // entry|junior|mid|senior|lead|manager|head|executive
  "employment_type": "permanent",              // permanent|fixed_term|contract|part_time|internship|learnership|temporary
  "purpose": "Own the supplier payment cycle for the Durban depot",
  "success_measures": ["Creditors age analysis under 45 days", "Weekly payment run ready by Thursday"],
  "responsibilities": ["Capture and match ~300 supplier invoices a week in Sage", "Reconcile 40 supplier statements monthly"],
  "tools": ["Sage", "Excel"],
  "must_have": [
    { "text": "Two or more years in a creditors role" },
    { "text": "Working knowledge of Sage", "justification": "all invoice capture happens in Sage" }
  ],
  "nice_to_have": ["Logistics or transport experience"],
  "location": "Durban, KwaZulu-Natal",
  "work_mode": "onsite",                       // remote|hybrid|onsite
  "hours": "Mon–Fri 08:00–17:00",
  "start_date": "2027-01-11",
  "positions": 1,
  "pay": { "min": 18000, "max": 22000, "currency": "ZAR", "period": "month", "basis": "years of creditors experience and Sage proficiency" },
  "benefits": ["Medical aid contribution 50%", "Provident fund 7% employer contribution", "20 days annual leave"],
  "company": { "name": "Mzansi Logistics", "about": "We move freight for 400 retailers across Gauteng and KZN." },
  "team": { "reports_to": "Finance Supervisor", "size": 3, "notes": "Two other clerks and two buyers" },
  "process": { "steps": "Phone screen, one on-site interview, short Excel exercise", "closing_date": "2026-11-30", "contact": "careers@example.co.za", "reference": "FIN-0042" },
  "statements": { "ee": "…", "popia": "…", "accessibility": "…" },
  "jurisdiction": "ZA",                        // ZA|EU|US|US-XX
  "designated_employer": true,                 // a missing EE statement becomes a must-fix reason when true
  "hosted_apply": false,                       // true when the board has its own Apply button
  "channel": "default"                         // default|linkedin|indeed — shifts the word-count band
}
```

Requirements accept a plain string or `{text, justification}`. The justification is the recruiter's "which duty needs this"; it feeds traceability and is the Employment Equity *inherent requirement* defence.

## Response for `/v1/drafts`

```jsonc
{
  "ad": { /* JobAd: title, company, summary, responsibilities[], must_have[], nice_to_have[], pay, location, work_mode, benefits[], team, process, closing_date, statements…, apply_contact */ },
  "rendered": {
    "markdown": "# Accounts Payable Clerk\n**Mzansi Logistics · Durban, KwaZulu-Natal · onsite**\n**Salary: ZAR 18,000 – 22,000 per month. …**\n\n## About us\n\n…\n\n## What you'll do\n\n- Capture and match …",
    "text": "Accounts Payable Clerk\n\nMzansi Logistics\n\n…"
  },
  "scorecard": {
    "spec_version": "0.1.8",
    "composite": 81.4,                         // 0–100, always computed; never zeroed
    "standard": {                              // ← the thing to show the recruiter
      "level": "publishable",                  // publishable (≥75, nothing to fix first) | review (60–74) | not_ready (a must-fix issue, or <60)
      "summary": "Publishable. Composite 81.4 against a bar of 75. 2 optional improvements listed.",
      "reasons": [                             // ordered: must_fix first, then lowest-scoring metrics; at most 10
        { "severity": "could_improve", "metric": "clarity.reading_grade", "label": "Reading level",
          "message": "Measured 9.8, target 0–9. Shorter sentences and everyday words; aim for a Grade 8 reading level.", "evidence": [] }
      ]
    },
    "dimensions": { "clarity": {"score": 0.9, "n": 7}, "specificity": {...}, ... },
    "metrics": [ { "id": "honesty.grounding", "status": "ok", "raw": 1, "normalized": 1, "evidence": [], "reasoning": "…" }, ... ],
    "verdict": "publishable", "gates_passed": true, "gate_failures": []   // legacy aliases of standard.level / must-fix reasons; prefer `standard`
  },
  "meta": { "request_id": "…", "drafter": { "model": "claude-opus-5", "usage": {...}, "latency_s": 21.3, "prompt_version": "0.2.1" }, "judge": { "model": "claude-sonnet-5", ... },
            "enrichment": { "model": "claude-sonnet-5", "searches": 2, "facts": 6, "usage": {...}, "latency_s": 12.4, "prompt_version": "0.1.0", "notes": "…" },   // only with options.enrich
            "spec": "0.1.9", "brief_schema": "0.3" }
}
```

**Structured and rendered.** `ad` is the source of truth: the scorer runs on its sections, `standard.reasons[].evidence` points into it, the frontend edits one field at a time, and job boards take separate fields. `rendered.markdown` and `rendered.text` are derived from it deterministically for display, copy-paste or conversion to HTML. Clients that only want the text can call `POST /v1/drafts?format=markdown` and receive `text/markdown` with the composite, standard level, prompt and spec versions in `x-composite`, `x-standard`, `x-drafter-prompt`, `x-spec` headers.

**The draft standard.** `standard` is the readable verdict. There are no gates and nothing zeroes the score: legal, honesty and minimum-content problems appear as `must_fix` reasons (publishing with one open is a legal or trust risk, not a style issue), weak metrics as `should_fix` (normalised < 0.5) or `could_improve` (0.5–0.8). Every reason carries a `label`, a plain-language `message` that says what to do, the `metric` id for deep-linking into `/v1/spec`, and `evidence` quoted from the ad. `level` is `not_ready` whenever a must-fix reason exists or the composite is under 60. `metrics[]` remains the full detail. A client that wants a revision loop re-posts the brief with the reasons folded into `purpose`/`responsibilities`; the service itself does not loop in Phase 1.

## `/v1/briefs/extract` — intake from free text

The frontend lets the user describe the role in their own words; this turns that into the contract.

```jsonc
{ "description": "We need an accounts payable clerk for our Durban depot. They'll capture about 300 supplier invoices a week in Sage and reconcile 40 statements a month. Must have 2+ years creditors experience and know Sage. Pays R18k–R22k a month, reports to the Finance Supervisor.", "company_name": "Mzansi Logistics" }
→ { "brief": { /* valid HiringBrief, ready for /v1/drafts */ } | null,
    "brief_partial": { /* everything extracted, HiringBrief shape, even if incomplete — pre-fill the form */ },
    "missing_required": [],                        // e.g. ["must_have"] when the text names no requirements → brief is null
    "questions": ["What benefits come with the role?", "Is the role on-site, hybrid or remote?", "What are the application steps and closing date?"],
    "completeness": { /* /v1/briefs/check on the extracted brief */ },
    "meta": { "model": "claude-sonnet-5", "usage": {...}, "latency_s": 6.2, "prompt_version": "0.1.0", "brief_schema": "0.3" } }
```

Extraction copies facts; it never fills gaps. A description that names no duties or requirements returns `brief: null` with `missing_required` and questions, not an error — the user needs to be asked, not rejected. Recommended flow: describe → extract → show `brief_partial` plus `questions` for confirmation or edits → `/v1/drafts`.

## `/v1/briefs/check`

```jsonc
{ "brief": { "title": "Driver", "company": { "name": "Acme" }, "responsibilities": ["Deliver stock to 40 pharmacies daily"], "must_have": ["Code 10 licence"] } }
→ { "valid": true, "would_be_not_ready": false, "not_ready_reasons": [],
    "unattainable_metrics": ["pay.range_present", "evp.benefits_specific", …], "attainable_metrics": 19, "total_scored_metrics": 33,
    "estimated_ceiling": 57.7,
    "suggestions": [ { "field": "must_have", "unlocks": ["specific.must_have_count", "specific.requirement_traceability"], "estimated_lift": 5.6, "hint": "Three to six must-haves." }, … ] }
```

Four fields are required for a brief to be *valid*; this endpoint says what it would be *worth*. `would_be_not_ready` means the draft would come back `not_ready` with must-fix reasons (today: a designated employer without an EE statement) and `/v1/drafts` would refuse it unless `options.allow_not_ready` is set. `estimated_ceiling` is the best composite the brief can reach if the drafter does everything right; `suggestions` are ranked by how many composite points each missing field would unlock. Deterministic, no model call — safe to call on every form change.

## Async drafting, spend cap, operations

```jsonc
POST /v1/draft-jobs  { "brief": {...}, "options": {...}, "callback_url": "https://frontend.example/hooks/draft" }
→ 202 { "job_id": "…", "status": "queued", "status_url": "/v1/draft-jobs/…", "created_at": 1762277000.1 }
GET  /v1/draft-jobs/{id}
→ 200 { "job_id": "…", "status": "done", "started_at": …, "finished_at": …, "result": { /* the /v1/drafts response */ } }
```

Pre-flight is identical to `/v1/drafts` (enrichment switch, `brief_not_ready` refusal, spend cap), so a job that is accepted will run. Drafting happens in a bounded pool inside the service (`MAX_CONCURRENT_DRAFTS`); job state lives in Redis (`REDIS_URL`, TTL 24 h) or in memory when Redis is absent. If the service restarts mid-job, the job is marked `failed` with "service restarted" — re-submit. `callback_url` receives `{ job_id, status, result, error }` once, best effort; polling is the reliable path.

**Spend cap.** The service estimates USD per draft from token usage and refuses new drafts with `429 { detail: { error: "daily_spend_cap" } }` once `DAILY_SPEND_CAP_USD` is reached for the UTC day (default 20; 0 disables). `/healthz` shows `spend.today_usd`. This is a guard against a looping client, not a billing system.

**Observability.** `/metrics` (Prometheus) and JSON logs on stdout, every line stamped with spec, drafter-prompt and judge-prompt versions. Internal service: no authentication; bind to the VPN interface, never a public one.

## Publishing: `/v1/platforms` and `/v1/ads/render`

The draft is one shape; job boards each want their own. `GET /v1/platforms` lists what we can prepare — today `linkedin`, `indeed`, `pnet`, `careers24`, `careerjunction`, `careers_site` (schema.org JobPosting JSON-LD for your own page / Google for Jobs), `social_teaser`, `generic_text` — each with its description format, limits marked `hard` (rejected beyond) or `recommended` (performance), and the extras it requires (`apply_url`, `category` for the SA boards).

```jsonc
POST /v1/ads/render
{ "ad": { /* JobAd from a draft */ },
  "extras": { "apply_url": "https://…/apply", "reference": "FIN-0042", "category": "Finance / Accounting", "employment_type": "permanent", "company_url": "https://…", "valid_through": "2026-11-30" },
  "platforms": ["linkedin", "indeed", "pnet", "careers_site", "social_teaser"] }        // omit for all
→ { "fields": { "title", "company_name", "location": { "city", "province", "country", "remote", "hybrid" }, "employment_type_schema": "FULL_TIME", "salary": { "min", "max", "currency", "unit" }, "closing_date", "reference", "category", "apply_url", "word_count" },
    "renderings": { "html": "…safe subset: h2/h3/p/ul/li/strong/br…", "text": "…", "markdown": "…", "json_ld": { "@type": "JobPosting", … }, "teaser": "We're hiring: … Apply: https://…" },
    "channels": { "linkedin": { "ready": true, "issues": [ { "severity": "warning", "field": "description", "message": "…" } ], "payload": { "title", "description", "description_format": "text", "employment_type": "Full-time", "location", "salary", "apply_url", … } },
                  "pnet": { "ready": false, "issues": [ { "severity": "error", "field": "category", "message": "PNet requires `category`…" } ], "payload": { … } }, … } }
```

`ready` is false when any `error` issue exists (missing required extra, hard limit exceeded, no SA province derivable for an SA board). Warnings (recommended length bands) do not block. Location is normalised for South Africa (city → province lookup). Employment type is mapped per platform. Deterministic and free; the actual sending to each platform is a separate concern (credentials, retries, status) that consumes these payloads.

## `/v1/scores`

```jsonc
{ "ad": { /* JobAd */ }, "context": { "jurisdiction": "ZA", "designated_employer": true, "hosted_apply": false, "sources": [{ "id": "brief", "text": "…" }] }, "judge": true }
```

With `judge:false` only the deterministic metrics run (no cost, milliseconds); judged metrics are reported as `skipped`. With `sources` provided, grounding is judged against them; without, grounding is `not_applicable`. The response carries the same `standard` object.

## Versioning

`healthz` reports four versions. Any change to the spec, the judge prompt, the drafter prompt or the brief schema bumps its number and is logged in `bench/experiments.md`. Scorecards embed `spec_version`; drafts embed `prompt_version`. Clients should store both with the published ad so later outcome metrics can be joined to the scorer that produced the score.
