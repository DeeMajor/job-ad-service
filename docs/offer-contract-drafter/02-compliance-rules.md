# Compliance rules — what is checked, against which section, and how

The machine-readable version is `compliance-rules.yaml` (v0.1.0). This page explains the structure and what still needs a person.

## Four kinds of rule

| Kind | Source | Check | Severity when it fails |
|---|---|---|---|
| **Particulars** (17) | BCEA s29(1)(a)–(q), s29(3) | the contract has a clause carrying each particular; identity particulars are placeholders | `must_fix` |
| **Floors** (≈30) | BCEA s9–s18 hours and rest, s20–s27 leave, s37 and s41 termination; NMW Act s4 and Schedules; BCEA s6(3) threshold; LRA s198B fixed-term; LRA Sch 8 probation; BCEA s43; EEA s6 | each term compared to the floor; sector or council floor replaces the national one where higher; hours/overtime rules switch off above the earnings threshold | `must_fix` for statute, `should_fix` for guidance, `could_improve` for common-law reasonableness |
| **Consistency** (5) | the HiringBrief the ad came from | title, pay range, work mode, location, employment type | `should_fix` |
| **Plain language** (4) | BCEA s29(3) | Flesch-Kincaid per clause; an explanation per clause; judge: explanation faithful, no invented obligations | `could_improve` / `should_fix` / `must_fix` |

Severity rolls up exactly as the ad's `standard` does: any `must_fix` → `not_compliant`; any `should_fix` → `review`; else `compliant`. Nothing is gated.

## How each floor is evaluated
- **Hourly equivalent.** Monthly pay → hourly: `amount × 12 / 52 / hours_per_week`; weekly → `/ hours_per_week`; daily → `/ hours_per_day`. The NMW compares against ordinary-hours pay only — allowances, bonuses, tips and payments in kind are excluded (NMWA s5).
- **Leave equivalence.** 21 consecutive days = 15 working days on a 5-day week = 18 on a 6-day week (BCEA s20(2)); the client may state any of the three.
- **Notice.** The contract may state one period; the check confirms it is at least the s37 floor for the longest service band the contract could reach (4 weeks), or states the statutory ladder.
- **Earnings threshold.** Derived from pay unless `earnings_threshold_override` is set. Above it, hours and overtime floors are not applied, the overtime-rate particular is waived, and the contract must still state the agreed hours.
- **Fixed term.** Over 3 months and below the threshold → a `justification` is required and must match one of the LRA s198B(4) reasons in substance (judge-assisted match, with the reason quoted).
- **Sector.** `terms.sector` selects the sectoral instrument; until its rates are loaded (`status: verify`) the national floor is applied and the finding says the sectoral floor was not checked.

## Figures and their status
Figures carry `effective_from`, `source` and `status`. **Confirmed** on this page as of writing: NMW R28.79/hour from 1 March 2025; earnings threshold R261 748.45/year from 1 April 2025; parental leave 10 days. **Verify before trusting**: the 2026 NMW adjustment (effective 1 March 2026), the 2026 earnings threshold (1 April 2026), EPWP and learnership rates, the UIF ceiling, every sectoral determination's current rates. A rule whose figure is `verify` still runs and is reported with `figures_to_verify` in the response so nobody mistakes it for a confirmed check. Updating a figure bumps `compliance-rules.yaml` version and is logged in `bench/experiments.md`.

## What a person must do once
1. Confirm the `verify` figures against the Government Gazette and record the gazette number as `source`.
2. Review the clause library (the fixed wording for probation, confidentiality, IP, restraint, fixed-term reason, retirement) with a labour practitioner. Model output never replaces that wording; it fills terms into it and explains it.
3. Decide which sectors the client actually hires in; only those get their sectoral tables loaded.
