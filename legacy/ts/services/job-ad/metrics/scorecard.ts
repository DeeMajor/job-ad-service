import type { JobAd, MetricResult, Scorecard, ScoringContext } from "./types.js";
import { isGate, loadSpec, type Spec } from "./spec.js";
import { gatePasses, normalize, pickNorm } from "./normalize.js";
import { runDeterministic, type Raw } from "./deterministic/index.js";
import { runJudge, type JudgeOptions, type JudgeRun } from "./judge/index.js";

/**
 * Combine raw metric results into a Scorecard using the spec.
 * Missing metrics are recorded as "skipped" and excluded from the composite.
 */
export function buildScorecard(raws: Raw[], ctx: ScoringContext, spec: Spec = loadSpec()): Scorecard {
  const byId = new Map(raws.map((r) => [r.id, r]));
  const metrics: MetricResult[] = [];
  const gateFailures: string[] = [];
  const dimAcc: Record<string, { sum: number; n: number }> = {};

  for (const m of spec.metrics) {
    const r = byId.get(m.id);
    const base: MetricResult = { id: m.id, dimension: m.dimension, grader: m.grader, status: r?.status ?? "skipped", raw: r?.raw, pass: r?.pass, evidence: r?.evidence, reasoning: r?.reasoning };
    if (m.jurisdictions && !m.jurisdictions.some((j) => ctx.jurisdiction === j || ctx.jurisdiction.startsWith(j + "-")) && base.status === "ok") {
      base.status = "not_applicable";
      base.reasoning = `not in jurisdictions ${m.jurisdictions.join(",")}`;
    }
    if (base.status === "ok" && typeof base.raw === "number") {
      base.normalized = normalize(base.raw, pickNorm(m, ctx.channel), m.type);
      if (m.type === "pass_fail") base.pass = base.raw >= 1;
      if (isGate(spec, m, ctx as unknown as Record<string, unknown>)) {
        const passes = m.gate ? gatePasses(base.raw, m.gate) : base.raw >= 1;
        // a gate with its own clause and no band: pass/fail is the only meaningful normalisation (ratios keep their value)
        if (m.gate && !pickNorm(m, ctx.channel) && m.type !== "ratio") base.normalized = passes ? 1 : 0;
        if (!passes) { base.gate_failed = true; gateFailures.push(m.id); }
      }
      if (!spec.dimensions[m.dimension].gate) {
        const acc = (dimAcc[m.dimension] ??= { sum: 0, n: 0 });
        acc.sum += base.normalized; acc.n += 1;
      }
    }
    metrics.push(base);
  }

  const dimensions: Scorecard["dimensions"] = {};
  let weightSum = 0, weighted = 0;
  for (const [d, cfg] of Object.entries(spec.dimensions)) {
    const acc = dimAcc[d];
    if (!acc || acc.n === 0) { dimensions[d] = { score: 0, n: 0 }; continue; }
    const score = acc.sum / acc.n;
    dimensions[d] = { score, n: acc.n };
    weightSum += cfg.weight; weighted += cfg.weight * score;
  }
  const gatesPassed = gateFailures.length === 0;
  const compositeRaw = weightSum > 0 ? Math.round((weighted / weightSum) * 1000) / 10 : 0;
  const composite = gatesPassed ? compositeRaw : 0;
  const verdict: Scorecard["verdict"] = !gatesPassed ? "blocked" : composite >= spec.publish_threshold ? "publishable" : composite >= spec.review_threshold ? "review" : "regenerate";
  return { spec_version: spec.version, metrics, gates_passed: gatesPassed, gate_failures: gateFailures, composite, dimensions, verdict };
}

/** Deterministic-only scorecard (no network). Judge metrics appear as "skipped". */
export function scoreDeterministic(ad: JobAd, ctx: ScoringContext, spec = loadSpec()): Scorecard {
  return buildScorecard(runDeterministic(ad, ctx), ctx, spec);
}

/** Full scorecard: deterministic + judge. */
export async function score(ad: JobAd, ctx: ScoringContext, judgeOpts: JudgeOptions = {}, spec = loadSpec()): Promise<{ scorecard: Scorecard; judge: JudgeRun }> {
  const det = runDeterministic(ad, ctx);
  const judge = await runJudge(ad, ctx, judgeOpts);
  return { scorecard: buildScorecard([...det, ...judge.results], ctx, spec), judge };
}

export { runDeterministic, runJudge, loadSpec };
export * from "./types.js";
