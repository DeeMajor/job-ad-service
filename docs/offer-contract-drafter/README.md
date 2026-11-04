# Offer & contract drafter — planning pack (South Africa)

**Status: planning. Nothing built.** Agree the contract (01) and the rule table (02, `compliance-rules.yaml`) before code.

## Goal
From the hiring brief the ad was drafted from plus the agreed terms, produce an **offer letter** and an **employment contract** that
(a) contain every written particular the Basic Conditions of Employment Act (BCEA) s29 requires, (b) do not fall below any statutory
floor — National Minimum Wage (NMW), hours, overtime, leave, notice — or the applicable sectoral determination / bargaining council
agreement, (c) are consistent with the ad and the offer, and (d) are written in plain language the employee can understand (BCEA s29(3)
makes that a legal duty, not a style choice). Every finding carries the section of the Act it rests on.

## Design stance
- **Rules first, model second.** The particulars list and the floors are statute; they are checked in code with no model. The model only
  turns agreed terms into prose and drafts conditional clauses (probation, confidentiality, restraint, fixed-term justification).
- **Compliance is reported, never gated.** Same shape as the ad's `standard`: `compliant | review | not_compliant` with `must_fix /
  should_fix / could_improve`, each with the Act reference as evidence. The recruiter decides; the service explains.
- **Blind by placeholders.** The contract needs the employee's name, ID number and address; the service does not. It emits
  `{{employee.full_name}}`, `{{employee.id_number}}`, `{{employee.address}}` and the client merges them. The service never receives
  identity, consistent with the ranker, and holds no personal data beyond the 24-hour job record.
- **Rates live in a dated table, not in code.** NMW and the earnings threshold change every year; sectoral rates have their own gazettes.
  `compliance-rules.yaml` carries each figure with `effective_from`, `source` and `status: confirmed | verify`. A figure marked `verify`
  is reported as such in the response until someone confirms it against the gazette.
- **Template, not legal advice.** Every response says so. The clause library is reviewed once by a labour lawyer or consultant before
  Phase 2; that review is a deliverable, not an assumption.
- **Same service, same machinery.** `job_ad/offer/` next to `drafter/`, `publish/` and `shortlist/`; `POST /v1/offers/draft` (sync, one
  model call) and `POST /v1/offer-jobs` (async); spend cap, metrics, versions in `/healthz`; SciDLC log in `bench/experiments.md`.

## What we know and assume
- Jurisdiction South Africa: BCEA 75 of 1997 (as amended, incl. Labour Laws Amendment Act 2018 parental leave), National Minimum Wage
  Act 9 of 2018, Labour Relations Act 66 of 1995 (s198B fixed-term, Schedule 8 probation), Employment Equity Act, POPIA, UIF Act.
- Sectoral determinations and bargaining-council agreements override national floors in their sectors; the brief must say the sector.
- Assumption to confirm: offers and contracts are generated **after** the recruiter has decided, for one candidate, from the same brief
  the ad came from; pay is inside the advertised range unless the brief says otherwise (that mismatch is a `should_fix`).
- Assumption to confirm: the client merges identity placeholders and stores the signed document; the service stores nothing.

## Files
| File | What |
|---|---|
| `01-contract.md` | `OfferBrief` request, `OfferDraft` response (offer letter + contract as clauses and Markdown + compliance report) |
| `02-compliance-rules.md` | the rule table in prose: particular / floor, Act section, how it is checked, severity |
| `compliance-rules.yaml` | the same table machine-readable, with dated figures and `status` |
| `03-scidlc-plan.md` | phases, pre-registered metrics, free Phase 0 benchmark, costs |
