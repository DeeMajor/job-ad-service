# What makes a good job ad — and how we measure it

A job ad is good when it gets the **right people to apply**, **quickly**, **without excluding anyone unfairly**, and **without promising anything untrue**. Everything below is a proxy for those four outcomes.

Two layers of metrics:

1. **Outcome metrics** (lagging, from the hiring funnel). These are the ground truth. They arrive days or weeks after publishing and cannot steer a draft in real time.
2. **Content metrics** (leading, computed on the text at draft time). These are what the scorer produces. Their weights are a hypothesis that Phase 5 of the SciDLC plan validates against the outcome metrics.

---

## 1. Outcome metrics (ground truth)

| Metric | Definition | Benchmark / note |
|---|---|---|
| Click-to-apply rate | applications started ÷ ad views | Industry mean about 6–7% (Appcast 2025/2026 benchmark, 379M clicks). |
| Application completion rate | applications submitted ÷ started | Mostly a form-length problem, but ads that set wrong expectations lose people here too. |
| Qualified applicant rate | applicants meeting must-haves ÷ applicants | The number recruiters actually feel. Too many unqualified applicants means vague requirements; too few means inflated ones. |
| Applicant pool diversity | gender / EE-group share of applicants vs the local labour pool | Direct test of the inclusivity metrics. |
| Time to first qualified applicant, time to fill | days | |
| Cost per qualified applicant | spend ÷ qualified applicants | Only when paid boards are used. |
| Recruiter edit distance | how much the human changed the AI draft before publishing | Cheap, immediate, and a strong signal of draft usefulness. Record on every publish. |

These require instrumenting the posting pipeline: `ad_id`, `variant_id`, `view`, `apply_start`, `apply_submit`, `screened_qualified`. Store them from day one even if the drafter is not live yet, so human-written ads provide a baseline.

---

## 2. Content metrics (the scorecard)

Seven dimensions. Each metric has an **id** (used in code and in `metrics.yaml`), a **grader** (deterministic code, lexicon, or LLM judge), and a **target**. Values are kept as separate columns; the composite is only for the UI.

### D1. Clarity and structure

| id | Metric | Grader | Target | Evidence / rationale |
|---|---|---|---|---|
| `structure.sections_present` | Required sections exist: title, about company, role summary, responsibilities, must-have requirements, nice-to-have, compensation, location/work mode, application process | deterministic (ad is structured JSON) | 9/9 | Missing salary, location or process are the top candidate complaints. |
| `structure.minimum_content` | Title, at least one responsibility, at least one requirement, at least 100 words | deterministic | pass — **hard gate** | Without it, metrics that reward the absence of bad things (no buzzwords, no gendered words) score an empty ad at 43. Found by the empty-ad probe in spec 0.1.8. |
| `structure.title_matches_content` | Title names the occupation the responsibilities describe | judge | pass | A misleading title wastes impressions and draws unqualified applicants. |
| `structure.title_quality` | Title is a standard searchable title, ≤ 60 chars, no internal level codes, no gimmick words ("ninja", "rockstar", "guru") | deterministic + lexicon | pass | Candidates search by standard titles; gimmick titles depress search impressions and skew the pool. |
| `clarity.word_count` | Total words | deterministic | 300–650 default; platform override (LinkedIn ≤ 300, Indeed 700–2000) | LinkedIn 4.5M-post study: 1–300 words got +8.4% applies per view; 301–600 words −3.4%. Indeed data favours longer posts. Keep continuous, apply band per channel. |
| `clarity.reading_grade` | Flesch–Kincaid grade level | deterministic | ≤ 9 (target 8) | Grade-8 level recommended for mixed first-language audiences; jargon-heavy postings get roughly 30% fewer applications. |
| `clarity.longest_sentence` | Words in the longest sentence | deterministic | ≤ 35 | Catches the single run-on sentence a document-level average hides. (Replaced mean sentence length in spec 0.1.1: the average was too insensitive to detect injected bloat in the benchmark.) |
| `clarity.scannability` | 1 − share of words sitting in prose paragraphs longer than 80 words | deterministic | ≥ 0.7 | Over half of LinkedIn views are mobile. |

### D2. Specificity and honesty

| id | Metric | Grader | Target | Evidence / rationale |
|---|---|---|---|---|
| `specific.responsibility_concreteness` | Share of responsibility bullets with action verb + object + context (what, for whom, how measured) | judge | ≥ 0.8 | Vague bullets ("support the team") lower qualified-applicant rate and raise unqualified volume. |
| `specific.must_have_count` | Number of must-have requirements | deterministic | 3–6 | LinkedIn: postings average 7 requirements; candidates meeting 4 of 7 are equally successful. Women tend to apply only at 100% match, so inflation skews the pool. |
| `specific.nice_to_have_split` | Must-haves and nice-to-haves are separated | deterministic | pass | Same evidence as above. |
| `specific.requirement_traceability` | Each *specific* must-have (tool, system, certification, licence, language, domain skill) is justified by a stated responsibility; generic education levels and experience bands are excluded (counted by `must_have_count` and `years_inflation` instead) | judge | ≥ 0.9 | Catches "Mandarin required" for a role that never uses it. Also the test for EE Act *inherent requirement*. (Spec 0.1.6: generic qualifications removed from the denominator after two models could not agree whether a commerce FETC "traces" to a sales role.) |
| `specific.years_inflation` | Any "N+ years" where N exceeds the taxonomy's typical range for the seniority | deterministic + taxonomy | 0 flags | Years are a weak proxy for skill and an age-discrimination risk. |
| `pay.range_present` | Salary or range disclosed | deterministic | pass | Pay transparency is the single strongest driver of apply rate in most studies, and mandatory in the EU from June 2026 and several US states. |
| `pay.range_width` | (max − min) ÷ min | deterministic | ≤ 0.30 | HBR (Feb 2026) and Cornell ILR (2026): wide ranges deter women specifically; adding how pay is set removes the gap. |
| `pay.context_present` | Ad explains what determines placement in the range | judge | pass | Same evidence. |
| `honesty.buzzword_density` | Buzzwords per 100 words (lexicon: "fast-paced", "work hard play hard", "wear many hats", "self-starter", "rockstar"...) | lexicon | ≤ 0.5 | Jargon correlates with lower applies and signals burnout culture. |
| `honesty.grounding` | Share of factual claims (benefits, salary, team size, tools, location, process) supported by a cited source in the brief or retrieved context | judge with citations | 1.00 — **hard gate** | The AI-specific risk: hallucinated benefits are a legal and trust problem. Unsupported claims must be removed, not softened. |

### D3. Inclusivity and fairness

| id | Metric | Grader | Target | Evidence / rationale |
|---|---|---|---|---|
| `inclusive.gender_coding` | Masculine-coded minus feminine-coded word count, normalised per 100 words (Gaucher, Friesen & Kay 2011 lexicons) | lexicon | between −1 and +1 (neutral) | Masculine-coded wording lowers women's intent to apply and their share of applications; the effect replicates in 2025 public-sector data. |
| `inclusive.exclusionary_terms` | Unambiguous proxies for protected grounds ("digital native", "recent graduate", "native English speaker", "able-bodied", "no family commitments", "under 35", gendered job titles) plus context patterns where an ambiguous word is applied to a person ("young, energetic leader"). Bare ambiguous words ("young company", "mature product", "single source of truth") are surfaced as review evidence only and left to the judge. | lexicon | 0 — **hard gate** | Direct EE Act s6 exposure. Smoke benchmark showed bare-word matching produced false gate failures on 10% of real ads. |
| `inclusive.proxy_requirements` | Requirements that exclude protected groups without being an inherent requirement (driver's licence for a desk job, "must be able to lift" for admin, specific degree where equivalent experience fits) | judge | 0 | Labour Appeal Court: an inherent requirement must be indispensable to the job. |
| `inclusive.accessibility_statement` | Ad states how to request accommodation and identifies inherent physical requirements, if any | deterministic | pass | Department of Labour guidance on accessible advertising. |
| `inclusive.candidate_address` | Second-person mentions ("you", "your") per 100 words, minus two for each third-person-candidate mention ("the ideal candidate", "the successful applicant") | deterministic | ≥ 1.0 | Direct address reads as inviting; "the ideal candidate" lists read as a filter. (Spec 0.1.4: was a ratio, which saturated on impersonal ads with zero third-person mentions.) |

### D4. Compliance (jurisdiction rule set, hard gates)

Rules live in `rag/compliance/<jurisdiction>.md` and are both retrieved into the prompt and checked after generation.

| id | South Africa rule | Grader |
|---|---|---|
| `compliance.protected_grounds` | No preference or exclusion on race, gender, sex, pregnancy, marital status, family responsibility, ethnic or social origin, colour, sexual orientation, age, disability, religion, HIV status, conscience, belief, political opinion, culture, language, birth (EEA s6) unless an inherent requirement is stated and justified | judge, citing the sentence |
| `compliance.ee_statement` | EE / affirmative-action statement present. A hard gate only when the employer is known to be a designated employer; otherwise scored in the process dimension (spec 0.1.7: the Act requires an EE plan, not a statement in the ad, and 4 of 5 real tech-company ads carried none) | deterministic |
| `compliance.popia_notice` | Applicant data processing notice or link present. Scored in the process dimension, not a gate: ATS-hosted ads carry it on the portal (85% of real SA bank ads lack it in the text). | deterministic |
| `compliance.no_prohibited_requests` | Does not ask for HIV status, pregnancy, criminal record (unless inherent and stated), photo, ID number at application stage | judge |
| `compliance.pay_disclosure_law` | Where the jurisdiction mandates a range (EU, CO/CA/NY/WA...), a range is present | deterministic |

Any compliance fail blocks publishing regardless of composite score.

### D5. Candidate value proposition

| id | Metric | Grader | Target |
|---|---|---|---|
| `evp.why_this_role` | The judge must quote the one sentence stating what the candidate will own, build, learn or grow into in this role; pass if one exists. Employer marketing does not qualify. | judge | pass |
| `evp.benefits_specific` | Benefits are concrete and grounded (not "competitive benefits") | judge | pass |
| `evp.team_context` | The judge must quote the title the person reports to, or a stated team size with a number; pass if either exists. Teams led, squads, tribes or stakeholders do not count. | judge | pass |
| `evp.work_mode_clarity` | Remote/hybrid/on-site and expected days stated unambiguously | deterministic + judge | pass |

### D6. Searchability

| id | Metric | Grader | Target |
|---|---|---|---|
| `seo.title_matches_taxonomy` | Title (or alternate title) exists in ESCO/OFO taxonomy | deterministic | pass |
| `seo.key_terms_early` | Role title, location and top 3 skills appear in the first 100 words | deterministic | pass |
| `seo.no_stuffing` | No skill or title repeated more than 4 times | deterministic | pass |

### D7. Process transparency

| id | Metric | Grader | Target |
|---|---|---|---|
| `process.steps_and_timeline` | Application steps, expected number of interview rounds, and a response or closing date | judge | pass |
| `process.contact_or_link` | A way to apply or ask questions | deterministic | pass |

---

## 3. Composite and the draft standard

```
composite = Σ weight_d × mean(normalised metrics in dimension d) × 100     — always computed, never zeroed
must_fix  = structure.minimum_content fails
         ∪ honesty.grounding < 1.0
         ∪ inclusive.exclusionary_terms > 0
         ∪ compliance.protected_grounds / no_prohibited_requests / pay_disclosure_law fail
         ∪ compliance.ee_statement fails when the employer is a known designated employer
level     = not_ready   if any must_fix, or composite < 60
          = review      if 60 ≤ composite < 75
          = publishable if composite ≥ 75 and no must_fix
```

The scorecard carries a `standard`: the level, a one-sentence summary, and reasons graded `must_fix` (legal, honesty, minimum content), `should_fix` (normalised < 0.5) and `could_improve` (0.5–0.8), each with a plain-language fix and quoted evidence. This replaced the earlier "gate → composite 0 → blocked" model (spec 0.1.9): zeroing the score threw away the information a recruiter needs to fix the ad, and "blocked" explained nothing. The must-fix set is exactly the old gate set; what changed is how it is reported, not what is checked.

Default dimension weights (hypothesis, to be re-fit in Phase 5):

| Dimension | Weight |
|---|---|
| D2 Specificity & honesty | 0.25 |
| D3 Inclusivity | 0.20 |
| D1 Clarity & structure | 0.20 |
| D5 Value proposition | 0.15 |
| D7 Process | 0.10 |
| D6 Searchability | 0.10 |
| D4 Compliance | must-fix only |

Normalisation: pass/fail → 1/0; counts and ratios → piecewise-linear to 0..1 around the target band (full score inside the band, linear decay outside, floor 0). Keep the raw value alongside the normalised one.

---

## 4. How the graders work

**Deterministic** (`metrics/deterministic/`): pure TypeScript, no network, unit-tested. Readability via a small Flesch–Kincaid implementation (syllable heuristics are good enough for English; log a note that the scorer is English-only for now). Lexicons are versioned JSON files: `gendered.json` (Gaucher 2011 stems), `buzzwords.json`, `exclusionary.json`. Lexicon changes are experiments too.

**Judge** (`metrics/judge/`): one `claude-sonnet-5` call per ad with structured output. The rubric is written as checkable claims, not scales. Each judged metric returns `{ value, evidence: string[] (quoted spans), reasoning }`. Grounding and compliance also return the offending sentence so the revision pass can target it. The judge sees the ad **and** the brief plus retrieved context, because grounding is relative to sources.

```ts
import Anthropic from "@anthropic-ai/sdk";
import { z } from "zod";
import { zodOutputFormat } from "@anthropic-ai/sdk/helpers/zod";

const JudgeMetric = z.object({
  value: z.number(),            // 0..1 for ratios, 0/1 for pass/fail, integer for counts
  evidence: z.array(z.string()),// quoted spans from the ad
  reasoning: z.string(),
});

export const JudgeOutput = z.object({
  specific_responsibility_concreteness: JudgeMetric,
  specific_requirement_traceability: JudgeMetric,
  honesty_grounding: JudgeMetric.extend({
    unsupported_claims: z.array(z.object({ claim: z.string(), sentence: z.string() })),
  }),
  inclusive_proxy_requirements: JudgeMetric,
  compliance_protected_grounds: JudgeMetric,
  // ...one entry per judge-graded id in metrics.yaml
});

export async function judge(client: Anthropic, input: { ad: string; brief: string; context: string }) {
  const res = await client.messages.parse({
    model: "claude-sonnet-5",
    max_tokens: 8000,
    system: [{ type: "text", text: JUDGE_SYSTEM_AND_RUBRIC, cache_control: { type: "ephemeral" } }],
    messages: [{ role: "user", content: renderJudgeInput(input) }],
    output_config: { format: zodOutputFormat(JudgeOutput) },
  });
  if (!res.parsed_output) throw new Error("judge output failed to parse");
  return res.parsed_output;
}
```

**Judge calibration** (SciDLC Phase 0, no humans): contrastive perturbations of real internet ads (the scorer must prefer the original on the targeted metric), agreement with a stronger reference model (κ ≥ 0.7, 0.8 for gate metrics), and three-run self-consistency ≥ 0.9. Null probes (empty ad, "I don't know", confident ad for the wrong role) must trip the gates. See `03-scidlc-plan.md` Phase 0.

---

## 5. What was considered and left out

- **"Describes a typical day/week"** (removed in spec 0.1.5): two models could not agree whether concrete recurring tasks count or only an explicit "a typical week" passage (κ 0.20), and it duplicated responsibility concreteness, which agrees at MAE 0.06.
- **Tone scales (1–5 "engaging")**: too subjective to calibrate; replaced by candidate-address ratio, buzzword density and EVP presence.
- **Keyword density vs competitors**: needs scraped competitor data; revisit if SEO becomes a measured problem.
- **Sentiment analysis**: no evidence it predicts applies.
- **Emoji / formatting style**: channel-specific; handled by the publishing layer, not the scorer.
- **Automatic bias detection models**: the Gaucher lexicon plus judge is auditable; a black-box classifier is not, and auditability matters for EE compliance.

## Sources

- Appcast, Recruitment Marketing Benchmark Report 2025 and 2026 (click-to-apply rates, completion-time effect).
- LinkedIn Talent Blog analysis of 4.5M posts (length vs apply rate); LinkedIn requirements study (7 listed, 4 sufficient).
- Gaucher, Friesen & Kay (2011), *Evidence That Gendered Wording in Job Advertisements Exists and Sustains Gender Inequality*, JPSP; 2025 replication *From Wording to Workforce* (public job ads).
- HBR (Feb 2026), *Posting a Wide Salary Range Can Deter Women from Applying*; Lee, Park & Chang (Cornell ILR, 2026), *The Implications of Pay Range Transparency*.
- Employment Equity Act 55 of 1998 s6 and s20(3); Labour Appeal Court jurisprudence on inherent requirements; Department of Employment and Labour EE guidance; POPIA.
- Pin.com 2026 analysis of 29,000 job descriptions (structure, readability).
