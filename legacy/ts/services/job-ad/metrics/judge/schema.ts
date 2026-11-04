import { z } from "zod";

const Judged = z.object({
  value: z.number().describe("0 or 1 for pass/fail; 0..1 for ratios; integer for counts"),
  evidence: z.array(z.string()).describe("Short quoted spans from the ad that justify the value"),
  reasoning: z.string().describe("One or two sentences"),
});

/**
 * Counts and ratios are never asked for directly: the judge enumerates items and code does the arithmetic.
 * Pass/fail metrics use `pass`. This removes the "is 1 good or bad?" ambiguity that a bare number invites.
 */
const PassFail = z.object({
  pass: z.boolean(),
  evidence: z.array(z.string()).describe("Short quoted spans from the ad that justify the verdict"),
  reasoning: z.string().describe("One or two sentences"),
});

export const JudgeOutput = z.object({
  title_matches_content: PassFail.describe("PASS if the job title names the same occupation the responsibilities describe. FAIL if a reader of the title would expect materially different work (e.g. title 'Boilermaker', duties are accounts payable)."),
  responsibilities: z.object({
    total: z.number().int().describe("Number of responsibility bullets in the ad"),
    concrete: z.array(z.string()).describe("Bullets that contain BOTH a specific activity verb (prepare, reconcile, call, repair, approve…) AND a specific object (which report, which customers, which system). Category labels ('Customer Experience', 'Risk Management'), outcomes without activity ('Ensure compliance'), and vague verbs ('support', 'assist', 'contribute') are NOT concrete. Quote each concrete bullet."),
    reasoning: z.string(),
  }),
  specific_requirements: z.object({
    items: z.array(z.object({
      requirement: z.string().describe("The must-have, quoted"),
      supporting_responsibility: z.string().describe("The stated responsibility that names the activity this requirement serves, quoted; \"\" if none does"),
    })).describe("Only SPECIFIC must-haves: named tools, systems, certifications, licences, languages, domain skills, regulatory prerequisites. EXCLUDE generic education levels (matric, FETC, degree, postgraduate), years-of-experience bands, and soft traits (attention to detail, communication) — those are measured elsewhere. Regulatory prerequisites the ad names as such (FAIS fit-and-proper, SANC registration) are supported by any duty in that regulated activity."),
    reasoning: z.string(),
  }),
  pay_context_present: PassFail.describe("If pay is disclosed, the ad says what determines placement in the range. FAIL if no pay disclosed."),
  grounding: z.object({
    factual_claims_total: z.number().int().describe("Number of factual claims about employer, pay, benefits, location, work mode, team, process or legal status. 0 if no SOURCE blocks were provided."),
    unsupported_claims: z.array(z.object({ claim: z.string(), sentence: z.string() })).describe("Claims no SOURCE block states. Empty if no SOURCE blocks were provided."),
    reasoning: z.string(),
  }),
  proxy_requirements: z.object({
    items: z.array(z.string()).describe("Requirements that would exclude a protected group (EEA s6: age, disability, family responsibility, language, origin, religion, gender, HIV status…) without being an inherent requirement of the work described: e.g. driving licence or own vehicle for a desk role, age ranges, a maximum years-of-experience ceiling, 'recent graduate', physical fitness for sedentary work, citizenship where no legal need is stated, a home language rather than a proficiency. NOT proxies: credit and criminal checks or FAIS fit-and-proper for regulated financial roles, a professional registration the work legally requires, a proficiency in a language the duties use. Quote each. Empty array if none."),
    reasoning: z.string(),
  }),
  protected_grounds_ok: PassFail.describe("PASS if no stated or implied preference/exclusion on race, gender, sex, pregnancy, marital status, family responsibility, ethnic or social origin, colour, sexual orientation, age, disability, religion, HIV status, conscience, belief, political opinion, culture, language, birth, unless an inherent requirement is stated and justified. A lawful Employment Equity preference statement is PASS."),
  no_prohibited_requests: PassFail.describe("PASS if the ad does not ask applicants for HIV status, pregnancy, criminal record (unless inherent and stated), photograph, ID number, marital status, religion, or medical information at application stage"),
  why_this_role: z.object({
    role_specific_draw: z.string().describe("Quote the ONE sentence that tells the candidate what they will own, build, change, learn or grow into in THIS role (e.g. 'you will own the weekly payment run', 'build and grow the Islamic banking franchise', 'a path to team lead within two years'). \"\" if no such sentence exists. Sentences about the employer in general ('exciting opportunity', 'dynamic environment', 'make a difference', company history, values) do NOT qualify."),
    reasoning: z.string(),
  }),
  evp_benefits_specific: PassFail.describe("Benefits are concrete (named items, amounts, days) rather than 'competitive' or 'market-related'"),
  team_context: z.object({
    reports_to: z.string().describe("The job title or role this person REPORTS TO, quoted from the ad (e.g. 'Finance Supervisor', 'Head of Retail Credit'); \"\" if the ad never states who the person reports to. Teams the person leads, works with or sits in do NOT count."),
    team_size: z.string().describe("A stated NUMBER of people in the immediate team this person joins or leads, quoted (e.g. 'team of six', '12 consultants'); \"\" if no number is given. 'Squads', 'tribes', 'DevOps team', 'a team of consultants' without a number do NOT count."),
    reasoning: z.string(),
  }),
  evp_work_mode_clarity: PassFail.describe("Remote/hybrid/on-site and expected office days (if hybrid) are unambiguous"),
  process_steps_and_timeline: PassFail.describe("Application steps, number or type of interview rounds, and a response or closing date are stated"),
});
export type JudgeOutput = z.infer<typeof JudgeOutput>;

export const JUDGE_METRIC_IDS = [
  "structure.title_matches_content", "specific.responsibility_concreteness", "specific.requirement_traceability", "pay.context_present",
  "honesty.grounding", "inclusive.proxy_requirements", "compliance.protected_grounds", "compliance.no_prohibited_requests",
  "evp.why_this_role", "evp.benefits_specific", "evp.team_context", "evp.work_mode_clarity", "process.steps_and_timeline",
] as const;
