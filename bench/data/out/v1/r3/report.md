# Phase 0 scorer benchmark — v1

Generated 2026-11-04T12:05:26.628Z. Spec 0.1.5, judge prompt 0.4.0. Normalizer: llm; judge: claude-sonnet-5; reference: claude-opus-5; reps: 3.

## Exit criteria

| Criterion | Result |
|---|---|
| Perturbation detection ≥ 0.9 (det) / 0.85 (judge) on every target | FAIL (insufficient data: strip_ee_popia→compliance.popia_notice, vague_responsibilities→specific.responsibility_concreteness, remove_team_and_work_mode→evp.work_mode_clarity) |
| Judge–reference κ ≥ 0.7 (0.8 gates) or MAE ≤ 0.2 for ratios, self-consistency ≥ 0.9 | FAIL |
| Null / oracle probes | PASS |

## Corpus and real-ad distribution

| | |
|---|---|
| Ads | 20 (full text 100%) |
| Sources | workday: 20 |
| Composite mean / median | 56.91 / 57.40 |
| Composite p10 / p25 / p75 / p90 | 51.50 / 55.40 / 58.70 / 64.20 |
| Gates pass rate | 100% |
| Verdicts | regenerate: 16, review: 4 |

## Metric distribution on real ads

| Metric | n | mean raw | mean norm | pass rate |
|---|---|---|---|---|
| structure.sections_present | 20 | 0.70 | 0.70 | – |
| structure.title_matches_content | 20 | 1 | 1 | 100% |
| structure.title_quality | 20 | 1 | 1 | 100% |
| clarity.word_count | 20 | 648.60 | 0.65 | – |
| clarity.reading_grade | 20 | 13.56 | 0.36 | – |
| clarity.longest_sentence | 20 | 47.10 | 0.65 | – |
| clarity.scannability | 20 | 0.95 | 1 | – |
| specific.responsibility_concreteness | 20 | 0.21 | 0.03 | – |
| specific.must_have_count | 20 | 4.75 | 0.42 | – |
| specific.nice_to_have_split | 20 | 0.85 | 0.85 | 85% |
| specific.requirement_traceability | 20 | 0.69 | 0.65 | – |
| specific.years_inflation | 20 | 0 | 1 | – |
| pay.range_present | 20 | 0 | 0 | 0% |
| pay.context_present | 20 | 0 | 0 | 0% |
| honesty.buzzword_density | 20 | 0.06 | 1.00 | – |
| inclusive.gender_coding | 20 | -0.05 | 0.95 | – |
| inclusive.exclusionary_terms | 20 | 0 | 1 | – |
| inclusive.proxy_requirements | 20 | 0 | 1 | – |
| inclusive.accessibility_statement | 20 | 1 | 1 | 100% |
| inclusive.candidate_address | 20 | -0.03 | 0.32 | – |
| compliance.protected_grounds | 20 | 1 | 1 | 100% |
| compliance.ee_statement | 20 | 1 | 1 | 100% |
| compliance.popia_notice | 20 | 0.15 | 0.15 | 15% |
| compliance.no_prohibited_requests | 20 | 1 | 1 | 100% |
| evp.why_this_role | 20 | 0.05 | 0.05 | 5% |
| evp.benefits_specific | 20 | 0 | 0 | 0% |
| evp.team_context | 20 | 0.60 | 0.60 | 60% |
| evp.work_mode_clarity | 20 | 0.20 | 0.20 | 20% |
| seo.key_terms_early | 20 | 1 | 1 | 100% |
| seo.no_stuffing | 20 | 0.65 | 0.65 | 65% |
| process.steps_and_timeline | 20 | 0 | 0 | 0% |

## Perturbation detection

Detection is measured only on ads with headroom (original normalised score > 0). "n" is eligible ads out of all perturbed; a pass needs n ≥ 5, rate ≥ target and zero false improvements (perturbed scoring higher than original by more than judge noise, 0.1 for judged metrics).

| Perturbation | Target metric | n (of) | detected | false impr. | target | |
|---|---|---|---|---|---|---|
| third_person_candidate | inclusive.candidate_address | 17 (20) | 100% | 0 | 90% | ok |
| inject_buzzwords | honesty.buzzword_density | 20 (20) | 100% | 0 | 90% | ok |
| inject_exclusionary_phrase | inclusive.exclusionary_terms | 20 (20) | 100% | 0 | 90% | ok |
| inflate_years | specific.years_inflation | 20 (20) | 100% | 0 | 90% | ok |
| inject_masculine_coding | inclusive.gender_coding | 20 (20) | 100% | 0 | 90% | ok |
| inflate_must_haves | specific.must_have_count | 15 (15) | 100% | 0 | 90% | ok |
| bloat_prose | clarity.reading_grade | 18 (20) | 100% | 0 | 90% | ok |
| bloat_prose | clarity.longest_sentence | 20 (20) | 100% | 0 | 90% | ok |
| bloat_prose | clarity.scannability | 20 (20) | 95% | 0 | 90% | ok |
| strip_ee_popia | compliance.ee_statement | 20 (20) | 100% | 0 | 90% | ok |
| strip_ee_popia | compliance.popia_notice | 3 (20) | 0% | 0 | 90% | too few |
| vague_responsibilities | specific.responsibility_concreteness | 4 (20) | 100% | 0 | 85% | too few |
| gimmick_title | structure.title_quality | 20 (20) | 100% | 0 | 90% | ok |
| untraceable_requirements | specific.requirement_traceability | 16 (20) | 94% | 1 | 85% | FAIL |
| prohibited_request | compliance.no_prohibited_requests | 20 (20) | 100% | 0 | 85% | ok |
| proxy_requirement | inclusive.proxy_requirements | 20 (20) | 100% | 0 | 85% | ok |
| proxy_requirement | compliance.protected_grounds | 20 (20) | 100% | 0 | 85% | ok |
| hallucinate_benefit | honesty.grounding | 19 (19) | 100% | 0 | 85% | ok |
| remove_team_and_work_mode | evp.team_context | 11 (15) | 45% | 0 | 85% | FAIL |
| remove_team_and_work_mode | evp.work_mode_clarity | 4 (15) | 75% | 0 | 85% | too few |
| merge_nice_to_haves | specific.nice_to_have_split | 6 (6) | 100% | 0 | 90% | ok |

## Judge agreement

Categorical metrics: Cohen's κ vs the reference model. Ratio metrics: mean absolute error vs the reference (κ on binned ratios punishes near-boundary values). Self-consistency: same label (or ratio spread ≤ 0.2, about one bullet on a short list) across 3 reps.

| Metric | n | agreement | self-consistency | target | |
|---|---|---|---|---|---|
| structure.title_matches_content | 10 | κ 1 | 100% | κ ≥ 0.7 | ok |
| specific.responsibility_concreteness | 10 | MAE 0.13 | 90% | MAE ≤ 0.2 | ok |
| specific.requirement_traceability | 10 | MAE 0.30 | 80% | MAE ≤ 0.2 | FAIL |
| pay.context_present | 10 | κ 1 | 100% | κ ≥ 0.7 | ok |
| inclusive.proxy_requirements | 10 | κ 0 | 100% | κ ≥ 0.7 | FAIL |
| compliance.protected_grounds | 10 | κ 1 | 100% | κ ≥ 0.8 | ok |
| compliance.no_prohibited_requests | 10 | κ 1 | 100% | κ ≥ 0.8 | ok |
| evp.why_this_role | 10 | κ 0.62 | 100% | κ ≥ 0.7 | FAIL |
| evp.benefits_specific | 10 | κ 1 | 100% | κ ≥ 0.7 | ok |
| evp.team_context | 10 | κ 0.40 | 80% | κ ≥ 0.7 | FAIL |
| evp.work_mode_clarity | 10 | κ 1 | 100% | κ ≥ 0.7 | ok |
| process.steps_and_timeline | 10 | κ 1 | 100% | κ ≥ 0.7 | ok |

## Probes

| Probe | Expectation | composite | gates | result |
|---|---|---|---|---|
| empty | blocked, composite < 20 | 0 | fail (compliance.ee_statement) | ok |
| i_dont_know | blocked or composite < 20 | 0 | fail (compliance.ee_statement) | ok |
| wrong_role_confident | structure.title_matches_content fails when judged; deterministic alone cannot catch | 93.10 | pass | ok |
| oracle_good_fixture | gates pass, composite >= 80 | 94.70 | pass | ok |

## Cost and latency

Judge calls: 20; mean input tokens 4688.80 (cache-read share 46%); mean output tokens 3088.85; mean latency 26.63 s. Normalize calls: 0, mean tokens 0.
