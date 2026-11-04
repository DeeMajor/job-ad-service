import { z } from "zod";
import type { JobAd, Jurisdiction, Channel } from "../metrics/types.js";

/**
 * HiringBrief v0.2 — the service's request contract.
 *
 * Everything the drafter may state as fact must come from here (Phase 1) or from retrieved, cited sources (Phase 2+).
 * Absent = not provided; the drafter may not fill the gap. Intake adapters (form, old-ad extraction, conversational agent)
 * all produce this object; the drafter, scorer and eval only ever see this.
 */
export const BRIEF_SCHEMA_VERSION = "0.2";

const Str = z.string().trim().min(1);
const IsoDate = z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "YYYY-MM-DD");

/** A requirement may carry the recruiter's justification: which duty needs it. Feeds traceability and the EE inherent-requirement defence. */
export const RequirementSchema = z.union([
  Str,
  z.object({ text: Str, justification: Str.optional() }),
]).transform((r) => (typeof r === "string" ? { text: r } : r));
export type Requirement = z.output<typeof RequirementSchema>;

export const HiringBriefSchema = z.object({
  schema_version: z.literal(BRIEF_SCHEMA_VERSION).default(BRIEF_SCHEMA_VERSION),

  // --- the role
  title: Str,
  seniority: z.enum(["entry", "junior", "mid", "senior", "lead", "manager", "head", "executive"]).optional(),
  employment_type: z.enum(["permanent", "fixed_term", "contract", "part_time", "internship", "learnership", "temporary"]).optional(),
  /** Why the role exists and what it is for; the drafter's raw material for "why this role". */
  purpose: Str.optional(),
  /** What good looks like at 3, 6 or 12 months; feeds concrete, measurable bullets. */
  success_measures: z.array(Str).default([]),
  responsibilities: z.array(Str).default([]),
  tools: z.array(Str).default([]),
  must_have: z.array(RequirementSchema).default([]),
  nice_to_have: z.array(RequirementSchema).default([]),

  // --- where, when, how much
  location: Str.optional(),
  work_mode: z.enum(["remote", "hybrid", "onsite"]).optional(),
  work_mode_detail: Str.optional(),
  hours: Str.optional(),                 // e.g. "Mon–Fri 08:00–17:00", "rotational shifts incl. weekends"
  start_date: IsoDate.optional(),
  positions: z.number().int().positive().optional(),
  pay: z.object({
    min: z.number().nonnegative().optional(),
    max: z.number().nonnegative().optional(),
    currency: z.string().length(3).default("ZAR"),
    period: z.enum(["year", "month", "hour", "day", "week"]),
    basis: Str.optional(),               // what determines placement in the range
  }).optional(),
  benefits: z.array(Str).default([]),

  // --- the people
  company: z.object({ name: Str, about: Str.optional() }),
  team: z.object({ reports_to: Str.optional(), size: z.number().int().positive().optional(), notes: Str.optional() }).optional(),

  // --- the process
  process: z.object({ steps: Str.optional(), closing_date: IsoDate.optional(), contact: Str.optional(), reference: Str.optional() }).optional(),
  statements: z.object({ ee: Str.optional(), popia: Str.optional(), accessibility: Str.optional() }).optional(),

  // --- scoring context
  jurisdiction: z.enum(["ZA", "EU", "US"]).or(z.string().regex(/^US-[A-Z]{2}$/)).default("ZA"),
  designated_employer: z.boolean().optional(),
  hosted_apply: z.boolean().default(false),
  channel: z.enum(["default", "linkedin", "indeed"]).default("default"),
});
export type HiringBriefInput = z.input<typeof HiringBriefSchema>;
export type HiringBrief = z.output<typeof HiringBriefSchema>;

/** Render the brief as the single SOURCE block the drafter and the grounding judge both see. */
export function renderBrief(b: HiringBrief): string {
  const L: string[] = [];
  const add = (k: string, v: string | number | undefined) => { if (v !== undefined && String(v).trim()) L.push(`${k}: ${String(v).trim()}`); };
  const list = (k: string, xs: string[]) => { if (xs.length) L.push(`${k}:\n${xs.map((x) => `  - ${x}`).join("\n")}`); };
  const reqs = (k: string, xs: Requirement[]) => list(k, xs.map((r) => (r.justification ? `${r.text} (needed because: ${r.justification})` : r.text)));
  add("Title", b.title);
  add("Seniority", b.seniority);
  add("Employment type", b.employment_type?.replace("_", " "));
  add("Positions", b.positions);
  add("Company", b.company.name);
  add("About the company", b.company.about);
  add("Purpose of the role", b.purpose);
  list("What success looks like", b.success_measures);
  list("Responsibilities (hiring manager's notes)", b.responsibilities);
  list("Tools and systems", b.tools);
  reqs("Must-have requirements", b.must_have);
  reqs("Nice-to-have", b.nice_to_have);
  add("Location", b.location);
  add("Work mode", b.work_mode ? `${b.work_mode}${b.work_mode_detail ? ` (${b.work_mode_detail})` : ""}` : undefined);
  add("Hours", b.hours);
  add("Start date", b.start_date);
  if (b.pay) add("Pay", `${b.pay.currency} ${b.pay.min ?? ""}${b.pay.max !== undefined && b.pay.max !== b.pay.min ? ` – ${b.pay.max}` : ""} per ${b.pay.period}${b.pay.basis ? `; basis: ${b.pay.basis}` : ""}`);
  list("Benefits", b.benefits);
  add("Reports to", b.team?.reports_to);
  add("Team size", b.team?.size);
  add("Team notes", b.team?.notes);
  add("Application process", b.process?.steps);
  add("Closing date", b.process?.closing_date);
  add("Reference", b.process?.reference);
  add("How to apply / contact", b.process?.contact);
  add("Employment equity statement", b.statements?.ee);
  add("POPIA notice", b.statements?.popia);
  add("Accessibility statement", b.statements?.accessibility);
  if (b.hosted_apply) L.push("Note: the ad will be published on a job board with its own Apply button.");
  return L.join("\n");
}

/**
 * Derive a brief from a structured real ad (the "paste your old ad" intake, and the Phase 1 eval).
 * Deliberately lossy: facts, not the real ad's prose.
 */
export function briefFromJobAd(ad: JobAd, opts: { jurisdiction?: Jurisdiction; hosted_apply?: boolean; channel?: Channel } = {}): HiringBrief {
  const u = (s?: string | null) => (s && s.trim() ? s.trim() : undefined);
  const date = (s?: string) => { if (!s) return undefined; const d = new Date(s); if (Number.isNaN(d.getTime())) return undefined; const p = (n: number) => String(n).padStart(2, "0"); return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`; };
  const pay = ad.pay && (ad.pay.min || ad.pay.max) && ad.pay.period ? { min: ad.pay.min, max: ad.pay.max ?? ad.pay.min, currency: ad.pay.currency && ad.pay.currency.length === 3 ? ad.pay.currency : "ZAR", period: ad.pay.period, basis: u(ad.pay.basis) } : undefined;
  return HiringBriefSchema.parse({
    title: ad.title,
    company: { name: ad.company?.name || "Unnamed employer", about: u(ad.company?.about) },
    purpose: u(ad.summary),
    responsibilities: ad.responsibilities,
    must_have: ad.must_have,
    nice_to_have: ad.nice_to_have,
    location: u(ad.location),
    work_mode: ad.work_mode && ad.work_mode !== "unspecified" ? ad.work_mode : undefined,
    work_mode_detail: u(ad.work_mode_detail),
    pay,
    benefits: ad.benefits,
    team: ad.team ? { notes: ad.team } : undefined,
    process: ad.process || ad.closing_date || ad.apply_contact ? { steps: u(ad.process), closing_date: date(ad.closing_date), contact: u(ad.apply_contact) } : undefined,
    statements: ad.ee_statement || ad.popia_notice || ad.accessibility_statement ? { ee: u(ad.ee_statement), popia: u(ad.popia_notice), accessibility: u(ad.accessibility_statement) } : undefined,
    jurisdiction: opts.jurisdiction ?? "ZA",
    hosted_apply: opts.hosted_apply ?? false,
    channel: opts.channel ?? "default",
  });
}
