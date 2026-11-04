# Judge cross-check vs claude-opus-5 — baseline, 20 drafts

| Metric | n | agreement | note |
|---|---|---|---|
| structure.title_matches_content | 20 | agree 100% | κ 1.00 → ok |
| specific.responsibility_concreteness | 20 | MAE 0.07 | target ≤ 0.2 → ok |
| specific.requirement_traceability | 13 | MAE 0.04 | target ≤ 0.2 → ok **(deferred from Phase 0)** |
| pay.context_present | 20 | agree 100% | rare positives: % agreement → ok |
| honesty.grounding | 20 | MAE 0.00 | target ≤ 0.2 → ok |
| inclusive.proxy_requirements | 20 | agree 90% | rare positives: % agreement → ok |
| compliance.protected_grounds | 20 | agree 100% | κ 1.00 → ok |
| compliance.no_prohibited_requests | 20 | agree 100% | κ 1.00 → ok |
| evp.why_this_role | 20 | agree 75% | κ 0.42 → FAIL **(deferred from Phase 0)** |
| evp.benefits_specific | 20 | agree 100% | rare positives: % agreement → ok |
| evp.team_context | 20 | agree 100% | κ 1.00 → ok **(deferred from Phase 0)** |
| evp.work_mode_clarity | 20 | agree 100% | κ 1.00 → ok |
| process.steps_and_timeline | 20 | agree 100% | rare positives: % agreement → ok |

## Disagreements on the deferred metrics

- **case_000 · evp.why_this_role** judge=0.00 ref=1.00
  - judge: No sentence describes what the candidate will specifically own, build, or grow into in this particular role.
  - ref: This sentence states what the candidate will own and grow in this specific role.
- **case_005 · evp.why_this_role** judge=0.00 ref=1.00
  - judge: The ad describes general support duties and impact but no sentence states what the candidate will specifically own, build, or grow into.
  - ref: This sentence states what the candidate's own work will change in this role rather than praising the employer.
- **case_009 · specific.requirement_traceability** judge=0.75 ref=1.00
  - judge: 3/4 specific requirements traceable (generic education and experience bands excluded). Most named technical requirements are directly tied to corresponding duties, except the generic 'development experience' list which lacks a matching specific duty.
  - ref: 4/4 specific requirements traceable (generic education and experience bands excluded). All four specific technical must-haves map to named duties in the responsibilities list.
- **case_014 · specific.requirement_traceability** judge=0.75 ref=1.00
  - judge: 3/4 specific requirements traceable (generic education and experience bands excluded). Named tools and domain experience are mostly traceable to specific responsibility bullets, except the Global Markets product exposure which has no matching duty.
  - ref: 4/4 specific requirements traceable (generic education and experience bands excluded). Named tool, platform and domain must-haves each map to a stated duty; degree and years bands excluded.
- **case_017 · evp.why_this_role** judge=0.00 ref=1.00
  - judge: The ad describes duties and requirements but contains no sentence framing what the candidate will personally own, build, or grow into.
  - ref: This sentence states what the candidate will learn and the accreditation they will gain in this role.
- **case_018 · evp.why_this_role** judge=0.00 ref=1.00
  - judge: No sentence describes what the candidate will personally own, build or grow into beyond generic duty descriptions.
  - ref: This names concrete role-specific learning the adviser will gain, unlike the generic employer blurb.
- **case_019 · evp.why_this_role** judge=0.00 ref=1.00
  - judge: No sentence describes what the candidate will personally own, build, or grow into in this specific role.
  - ref: This sentence states what the person will learn and become accredited for in this role.
