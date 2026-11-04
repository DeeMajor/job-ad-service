import { z } from "zod";
import type { JobAd } from "./metrics/types.js";

/** No nullable/union fields: the API caps union-typed parameters at 16. Absent text = "", absent number = 0. */
export const JobAdSchema = z.object({
  title: z.string(),
  company_name: z.string().describe('"" if not stated'),
  company_about: z.string().describe('"" if not stated'),
  summary: z.string().describe('"" if not stated'),
  responsibilities: z.array(z.string()),
  must_have: z.array(z.string()),
  nice_to_have: z.array(z.string()),
  pay_min: z.number().describe("0 if not stated"),
  pay_max: z.number().describe("0 if not stated; equal to pay_min for a single figure"),
  pay_currency: z.string().describe('ISO code like ZAR, or "" if not stated'),
  pay_period: z.enum(["year", "month", "hour", "day", "week", "unspecified"]),
  pay_basis: z.string().describe('what determines placement in the range, or ""'),
  location: z.string().describe('"" if not stated'),
  work_mode: z.enum(["remote", "hybrid", "onsite", "unspecified"]),
  work_mode_detail: z.string().describe('e.g. "3 days in office", or ""'),
  benefits: z.array(z.string()),
  team: z.string().describe('who the person works with / reports to, or ""'),
  process: z.string().describe('application steps, rounds, timeline, or ""'),
  closing_date: z.string().describe('"" if not stated'),
  accessibility_statement: z.string().describe('"" if not stated'),
  ee_statement: z.string().describe('employment equity / affirmative action statement, or ""'),
  popia_notice: z.string().describe('personal-information / privacy notice, or ""'),
  apply_contact: z.string().describe('URL, email or instruction, or ""'),
  other: z.string().describe('text that fits no field, or ""'),
});

export function fromSchema(p: z.infer<typeof JobAdSchema>): JobAd {
  const t = (x: string): string | undefined => (x.trim() ? x.trim() : undefined);
  const hasPay = p.pay_min > 0 || p.pay_max > 0;
  return {
    title: p.title,
    company: t(p.company_name) || t(p.company_about) ? { name: t(p.company_name), about: t(p.company_about) } : undefined,
    summary: t(p.summary), responsibilities: p.responsibilities, must_have: p.must_have, nice_to_have: p.nice_to_have,
    pay: hasPay ? { min: p.pay_min || undefined, max: p.pay_max || p.pay_min || undefined, currency: t(p.pay_currency), period: p.pay_period === "unspecified" ? undefined : p.pay_period, basis: t(p.pay_basis) } : null,
    location: t(p.location), work_mode: p.work_mode, work_mode_detail: t(p.work_mode_detail), benefits: p.benefits, team: t(p.team),
    process: t(p.process), closing_date: t(p.closing_date), accessibility_statement: t(p.accessibility_statement), ee_statement: t(p.ee_statement),
    popia_notice: t(p.popia_notice), apply_contact: t(p.apply_contact), other: t(p.other),
  };
}

