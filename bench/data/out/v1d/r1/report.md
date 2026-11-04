# Phase 0 scorer benchmark — v1d

Generated 2026-11-04T12:30:43.216Z. Spec 0.1.5, judge prompt 0.4.0. Normalizer: llm; judge: claude-sonnet-5; reference: claude-opus-5; reps: 3.

## Exit criteria

| Criterion | Result |
|---|---|
| Perturbation detection ≥ 0.9 (det) / 0.85 (judge) on every target | FAIL (insufficient data: strip_ee_popia→compliance.popia_notice, delete_process→process.contact_or_link, delete_process→structure.sections_present, remove_timeline→process.steps_and_timeline, strip_pay→pay.range_present, strip_pay→structure.sections_present, widen_pay_range→pay.range_width) |
| Judge–reference κ ≥ 0.7 (0.8 gates) or MAE ≤ 0.2 for ratios, self-consistency ≥ 0.9 | FAIL |
| Null / oracle probes | PASS |

## Corpus and real-ad distribution

| | |
|---|---|
| Ads | 20 (full text 100%) |
| Sources | workday: 15, greenhouse: 5 |
| Composite mean / median | 47.14 / 54.10 |
| Composite p10 / p25 / p75 / p90 | 0 / 50.10 / 63.10 / 70.40 |
| Gates pass rate | 80% |
| Verdicts | regenerate: 9, blocked: 4, review: 7 |

Gate failure rates: compliance.ee_statement 20%

## Metric distribution on real ads

| Metric | n | mean raw | mean norm | pass rate |
|---|---|---|---|---|
| structure.sections_present | 20 | 0.78 | 0.78 | – |
| structure.title_matches_content | 20 | 0.95 | 0.95 | 95% |
| structure.title_quality | 20 | 1 | 1 | 100% |
| clarity.word_count | 20 | 670.35 | 0.62 | – |
| clarity.reading_grade | 20 | 12.48 | 0.51 | – |
| clarity.longest_sentence | 20 | 41.35 | 0.81 | – |
| clarity.scannability | 20 | 0.88 | 0.98 | – |
| specific.responsibility_concreteness | 20 | 0.36 | 0.21 | – |
| specific.must_have_count | 20 | 7.20 | 0.63 | – |
| specific.nice_to_have_split | 20 | 0.85 | 0.85 | 85% |
| specific.requirement_traceability | 20 | 0.59 | 0.39 | – |
| specific.years_inflation | 20 | 0.10 | 0.95 | – |
| pay.range_present | 20 | 0.20 | 0.20 | 20% |
| pay.range_width | 4 | 0.05 | 1 | – |
| pay.context_present | 20 | 0.15 | 0.15 | 15% |
| honesty.buzzword_density | 20 | 0.08 | 1 | – |
| inclusive.gender_coding | 20 | -0.02 | 0.88 | – |
| inclusive.exclusionary_terms | 20 | 0 | 1 | – |
| inclusive.proxy_requirements | 20 | 0 | 1 | – |
| inclusive.accessibility_statement | 20 | 0.50 | 0.50 | 50% |
| inclusive.candidate_address | 20 | 0.84 | 0.63 | – |
| compliance.protected_grounds | 20 | 1 | 1 | 100% |
| compliance.ee_statement | 20 | 0.80 | 0.80 | 80% |
| compliance.popia_notice | 20 | 0.20 | 0.20 | 20% |
| compliance.no_prohibited_requests | 20 | 1 | 1 | 100% |
| evp.why_this_role | 20 | 0.25 | 0.25 | 25% |
| evp.benefits_specific | 20 | 0.35 | 0.35 | 35% |
| evp.team_context | 20 | 0.35 | 0.35 | 35% |
| evp.work_mode_clarity | 20 | 0.30 | 0.30 | 30% |
| seo.key_terms_early | 20 | 1 | 1 | 100% |
| seo.no_stuffing | 20 | 0.65 | 0.65 | 65% |
| process.steps_and_timeline | 20 | 0 | 0 | 0% |

## Perturbation detection

Detection is measured only on ads with headroom (original normalised score > 0). "n" is eligible ads out of all perturbed; a pass needs n ≥ 5, rate ≥ target and zero false improvements (perturbed scoring higher than original by more than judge noise, 0.1 for judged metrics).

| Perturbation | Target metric | n (of) | detected | false impr. | target | |
|---|---|---|---|---|---|---|
| merge_nice_to_haves | specific.nice_to_have_split | 15 (15) | 100% | 0 | 90% | ok |
| inject_masculine_coding | inclusive.gender_coding | 19 (20) | 100% | 0 | 90% | ok |
| inflate_years | specific.years_inflation | 20 (20) | 100% | 0 | 90% | ok |
| inflate_must_haves | specific.must_have_count | 11 (11) | 100% | 0 | 90% | ok |
| inject_exclusionary_phrase | inclusive.exclusionary_terms | 20 (20) | 100% | 0 | 90% | ok |
| third_person_candidate | inclusive.candidate_address | 19 (20) | 100% | 0 | 90% | ok |
| bloat_prose | clarity.reading_grade | 19 (20) | 100% | 0 | 90% | ok |
| bloat_prose | clarity.longest_sentence | 19 (20) | 100% | 0 | 90% | ok |
| bloat_prose | clarity.scannability | 20 (20) | 100% | 0 | 90% | ok |
| inject_buzzwords | honesty.buzzword_density | 20 (20) | 100% | 0 | 90% | ok |
| vague_responsibilities | specific.responsibility_concreteness | 10 (20) | 100% | 0 | 85% | ok |
| strip_ee_popia | compliance.ee_statement | 16 (17) | 100% | 0 | 90% | ok |
| strip_ee_popia | compliance.popia_notice | 4 (17) | 75% | 0 | 90% | too few |
| proxy_requirement | inclusive.proxy_requirements | 20 (20) | 100% | 0 | 85% | ok |
| proxy_requirement | compliance.protected_grounds | 20 (20) | 100% | 0 | 85% | ok |
| untraceable_requirements | specific.requirement_traceability | 13 (20) | 100% | 1 | 85% | FAIL |
| hallucinate_benefit | honesty.grounding | 20 (20) | 100% | 0 | 85% | ok |
| gimmick_title | structure.title_quality | 20 (20) | 100% | 0 | 90% | ok |
| prohibited_request | compliance.no_prohibited_requests | 20 (20) | 100% | 0 | 85% | ok |
| delete_process | process.contact_or_link | 0 (4) | 0% | 0 | 90% | too few |
| delete_process | structure.sections_present | 4 (4) | 100% | 0 | 90% | too few |
| remove_team_and_work_mode | evp.team_context | 7 (14) | 29% | 2 | 85% | FAIL |
| remove_team_and_work_mode | evp.work_mode_clarity | 6 (14) | 17% | 0 | 85% | FAIL |
| vague_benefits | evp.benefits_specific | 7 (11) | 100% | 0 | 85% | ok |
| remove_timeline | process.steps_and_timeline | 0 (4) | 0% | 0 | 85% | too few |
| strip_pay | pay.range_present | 4 (4) | 100% | 0 | 90% | too few |
| strip_pay | structure.sections_present | 4 (4) | 100% | 0 | 90% | too few |
| widen_pay_range | pay.range_width | 4 (4) | 100% | 0 | 90% | too few |

## Judge agreement

Categorical metrics: Cohen's κ vs the reference model. Ratio metrics: mean absolute error vs the reference (κ on binned ratios punishes near-boundary values). Self-consistency: same label (or ratio spread ≤ 0.2, about one bullet on a short list) across 3 reps.

| Metric | n | agreement | self-consistency | target | |
|---|---|---|---|---|---|
| structure.title_matches_content | 10 | κ 1 | 100% | κ ≥ 0.7 | ok |
| specific.responsibility_concreteness | 10 | MAE 0.07 | 100% | MAE ≤ 0.2 | ok |
| specific.requirement_traceability | 10 | MAE 0.18 | 80% | MAE ≤ 0.2 | FAIL |
| pay.context_present | 10 | κ 0.78 | 90% | κ ≥ 0.7 | ok |
| inclusive.proxy_requirements | 10 | κ 0 | 100% | κ ≥ 0.7 | FAIL |
| compliance.protected_grounds | 10 | κ 1 | 100% | κ ≥ 0.8 | ok |
| compliance.no_prohibited_requests | 10 | κ 1 | 100% | κ ≥ 0.8 | ok |
| evp.why_this_role | 10 | κ 0.40 | 70% | κ ≥ 0.7 | FAIL |
| evp.benefits_specific | 10 | κ 1 | 90% | κ ≥ 0.7 | ok |
| evp.team_context | 10 | κ 1 | 90% | κ ≥ 0.7 | ok |
| evp.work_mode_clarity | 10 | κ 1 | 100% | κ ≥ 0.7 | ok |
| process.steps_and_timeline | 10 | κ 1 | 100% | κ ≥ 0.7 | ok |

## Probes

| Probe | Expectation | composite | gates | result |
|---|---|---|---|---|
| empty | blocked, composite < 20 | 0 | fail (compliance.protected_grounds, compliance.ee_statement, compliance.no_prohibited_requests) | ok |
| i_dont_know | blocked or composite < 20 | 0 | fail (compliance.ee_statement) | ok |
| wrong_role_confident | structure.title_matches_content fails when judged; deterministic alone cannot catch | 91.80 | pass | ok |
| oracle_good_fixture | gates pass, composite >= 80 | 98.40 | pass | ok |

## Cost and latency

Judge calls: 20; mean input tokens 4727 (cache-read share 67%); mean output tokens 3451.25; mean latency 29.55 s. Normalize calls: 20, mean tokens 3389.25.
