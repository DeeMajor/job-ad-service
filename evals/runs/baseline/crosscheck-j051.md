# Judge 0.5.1 re-check vs stored claude-opus-5 labels — baseline, 20 drafts

| Metric | n | agreement | note |
|---|---|---|---|
| structure.title_matches_content | 20 | agree 100% | κ 1.00 → ok |
| specific.responsibility_concreteness | 20 | MAE 0.16 | ok |
| specific.requirement_traceability | 12 | MAE 0.05 | ok **(deferred)** |
| pay.context_present | 20 | agree 100% | rare positives → ok |
| honesty.grounding | 20 | MAE 0.00 | ok |
| inclusive.proxy_requirements | 20 | agree 90% | rare positives → ok |
| compliance.protected_grounds | 20 | agree 100% | κ 1.00 → ok |
| compliance.no_prohibited_requests | 20 | agree 100% | κ 1.00 → ok |
| evp.why_this_role | 20 | agree 85% | κ 0.58 → FAIL **(deferred)** |
| evp.benefits_specific | 20 | agree 100% | rare positives → ok |
| evp.team_context | 20 | agree 100% | κ 1.00 → ok **(deferred)** |
| evp.work_mode_clarity | 20 | agree 100% | κ 1.00 → ok |
| process.steps_and_timeline | 20 | agree 100% | rare positives → ok |

## Remaining disagreements on why_this_role

- **case_000** judge=0 ref=1
  - judge: No sentence offers ownership, learning, accreditation, or a growth path specific to this role.
  - ref: This sentence states what the candidate will own and grow in this specific role.
- **case_005** judge=0 ref=1
  - judge: No sentence offers the candidate ownership, learning, accreditation, or a growth path specific to this role.
  - ref: This sentence states what the candidate's own work will change in this role rather than praising the employer.
- **case_014** judge=0 ref=1
  - judge: No sentence offers the candidate specific ownership, learning, accreditation, or growth path beyond general role description.
  - ref: This sentence states the ownership and technical authority the candidate takes on in this role.
