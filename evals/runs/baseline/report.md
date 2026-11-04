# Drafter eval — variant baseline

Generated 2026-11-04T14:06:39Z. 56 rows. Drafter claude-opus-5/medium, prompt 0.1.1; judge claude-sonnet-5, prompt 0.5.0; spec 0.1.8.

## Headline

| Split | n | composite mean | median | publishable | gates pass | beats real ad | real ad mean |
|---|---|---|---|---|---|---|---|
| test | 8 | 66.52 | 66.90 | 0% | 100% | 100% | 57.17 |
| train | 24 | 70.35 | 70.60 | 25% | 100% | 100% | 52.70 |
| validation | 24 | 69.40 | 70.70 | 33% | 100% | 100% | 44.84 |

## By role

| Role | n | composite | beats real | real mean |
|---|---|---|---|---|
| bank_sales | 28 | 69.12 | 100% | 57.20 |
| customer_service | 7 | 75.84 | 100% | 67.29 |
| management | 7 | 65.86 | 100% | 35.26 |
| specialist_admin | 7 | 65.81 | 100% | 53.69 |
| tech_data | 7 | 71.17 | 100% | 14.76 |

Noise floor: 8 cases with repeats; mean composite spread 2.66, max 6.10.

## Weakest metrics (mean normalised, lowest first)

| Metric | mean | n |
|---|---|---|
| process.steps_and_timeline | 0 | 56 |
| pay.range_present | 0.11 | 56 |
| pay.context_present | 0.12 | 56 |
| compliance.popia_notice | 0.16 | 56 |
| evp.team_context | 0.20 | 56 |
| evp.benefits_specific | 0.25 | 56 |
| evp.work_mode_clarity | 0.25 | 56 |
| specific.responsibility_concreteness | 0.54 | 56 |
| clarity.reading_grade | 0.57 | 56 |
| evp.why_this_role | 0.59 | 56 |

## Cost and latency

Drafter: mean input 4033.38 tokens, output 1241.30, latency 13.78 s. Mean words per ad 518.14. **Mean cost per draft incl. judge: $0.086** (total $4.79).
