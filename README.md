# Recruitment platform — job-ad drafter and scorer

Python 3.10+. A headless service that drafts job advertisements from a structured brief and scores any ad against a validated 37-metric rubric, returning a readable draft standard (level + reasons + fixes) rather than a pass/fail gate, developed with a measurement-first lifecycle (SciDLC).

```bash
# environment (uv is a user-level install; python3-venv is not available on this machine)
python3 -m pip install --user uv && export PATH="$HOME/.local/bin:$PATH"
uv venv --python 3.10 .venv && uv pip install --python .venv/bin/python -e ".[dev]"

.venv/bin/python -m pytest -q                       # 56 tests, no network
set -a; source .env; set +a                          # ANTHROPIC_API_KEY for anything that calls a model
PORT=4310 .venv/bin/uvicorn job_ad.api.app:app --port 4310   # the service; OpenAPI at /docs
```

| Path | What |
|---|---|
| `job_ad/metrics/` | the scorer: deterministic graders, lexicons, Claude judge, scorecard |
| `job_ad/drafter/` | HiringBrief v0.3 (request contract), drafter prompt, `draft()` |
| `job_ad/api/app.py` | FastAPI service: `/healthz`, `/v1/spec`, `/v1/scores`, `/v1/drafts` |
| `bench/` | Phase 0 scorer benchmark: `fetch`, `normalize`, `perturb`, `run`; `experiments.md` is the SciDLC log for every phase; `data/` holds frozen corpora and run outputs |
| `evals/` | Phase 1+ drafter eval: `build_cases`, `run_drafter`, `cases/briefs.jsonl` |
| `docs/job-ad-drafter/` | metrics rationale, machine-readable spec, RAG plan, SciDLC plan, service API |
| `legacy/ts/` | the original TypeScript implementation (ported to Python 2026-11-04 with exact scorer parity; kept for reference, not maintained) |
