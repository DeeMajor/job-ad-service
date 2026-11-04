# AI Job-Ad Drafter — planning pack

Goal: a service module that drafts a job ad for **any role** from a short hiring brief, grounded in company facts and role knowledge (RAG), and developed with a measurement-first lifecycle (SciDLC) so every change is justified by a metric moving.

Order of work is deliberate: **measure first, generate second**. Without a scorer we cannot tell whether a prompt change, a retrieval change or a model change helped.

| Doc | What it answers |
|---|---|
| [01-job-ad-quality-metrics.md](01-job-ad-quality-metrics.md) | What makes a good job ad, with evidence, and how each property is scored |
| [metrics/job-ad-metrics.yaml](metrics/job-ad-metrics.yaml) | Machine-readable metric spec the scorer implements (ids, type, grader, thresholds, weights, gates) |
| [02-rag-plan.md](02-rag-plan.md) | Knowledge sources, retrieval design, prompt assembly, grounding and RAG-specific evals |
| [03-scidlc-plan.md](03-scidlc-plan.md) | The scientific development lifecycle: phases, hypotheses, experiments, decision gates, experiment log |
| [04-service-api.md](04-service-api.md) | The headless service: endpoints, the HiringBrief v0.3 request contract, response shape, versioning |

## Assumptions (stated, not verified with you)

- **"SciDLC"** is not a published framework. It is interpreted here as a *Scientific Development Lifecycle*: observe → hypothesise → pre-register a metric and success criterion → run a controlled experiment against a frozen baseline → measure with a known noise floor → decide (ship / iterate / kill) → record. Every change to the module is an experiment with a number.
- **Stack**: Python 3.10+, `anthropic` SDK with Pydantic structured outputs, FastAPI for the headless service, scikit-learn/pandas for benchmark statistics, Postgres + `pgvector` for retrieval when Phase 2 arrives. (Started in TypeScript on a fleet-fit assumption; ported 2026-11-04 on merit — the project's centre of gravity is measurement and data work. The TS version is in `legacy/ts/`; scorer parity was proven exact on 40 real ads × 37 metrics and on the smoke benchmark before the switch.)
- **Primary jurisdiction**: South Africa (Employment Equity Act, POPIA), with a pluggable rule set so EU/US pay-transparency rules can be added.
- **Models**: `claude-opus-5` drafts; `claude-sonnet-5` judges (never the model under test). Costs and effort levels are tuned in Phase 4 of the SciDLC plan.

## Module architecture (as built, Phase 1, Python)

```
job_ad/
  api/app.py        # headless FastAPI service: /healthz, /v1/spec, /v1/scores, /v1/drafts (no UI); OpenAPI from Pydantic
  schema.py         # JobAdOut: model-facing output shape (no unions) + from_llm_output → JobAd
  metrics/          # pure functions + LLM judge; no generation here
    deterministic.py  # length, readability, lexicons, salary math, structure checks
    judge/            # Claude-as-judge rubric with structured output (schema.py, prompt.py, run.py)
    scorecard.py      # combines → Scorecard (per-metric values + gates + composite)
  rag/
    ingest/         # company profile, past ads, taxonomy (ESCO/OFO), compliance rules
    retrieve.ts     # hybrid retrieval, tenant + jurisdiction filters
    context.ts      # assembles cited context blocks for the prompt
  drafter/
    brief.py        # HiringBrief v0.3 (the request contract) + brief_from_job_ad (old-ad intake)
    draft.py        # brief → JobAd (claude-opus-5, structured output) → scorecard; no RAG, no revision yet
    prompts.py      # versioned system prompt (cache-stable prefix)
evals/
  build_cases.py    # briefs derived from Phase 0's real ads, with the real ad's score to beat
  run_drafter.py    # baseline / variant runs → results.jsonl + traces/ + report.md
bench/              # Phase 0 scorer benchmark (fetch, normalize, perturb, run) + experiments.md (the SciDLC log for every phase)
```

Data contract at the centre of everything:

```
HiringBrief  →  draft()  →  { ad: JobAd, scorecard: Scorecard, citations: Citation[] }
JobAd        →  score()  →  Scorecard          (usable on human-written ads too)
```

The scorer is independently valuable: it can grade ads recruiters write by hand, which is also how we collect the human-labelled calibration set.
