# Phase 0 scorer benchmark

Validates the job-ad scorer (`job_ad/metrics`) with no human labelling:
real ads from the internet, contrastive perturbations, model-vs-model agreement, null probes.
Design and exit criteria: `docs/job-ad-drafter/03-scidlc-plan.md` → Phase 0.

## 1. Pull a corpus (frozen per version)

```bash
# South Africa, full text, no key: public job-board APIs of named SA employers (Workday, Greenhouse; Lever/Workable supported)
.venv/bin/python -m bench.fetch --source ats --boards bench/boards.za.json --limit 400 --version v1

# any list of career-page URLs with schema.org JobPosting markup
.venv/bin/python -m bench.fetch --source jsonld --urls my-urls.txt --version v1

# keyless feeds (not SA; pipeline testing only)
.venv/bin/python -m bench.fetch --source arbeitnow --limit 40 --version smoke
```

`bench/boards.za.json` lists the employers: tenant/site for Workday (with the South Africa `locationCountry` facet so pan-African tenants return SA roles only), board slug for Greenhouse, plus a per-board cap so no single employer dominates. Add employers there; the Workday site name is the path segment after `myworkdayjobs.com/en-US/` on any of their job URLs.

**Adzuna** (`--source adzuna`, needs `ADZUNA_APP_ID`/`ADZUNA_APP_KEY`): the search API returns ~65-word snippets and its landing pages block automated clients (CloudFront 403), so full text cannot be recovered. Snippets fall under the 120-word minimum and are dropped. Kept as a source for salary metadata only.

Output: `bench/data/raw/<version>/ads.jsonl` (append-only, de-duplicated, ads under 120 words dropped). Never regenerate a version; start a new one.

## 2. Run the benchmark

```bash
# full run (needs ANTHROPIC_API_KEY; load with `set -a; source .env; set +a`)
.venv/bin/python -m bench.run --version v1

# cheaper variants
.venv/bin/python -m bench.run --version v1 --limit 50 --agreement-sample 20 --reps 2
.venv/bin/python -m bench.run --version smoke --normalizer heuristic --judge off     # offline, deterministic half only
```

Every stage is resumable: rerunning skips ads already in the output files. Errors go to `errors.jsonl`, never into a score.

Each judge-prompt or spec change gets its own `--run` name (r1, r2, …) so results stay comparable; normalised ads are shared across runs because the normaliser rarely changes.

Output in `bench/data/out/<version>/`:

| file | contents |
|---|---|
| `normalized.jsonl` | raw ad → structured `JobAd` (LLM extraction, verbatim, or heuristic); shared by all runs |
| `<run>/scores.jsonl` | scorecard per real ad, with judge model, usage and latency |
| `<run>/perturbations.jsonl` | per ad × perturbation × target metric: original vs perturbed normalised score, detected?, false improvement? |
| `<run>/agreement.jsonl` | per ad × judged metric: reference-model label, N judge repetitions, both reasonings |
| `<run>/report.md` / `report.json` | exit-criteria table, real-ad score distribution, detection rates, κ / MAE and consistency, probes, cost |

## 3. What "pass" means

| Check | Target |
|---|---|
| Perturbation detection, deterministic metrics | ≥ 90% of ads |
| Perturbation detection, judged metrics | ≥ 85% of ads |
| Judge vs `claude-opus-5` reference | κ ≥ 0.7 for pass/fail and counts (≥ 0.8 for grounding and compliance); MAE ≤ 0.2 for ratios |
| Judge self-consistency over 3 reps | ≥ 90% |
| Probes: empty ad, "I don't know" | blocked or composite < 20 |
| Probe: good fixture | gates pass, composite ≥ 80 |

A failing check is a finding about the metric or the rubric, not about the ads. Fix the grader or the rubric, bump `JUDGE_PROMPT_VERSION` or the spec version, rerun under a new output version, log it in `experiments.md`.

## Cost guide

Measured on run r1 (judge prompt 0.2.0): $0.033 per judge call, 7.8 judge calls per ad, **$0.27 per ad all-in**; a 242-ad corpus is about $65 plus $7 for a 40-ad agreement sample. Output tokens dominate (judge reasoning), so prompt 0.3.0 caps quotes and reasoning length. Run `--limit 20 --agreement-sample 10` first and read `report.md`'s cost line before the full run.
