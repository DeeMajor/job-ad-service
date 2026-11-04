import { describe, expect, it } from "vitest";
import { applyAll, PERTURBATIONS } from "../perturb.js";
import { scoreDeterministic } from "../../services/job-ad/metrics/scorecard.js";
import { GOOD_AD } from "../../services/job-ad/metrics/__tests__/fixtures.js";

const ZA = { jurisdiction: "ZA" as const, designated_employer: true };
const norm = (ad: typeof GOOD_AD, id: string) => scoreDeterministic(ad, ZA).metrics.find((m) => m.id === id)!.normalized;

describe("perturbations", () => {
  it("every perturbation applies to the good fixture", () => {
    expect(applyAll(GOOD_AD).map((p) => p.name).sort()).toEqual(PERTURBATIONS.map((p) => p.name).sort());
  });
  it("does not mutate the original", () => {
    const before = JSON.stringify(GOOD_AD);
    applyAll(GOOD_AD);
    expect(JSON.stringify(GOOD_AD)).toBe(before);
  });
  for (const p of PERTURBATIONS.filter((p) => !p.needs_judge)) {
    it(`${p.name} lowers ${p.targets.join(", ")} deterministically`, () => {
      const pa = p.apply(GOOD_AD)!;
      for (const t of p.targets) {
        const a = norm(GOOD_AD, t), b = norm(pa, t);
        expect(b, `${p.name} → ${t}: ${a} → ${b}`).toBeLessThan(a!);
      }
    });
  }
});
