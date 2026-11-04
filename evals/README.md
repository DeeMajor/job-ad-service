# Drafter eval (Phase 1 onward)

Measures the drafter with the Phase 0 scorer. Every case is a brief derived from a real South African ad, so each draft is compared head-to-head with the real ad for the same role.

```bash
.venv/bin/python -m evals.build_cases                                   # evals/cases/briefs.jsonl from Phase 0's normalised ads (free)
.venv/bin/python -m evals.run_drafter --variant baseline --split test --limit 5          # pilot
.venv/bin/python -m evals.run_drafter --variant baseline                                 # all splits, 1 rep
.venv/bin/python -m evals.run_drafter --variant baseline --split validation --reps 3     # noise floor
```

Outputs in `evals/runs/<variant>/`: `results.jsonl` (one row per case × rep: grade per metric, composite, publishable, beats_real, model, usage, latency), `traces/<id>_rep<k>.json` (brief, drafted ad, scorecard with judge evidence), `errors.jsonl`, `report.md`.

Headline metrics: composite mean, publishable rate (gates pass and composite ≥ 75), **beats_real** (draft composite > the real ad's), gate failures (grounding is the one to watch in Phase 1). Side channels: cost per draft including the judge, latency, words.

Rules (SciDLC): one change per variant; a new drafter prompt version = a new `--variant` name; tune on train, pick on validation, report test; compare to the frozen `baseline` directory, never regenerate it.

Grounding: the brief is the only SOURCE. Anything the draft states that the brief does not is an unsupported claim and fails the grounding gate. In Phase 1 that is expected to happen often; Phase 2 adds retrieval to fix it.
