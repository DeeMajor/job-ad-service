import { describe, expect, it } from "vitest";
import { briefFromJobAd, HiringBriefSchema, renderBrief } from "../brief.js";
import { GOOD_AD, BAD_AD } from "../../metrics/__tests__/fixtures.js";
import { scoringContextFor } from "../draft.js";

describe("HiringBrief v0.2", () => {
  it("derives a brief from a structured ad", () => {
    const b = briefFromJobAd(GOOD_AD, { hosted_apply: false });
    expect(b.schema_version).toBe("0.2");
    expect(b.title).toBe("Accounts Payable Clerk");
    expect(b.pay).toEqual({ min: 18000, max: 22000, currency: "ZAR", period: "month", basis: expect.stringMatching(/Placement/) });
    expect(b.must_have).toHaveLength(3); expect(b.must_have[0]).toEqual({ text: expect.stringMatching(/Two or more years/) });
    expect(b.statements?.ee).toMatch(/designated employer/);
    expect(b.process?.closing_date).toBe("2026-11-30");
  });
  it("renders every provided fact and nothing for absent ones", () => {
    const t = renderBrief(briefFromJobAd(GOOD_AD));
    expect(t).toMatch(/^Title: Accounts Payable Clerk/m);
    expect(t).toMatch(/Pay: ZAR 18000 – 22000 per month; basis:/);
    expect(t).toMatch(/Must-have requirements:\n  - Two or more years/);
    const thin = renderBrief(briefFromJobAd({ ...BAD_AD, pay: null, process: undefined }));
    expect(thin).not.toMatch(/^Pay:/m);
    expect(thin).not.toMatch(/Application process/);
  });
  it("accepts a minimal brief and a rich one with justified requirements", () => {
    const min = HiringBriefSchema.parse({ title: "Driver", company: { name: "Acme" } });
    expect(min.work_mode).toBeUndefined(); expect(min.must_have).toEqual([]); expect(min.jurisdiction).toBe("ZA");
    const rich = HiringBriefSchema.parse({
      title: "Delivery Driver", company: { name: "Acme" }, seniority: "mid", employment_type: "permanent",
      purpose: "Keep 40 pharmacies stocked daily", success_measures: ["98% on-time deliveries"],
      must_have: [{ text: "Code 10 licence with PDP", justification: "drives a 4-ton truck daily" }, "Clean driving record"],
      pay: { min: 14000, max: 16000, period: "month" }, team: { reports_to: "Fleet Supervisor", size: 12 },
      process: { closing_date: "2026-12-15" }, hours: "Mon–Sat 06:00–15:00",
    });
    expect(rich.must_have[0]).toEqual({ text: "Code 10 licence with PDP", justification: "drives a 4-ton truck daily" });
    expect(rich.must_have[1]).toEqual({ text: "Clean driving record" });
    expect(renderBrief(rich)).toMatch(/Code 10 licence with PDP \(needed because: drives a 4-ton truck daily\)/);
    expect(renderBrief(rich)).toMatch(/Team size: 12/);
  });
  it("rejects malformed input with useful issues", () => {
    const r = HiringBriefSchema.safeParse({ title: "", company: {}, pay: { min: 1, period: "fortnight" }, process: { closing_date: "15/12/2026" } });
    expect(r.success).toBe(false);
    const paths = r.success ? [] : r.error.issues.map((i) => i.path.join("."));
    expect(paths).toEqual(expect.arrayContaining(["title", "company.name", "pay.period", "process.closing_date"]));
  });
  it("scoring context uses the brief as the only source", () => {
    const ctx = scoringContextFor(briefFromJobAd(GOOD_AD, { hosted_apply: true }));
    expect(ctx.sources).toHaveLength(1); expect(ctx.sources![0].id).toBe("brief");
    expect(ctx.hosted_apply).toBe(true); expect(ctx.jurisdiction).toBe("ZA");
  });
});
