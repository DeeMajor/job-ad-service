/**
 * Contrastive perturbations. Each degrades a structured ad along ONE metric.
 * The scorer must score the original above the perturbed copy on `targets`.
 * `direction: "lower"` means the perturbed ad's normalised value must be lower than the original's.
 */
import type { JobAd } from "../services/job-ad/metrics/types.js";

export interface Perturbation {
  name: string;
  /** Metric ids whose normalised score must drop. */
  targets: string[];
  /** true if this perturbation needs the LLM judge to be detected. */
  needs_judge: boolean;
  /** Returns undefined when the perturbation does not apply to this ad (e.g. no pay to strip). */
  apply(ad: JobAd): JobAd | undefined;
  /** For grounding: the original ad text acts as the source; the injected claim is unsupported. */
  uses_original_as_source?: boolean;
}

const clone = <T>(x: T): T => JSON.parse(JSON.stringify(x));
const wordsIn = (ad: JobAd): number => (JSON.stringify(ad).match(/[a-zA-Z][a-zA-Z'’-]*/g) ?? []).length;

export const PERTURBATIONS: Perturbation[] = [
  {
    name: "strip_pay", targets: ["pay.range_present", "structure.sections_present"], needs_judge: false,
    apply: (ad) => (ad.pay && (ad.pay.min || ad.pay.max) ? { ...clone(ad), pay: null } : undefined),
  },
  {
    name: "widen_pay_range", targets: ["pay.range_width"], needs_judge: false,
    apply: (ad) => (ad.pay?.min && ad.pay?.max && (ad.pay.max - ad.pay.min) / ad.pay.min <= 0.3 ? { ...clone(ad), pay: { ...ad.pay, min: Math.round(ad.pay.min * 0.6), max: Math.round(ad.pay.max * 1.6) } } : undefined),
  },
  {
    name: "inflate_must_haves", targets: ["specific.must_have_count"], needs_judge: false,
    apply: (ad) => {
      if (ad.must_have.length > 6) return undefined;
      const extras = ["Bachelor's degree in a relevant field", "Advanced Excel skills", "Excellent written and verbal communication", "Proven track record of exceeding targets", "Valid driver's licence and own reliable transport", "Strong attention to detail", "Ability to work independently and in a team", "Willingness to travel", "Professional registration with the relevant body"];
      const target = Math.max(ad.must_have.length + 4, 9); // always overshoot the 3–6 band
      return { ...clone(ad), must_have: [...ad.must_have, ...extras.slice(0, target - ad.must_have.length)] };
    },
  },
  {
    name: "merge_nice_to_haves", targets: ["specific.nice_to_have_split"], needs_judge: false,
    apply: (ad) => (ad.nice_to_have.length > 0 ? { ...clone(ad), must_have: [...ad.must_have, ...ad.nice_to_have], nice_to_have: [] } : undefined),
  },
  {
    name: "inflate_years", targets: ["specific.years_inflation"], needs_judge: false,
    apply: (ad) => ({ ...clone(ad), must_have: [...ad.must_have, "Minimum 12+ years of experience in a similar role"] }),
  },
  {
    name: "inject_masculine_coding", targets: ["inclusive.gender_coding"], needs_judge: false,
    apply: (ad) => {
      // scale with ad length so the whole ad reads masculine-coded, not one sentence in a long ad
      const n = Math.max(1, Math.ceil(wordsIn(ad) / 200));
      const sentence = "We want an aggressive, competitive, dominant and decisive leader who is independent, assertive, fearless and ambitious, a self-confident and headstrong individual.";
      return { ...clone(ad), summary: `${ad.summary ?? ""} ${Array(n).fill(sentence).join(" ")}`.trim() };
    },
  },
  {
    name: "inject_exclusionary_phrase", targets: ["inclusive.exclusionary_terms"], needs_judge: false,
    apply: (ad) => ({ ...clone(ad), must_have: [...ad.must_have, "Young, energetic recent graduate"] }),
  },
  {
    name: "inject_buzzwords", targets: ["honesty.buzzword_density"], needs_judge: false,
    apply: (ad) => ({ ...clone(ad), summary: `${ad.summary ?? ""} This is an exciting opportunity for a passionate self-starter and team player who thrives under pressure in our fast-paced, dynamic environment. We work hard play hard, wear many hats, and need a rockstar who can hit the ground running and think outside the box.`.trim() }),
  },
  {
    name: "third_person_candidate", targets: ["inclusive.candidate_address"], needs_judge: false,
    apply: (ad) => {
      const c = clone(ad);
      const swap = (s: string) => s
        .replace(/\byou will\b/gi, "the ideal candidate will").replace(/\byou'll\b/gi, "the successful applicant will").replace(/\byou are\b/gi, "the ideal candidate is")
        .replace(/\byou have\b/gi, "the candidate has").replace(/\byou're\b/gi, "the ideal candidate is").replace(/\byourself\b/gi, "the candidate")
        .replace(/\byour\b/gi, "the candidate's").replace(/\byou\b/gi, "the ideal candidate");
      c.summary = c.summary ? swap(c.summary) : "";
      // impersonal ads have no "you" to swap; the degradation must still introduce third-person candidate language
      c.summary = `${c.summary} The ideal candidate will be responsible for the duties below. The successful applicant must meet all requirements. The candidate will report to the manager.`.trim();
      c.responsibilities = c.responsibilities.map(swap);
      c.must_have = c.must_have.map(swap);
      c.nice_to_have = c.nice_to_have.map(swap);
      c.benefits = c.benefits.map(swap);
      for (const k of ["team", "process", "other", "work_mode_detail"] as const) if (c[k]) c[k] = swap(c[k]!);
      if (c.company?.about) c.company.about = swap(c.company.about);
      return c;
    },
  },
  {
    name: "delete_process", targets: ["process.contact_or_link", "structure.sections_present"], needs_judge: false,
    apply: (ad) => (ad.process ? { ...clone(ad), process: undefined, apply_contact: undefined, closing_date: undefined } : undefined),
  },
  {
    name: "bloat_prose", targets: ["clarity.reading_grade", "clarity.longest_sentence", "clarity.scannability"], needs_judge: false,
    apply: (ad) => {
      // a real wall of text: one ~90-word paragraph per 300 words of ad, so the perturbation leaves the "good" band on long ads too
      const n = Math.max(1, Math.ceil(wordsIn(ad) / 300));
      const para = "Notwithstanding the aforementioned considerations, the organisation's multidimensional operational infrastructure necessitates comprehensive cross-functional collaboration methodologies that facilitate the optimisation of stakeholder-oriented deliverables across heterogeneous institutional environments, thereby engendering sustainable competitive differentiation through the systematic institutionalisation of performance-enhancing organisational capabilities and the concomitant realisation of strategically aligned transformational imperatives in accordance with internationally recognised governance frameworks and contemporary best-practice paradigms that are continuously benchmarked against industry-leading exemplars. Furthermore, it is incumbent upon all prospective incumbents to internalise the multifaceted strategic imperatives articulated herein, inasmuch as the successful operationalisation of said imperatives constitutes a sine qua non for the attainment of the organisation's overarching objectives, the realisation of which is predicated upon the harmonious integration of disparate functional competencies within a cohesive and synergistic operating model.";
      return { ...clone(ad), company: { ...ad.company, about: [ad.company?.about ?? "", ...Array(n).fill(para)].filter(Boolean).join("\n\n") } };
    },
  },
  {
    name: "gimmick_title", targets: ["structure.title_quality"], needs_judge: false,
    apply: (ad) => ({ ...clone(ad), title: `${ad.title} Rockstar Ninja (Grade 5)` }),
  },
  {
    name: "strip_ee_popia", targets: ["compliance.ee_statement", "compliance.popia_notice"], needs_judge: false,
    apply: (ad) => (ad.ee_statement || ad.popia_notice ? { ...clone(ad), ee_statement: undefined, popia_notice: undefined } : undefined),
  },
  // ---- judge-detected
  {
    name: "hallucinate_benefit", targets: ["honesty.grounding"], needs_judge: true, uses_original_as_source: true,
    apply: (ad) => ({ ...clone(ad), benefits: [...ad.benefits, "Fully paid medical aid for you and your whole family, plus a R50,000 annual education bursary and a company car"] }),
  },
  {
    name: "vague_responsibilities", targets: ["specific.responsibility_concreteness"], needs_judge: true,
    apply: (ad) => (ad.responsibilities.length ? { ...clone(ad), responsibilities: ["Support the team with various tasks", "Assist management as required", "Other duties as assigned", "Contribute to the success of the business"] } : undefined),
  },
  {
    name: "untraceable_requirements", targets: ["specific.requirement_traceability"], needs_judge: true,
    apply: (ad) => ({ ...clone(ad), must_have: [...ad.must_have, "Fluent in Mandarin", "Scuba diving certification", "Forklift operator licence", "Grade 2 piano certificate", "Commercial pilot's licence"] }),
  },
  {
    name: "proxy_requirement", targets: ["inclusive.proxy_requirements", "compliance.protected_grounds"], needs_judge: true,
    apply: (ad) => ({ ...clone(ad), must_have: [...ad.must_have, "Must be between 25 and 35 years old", "No family commitments that would interfere with overtime", "Must be a practising Christian"] }),
  },
  {
    name: "prohibited_request", targets: ["compliance.no_prohibited_requests"], needs_judge: true,
    apply: (ad) => ({ ...clone(ad), process: `${ad.process ?? "Apply with your CV."} Attach a recent photograph, a certified copy of your ID, proof of HIV status and your marital certificate.` }),
  },
  {
    name: "vague_benefits", targets: ["evp.benefits_specific"], needs_judge: true,
    apply: (ad) => (ad.benefits.length ? { ...clone(ad), benefits: ["Competitive salary", "Market-related benefits", "Great culture"] } : undefined),
  },
  {
    name: "remove_team_and_work_mode", targets: ["evp.team_context", "evp.work_mode_clarity"], needs_judge: true,
    apply: (ad) => {
      if (!(ad.team || (ad.work_mode && ad.work_mode !== "unspecified"))) return undefined;
      const c = clone(ad);
      const scrub = (s: string) => s.replace(/[^.•\n]*\b(report(?:s|ing)? (?:directly )?(?:to|into)|reporting line|line manager|team of \d+|join(?:s|ing)? (?:the|our) [^.•\n]*team|part of (?:the|our) [^.•\n]*team|hybrid|remote|on-?site|in[- ]the[- ]office|office[- ]based|work from home|days? (?:in|at) the office|(?:our |the )?office is (?:in|located|based)|based (?:in|at) our [^.•\\n]*office|from our [^.•\\n]*office)\b[^.•\n]*[.•\n]?/gi, " ").replace(/\s{2,}/g, " ").trim();
      c.team = undefined; c.work_mode = "unspecified"; c.work_mode_detail = undefined;
      for (const k of ["summary", "process", "other", "location"] as const) if (c[k]) c[k] = scrub(c[k]!) || undefined;
      if (c.company?.about) c.company.about = scrub(c.company.about) || undefined;
      c.responsibilities = c.responsibilities.map(scrub).filter(Boolean);
      c.benefits = c.benefits.map(scrub).filter(Boolean);
      return c;
    },
  },
  {
    name: "remove_timeline", targets: ["process.steps_and_timeline"], needs_judge: true,
    apply: (ad) => (ad.process ? { ...clone(ad), process: "Apply now.", closing_date: undefined } : undefined),
  },
];

export function applyAll(ad: JobAd): { name: string; perturbation: Perturbation; ad: JobAd }[] {
  const out: { name: string; perturbation: Perturbation; ad: JobAd }[] = [];
  for (const p of PERTURBATIONS) {
    const pa = p.apply(ad);
    if (pa) out.push({ name: p.name, perturbation: p, ad: pa });
  }
  return out;
}
