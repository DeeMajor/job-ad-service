/**
 * Phase 0 benchmark runner.
 *
 *   tsx bench/run.ts --version v1 [--run r2] [--normalizer llm|heuristic] [--judge on|off] [--limit N]
 *                    [--judge-model claude-sonnet-5] [--reference-model claude-opus-5] [--reps 3] [--agreement-sample 40] [--concurrency 6]
 *
 * Reads  bench/data/raw/<version>/ads.jsonl
 * Writes bench/data/out/<version>/normalized.jsonl (shared across runs: the normaliser rarely changes)
 *    and bench/data/out/<version>/<run>/{scores.jsonl, perturbations.jsonl, agreement.jsonl, report.json, report.md}
 * A new judge prompt or spec version = a new --run name, so earlier results stay comparable.
 *
 * Without an API key: --normalizer heuristic --judge off runs the deterministic half end to end.
 */
import fs from "node:fs";
import path from "node:path";
import Anthropic from "@anthropic-ai/sdk";
import type { JobAd, Scorecard, ScoringContext } from "../services/job-ad/metrics/types.js";
import { buildScorecard, loadSpec, runDeterministic, runJudge } from "../services/job-ad/metrics/scorecard.js";
import { renderAd } from "../services/job-ad/metrics/text.js";
import { JUDGE_PROMPT_VERSION } from "../services/job-ad/metrics/judge/prompt.js";
import type { RawAd } from "./fetch.js";
import { normalizeHeuristic, normalizeLLM } from "./normalize.js";
import { PERTURBATIONS } from "./perturb.js";
import { EMPTY_AD, GOOD_AD } from "../services/job-ad/metrics/__tests__/fixtures.js";

const a = parseArgs(process.argv.slice(2));
const VERSION = a.version ?? "v1";
const NORMALIZER = (a.normalizer ?? "llm") as "llm" | "heuristic";
const JUDGE = (a.judge ?? "on") === "on";
const LIMIT = a.limit ? Number(a.limit) : Infinity;
const JUDGE_MODEL = a["judge-model"] ?? "claude-sonnet-5";
const REF_MODEL = a["reference-model"] ?? "claude-opus-5";
const REPS = Number(a.reps ?? 3);
const AGREEMENT_SAMPLE = Number(a["agreement-sample"] ?? 40);
const CONCURRENCY = Number(a.concurrency ?? 6);
const RUN = a.run ?? "r1";
const RAW = path.join("bench/data/raw", VERSION, "ads.jsonl");
const OUT_SHARED = path.join("bench/data/out", VERSION);
const OUT = path.join(OUT_SHARED, RUN);
const TARGETS = { det: 0.9, judge: 0.85, kappa: 0.7, kappa_gate: 0.8, mae: 0.2, consistency: 0.9, judge_noise: 0.1, ratio_spread: 0.2 };

const spec = loadSpec();
const client = JUDGE || NORMALIZER === "llm" ? new Anthropic() : undefined;
const JUDGE_IDS = new Set(spec.metrics.filter((m) => m.grader === "judge").map((m) => m.id));
const GATE_IDS = new Set(["honesty.grounding", "compliance.protected_grounds", "compliance.no_prohibited_requests"]);

interface ScoredRow { id: string; title: string; source: string; full_text: boolean; scorecard: Scorecard; model?: string; usage?: Anthropic.Usage; judge_model?: string; judge_usage?: Anthropic.Usage; latency_s?: number }

async function main() {
  fs.mkdirSync(OUT, { recursive: true });
  const raws: RawAd[] = fs.readFileSync(RAW, "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l)).slice(0, LIMIT);
  const HOSTED = new Set(["workday", "greenhouse", "lever", "workable", "arbeitnow", "remotive"]);
  const ctxOf = (r: RawAd): ScoringContext => ({ jurisdiction: r.country === "ZA" ? "ZA" : r.country === "DE" ? "EU" : "US", hosted_apply: HOSTED.has(r.source) });
  log(`corpus: ${raws.length} ads from ${RAW}; run=${RUN} normalizer=${NORMALIZER} judge=${JUDGE ? JUDGE_MODEL : "off"} judge_prompt=${JUDGE_PROMPT_VERSION} spec=${spec.version}`);

  // 1. normalise (resumable)
  const normFile = path.join(OUT_SHARED, "normalized.jsonl");
  const normalized = new Map<string, JobAd>(readJsonl<{ id: string; ad: JobAd }>(normFile).map((x) => [x.id, x.ad]));
  const normUsage: Anthropic.Usage[] = [];
  await pool(raws.filter((r) => !normalized.has(r.id)), CONCURRENCY, async (r) => {
    try {
      const ad = NORMALIZER === "llm" ? await normalizeLLM(r, client!).then((x) => { normUsage.push(x.usage); return x.ad; }) : normalizeHeuristic(r);
      normalized.set(r.id, ad);
      fs.appendFileSync(normFile, JSON.stringify({ id: r.id, ad }) + "\n");
    } catch (e) { appendErr("normalize", r.id, e); }
  });
  log(`normalized: ${normalized.size}`);

  // 2. score originals (resumable)
  const scoreFile = path.join(OUT, "scores.jsonl");
  const scored = new Map<string, ScoredRow>(readJsonl<ScoredRow>(scoreFile).map((x) => [x.id, x]));
  await pool(raws.filter((r) => normalized.has(r.id) && !scored.has(r.id)), CONCURRENCY, async (r) => {
    try {
      const row = await scoreOne(r.id, r.title, r.source, r.full_text, normalized.get(r.id)!, ctxOf(r));
      scored.set(r.id, row);
      fs.appendFileSync(scoreFile, JSON.stringify(row) + "\n");
    } catch (e) { appendErr("score", r.id, e); }
  });
  log(`scored: ${scored.size}`);

  // 3. perturbation detection (resumable per ad×perturbation)
  const pertFile = path.join(OUT, "perturbations.jsonl");
  /** detected: null when the original has no headroom (already 0) or either side was not scored. */
  type PertRow = { id: string; perturbation: string; target: string; needs_judge: boolean; original: number | undefined; perturbed: number | undefined; detected: boolean | null; false_improvement: boolean };
  const pert: PertRow[] = readJsonl<PertRow>(pertFile);
  const done = new Set(pert.map((p) => `${p.id}|${p.perturbation}`));
  const jobs: { r: RawAd; ad: JobAd; orig: ScoredRow; p: (typeof PERTURBATIONS)[number]; pa: JobAd }[] = [];
  for (const r of raws) {
    const ad = normalized.get(r.id); const orig = scored.get(r.id);
    if (!ad || !orig) continue;
    for (const p of PERTURBATIONS) {
      if (done.has(`${r.id}|${p.name}`)) continue;
      if (p.needs_judge && !JUDGE) continue;
      const pa = p.apply(ad);
      if (pa) jobs.push({ r, ad, orig, p, pa });
    }
  }
  await pool(jobs, CONCURRENCY, async ({ r, ad, orig, p, pa }) => {
    try {
      const ctx: ScoringContext = { ...ctxOf(r), sources: p.uses_original_as_source ? [{ id: "original_ad", text: renderAd(ad) }] : undefined };
      // when grounding is the target, the original must also be judged against itself as source
      const origCard = p.uses_original_as_source ? (await scoreOne(r.id, r.title, r.source, r.full_text, ad, ctx)).scorecard : orig.scorecard;
      const pc = (await scoreOne(r.id, r.title, r.source, r.full_text, pa, ctx)).scorecard;
      for (const t of p.targets) {
        const o = origCard.metrics.find((m) => m.id === t)!, q = pc.metrics.find((m) => m.id === t)!;
        const scoredBoth = o.status === "ok" && q.status === "ok";
        const headroom = scoredBoth && o.normalized! > 0;
        const detected = headroom ? q.normalized! < o.normalized! : null;
        // judged metrics carry run-to-run noise; a "false improvement" must exceed that noise to count
        const tol = p.needs_judge ? TARGETS.judge_noise : 0;
        const row: PertRow = { id: r.id, perturbation: p.name, target: t, needs_judge: p.needs_judge, original: o.normalized, perturbed: q.normalized, detected, false_improvement: scoredBoth && q.normalized! > o.normalized! + tol };
        pert.push(row); fs.appendFileSync(pertFile, JSON.stringify(row) + "\n");
      }
    } catch (e) { appendErr("perturb", `${r.id}|${p.name}`, e); }
  });
  log(`perturbation rows: ${pert.length}`);

  // 4. judge agreement: reference model + self-consistency (sample)
  type AgreeRow = { id: string; metric: string; judge: number[]; reference: number; reference_reasoning?: string; judge_reasoning?: string };
  const agreeFile = path.join(OUT, "agreement.jsonl");
  let agree: AgreeRow[] = readJsonl<AgreeRow>(agreeFile);
  if (JUDGE && agree.length === 0) {
    const sample = raws.filter((r) => normalized.has(r.id)).slice(0, AGREEMENT_SAMPLE);
    await pool(sample, Math.max(1, Math.floor(CONCURRENCY / 2)), async (r) => {
      const ad = normalized.get(r.id)!;
      try {
        const [ref, ...reps] = await Promise.all([
          runJudge(ad, ctxOf(r), { client, model: REF_MODEL, effort: "high" }),
          ...Array.from({ length: REPS }, () => runJudge(ad, ctxOf(r), { client, model: JUDGE_MODEL })),
        ]);
        for (const m of ref.results) {
          if (m.status !== "ok") continue;
          const jr = reps.map((j) => j.results.find((x) => x.id === m.id)!);
          const row: AgreeRow = { id: r.id, metric: m.id, reference: m.raw!, judge: jr.map((x) => x.raw!), reference_reasoning: m.reasoning, judge_reasoning: jr[0]?.reasoning };
          agree.push(row); fs.appendFileSync(agreeFile, JSON.stringify(row) + "\n");
        }
      } catch (e) { appendErr("agreement", r.id, e); }
    });
  }

  // 5. probes
  const probes = await runProbes({ jurisdiction: "ZA", designated_employer: true, hosted_apply: false });

  // 6. report
  const report = buildReport([...scored.values()], pert, agree, probes, normUsage);
  fs.writeFileSync(path.join(OUT, "report.json"), JSON.stringify(report, null, 2));
  fs.writeFileSync(path.join(OUT, "report.md"), renderMd(report));
  console.log(renderMd(report));
}

async function scoreOne(id: string, title: string, source: string, full_text: boolean, ad: JobAd, ctx: ScoringContext): Promise<ScoredRow> {
  const det = runDeterministic(ad, ctx);
  if (!JUDGE) return { id, title, source, full_text, scorecard: buildScorecard(det, ctx, spec) };
  const j = await runJudge(ad, ctx, { client, model: JUDGE_MODEL });
  return { id, title, source, full_text, scorecard: buildScorecard([...det, ...j.results], ctx, spec), judge_model: j.model, judge_usage: j.usage, latency_s: j.latency_s };
}

async function runProbes(ctx: ScoringContext) {
  const probes: { name: string; ad: JobAd; expect: string }[] = [
    { name: "empty", ad: EMPTY_AD, expect: "blocked, composite < 20" },
    { name: "i_dont_know", ad: { ...EMPTY_AD, title: "Job", summary: "I don't know what this role is. Apply if you like." }, expect: "blocked or composite < 20" },
    { name: "wrong_role_confident", ad: { ...GOOD_AD, title: "Senior Boilermaker" }, expect: "structure.title_matches_content fails when judged; deterministic alone cannot catch" },
    { name: "oracle_good_fixture", ad: GOOD_AD, expect: "gates pass, composite >= 80" },
  ];
  const out = [];
  for (const p of probes) {
    const row = await scoreOne(`probe:${p.name}`, p.name, "probe", true, p.ad, ctx).catch((e) => ({ scorecard: undefined as Scorecard | undefined, err: String(e) }));
    const sc = row.scorecard;
    const pass = p.name === "oracle_good_fixture" ? !!sc && sc.gates_passed && sc.composite >= 80 : p.name === "wrong_role_confident" ? (JUDGE ? !!sc && sc.metrics.find((m) => m.id === "structure.title_matches_content")?.pass === false : null) : !!sc && (!sc.gates_passed || sc.composite < 20);
    out.push({ name: p.name, expect: p.expect, composite: sc?.composite, gates_passed: sc?.gates_passed, gate_failures: sc?.gate_failures, pass });
  }
  return out;
}

function buildReport(rows: ScoredRow[], pert: any[], agree: any[], probes: any[], normUsage: Anthropic.Usage[]) {
  const comps = rows.map((r) => r.scorecard.composite).sort((x, y) => x - y);
  const q = (p: number) => comps.length ? comps[Math.min(comps.length - 1, Math.floor(p * comps.length))] : 0;
  const metricDist: Record<string, { n: number; mean_norm: number; pass_rate?: number; mean_raw: number }> = {};
  for (const m of spec.metrics) {
    const vals = rows.map((r) => r.scorecard.metrics.find((x) => x.id === m.id)!).filter((x) => x.status === "ok");
    if (!vals.length) continue;
    metricDist[m.id] = { n: vals.length, mean_norm: mean(vals.map((v) => v.normalized!)), mean_raw: mean(vals.map((v) => v.raw!)), ...(m.type === "pass_fail" ? { pass_rate: mean(vals.map((v) => (v.pass ? 1 : 0))) } : {}) };
  }
  const gateFailRate: Record<string, number> = {};
  for (const r of rows) for (const g of r.scorecard.gate_failures) gateFailRate[g] = (gateFailRate[g] ?? 0) + 1 / rows.length;

  const detection: Record<string, { perturbation: string; target: string; n_total: number; n: number; rate: number; false_improvements: number; target_rate: number; pass: boolean }> = {};
  for (const p of pert) {
    const k = `${p.perturbation}→${p.target}`;
    const d = (detection[k] ??= { perturbation: p.perturbation, target: p.target, n_total: 0, n: 0, rate: 0, false_improvements: 0, target_rate: p.needs_judge ? TARGETS.judge : TARGETS.det, pass: false });
    d.n_total++;
    if (p.false_improvement) d.false_improvements++;
    if (p.detected === null) continue;
    d.n++; d.rate += p.detected ? 1 : 0;
  }
  for (const d of Object.values(detection)) { d.rate = d.n ? d.rate / d.n : 0; d.pass = d.n >= 5 && d.rate >= d.target_rate && d.false_improvements === 0; }

  const agreement: Record<string, { n: number; type: string; kappa?: number; mae?: number; consistency: number; target: string; pass: boolean }> = {};
  const byMetric = groupBy(agree, (x) => x.metric);
  const RATIO = new Set(spec.metrics.filter((m) => m.type === "ratio" && m.grader === "judge").map((m) => m.id));
  for (const [metric, xs] of Object.entries(byMetric)) {
    if (RATIO.has(metric)) {
      // ratios: agreement = mean absolute error vs reference; consistency = spread across reps ≤ 0.15
      const mae = mean(xs.map((x) => Math.abs(x.reference - x.judge[0])));
      const consistency = mean(xs.map((x) => (Math.max(...x.judge) - Math.min(...x.judge) <= TARGETS.ratio_spread ? 1 : 0)));
      agreement[metric] = { n: xs.length, type: "ratio", mae, consistency, target: `MAE ≤ ${TARGETS.mae}`, pass: mae <= TARGETS.mae && consistency >= TARGETS.consistency };
    } else {
      const ref = xs.map((x) => bin(x.reference)); const j = xs.map((x) => bin(x.judge[0]));
      const consistency = mean(xs.map((x) => (x.judge.every((v: number) => bin(v) === bin(x.judge[0])) ? 1 : 0)));
      const kappa = cohenKappa(ref, j);
      const target_kappa = GATE_IDS.has(metric) ? TARGETS.kappa_gate : TARGETS.kappa;
      // κ is undefined when both raters are constant and identical; treat perfect identical agreement as pass
      const identical = ref.every((v, i) => v === j[i]);
      const positives = Math.max(ref.filter((v) => v !== 0).length, j.filter((v) => v !== 0).length);
      const pctAgree = mean(ref.map((v, i) => (v === j[i] ? 1 : 0)));
      if (positives <= 2 && !identical) {
        // κ is undefined/unstable when a label is this rare; fall back to percent agreement and say so
        agreement[metric] = { n: xs.length, type: "categorical (rare positives: κ unstable, % agreement used)", kappa: pctAgree, consistency, target: `agree ≥ 0.9`, pass: pctAgree >= 0.9 && consistency >= TARGETS.consistency };
      } else {
        agreement[metric] = { n: xs.length, type: "categorical", kappa: identical ? 1 : kappa, consistency, target: `κ ≥ ${target_kappa}`, pass: (identical || kappa >= target_kappa) && consistency >= TARGETS.consistency };
      }
    }
  }

  const judgeUsage = rows.filter((r) => r.judge_usage);
  const cost = {
    judge_calls: judgeUsage.length,
    judge_mean_input_tokens: mean(judgeUsage.map((r) => r.judge_usage!.input_tokens + (r.judge_usage!.cache_read_input_tokens ?? 0) + (r.judge_usage!.cache_creation_input_tokens ?? 0))),
    judge_mean_output_tokens: mean(judgeUsage.map((r) => r.judge_usage!.output_tokens)),
    judge_mean_latency_s: mean(judgeUsage.map((r) => r.latency_s!)),
    judge_cache_read_share: judgeUsage.length ? mean(judgeUsage.map((r) => (r.judge_usage!.cache_read_input_tokens ?? 0) / Math.max(1, r.judge_usage!.input_tokens + (r.judge_usage!.cache_read_input_tokens ?? 0) + (r.judge_usage!.cache_creation_input_tokens ?? 0)))) : 0,
    normalize_calls: normUsage.length,
    normalize_mean_tokens: mean(normUsage.map((u) => u.input_tokens + u.output_tokens)),
  };

  const evaluable = Object.values(detection).filter((d) => d.n >= 5);
  const insufficient = Object.values(detection).filter((d) => d.n < 5).map((d) => `${d.perturbation}→${d.target}`);
  const exit = {
    perturbation_all_pass: evaluable.length > 0 && evaluable.every((d) => d.pass),
    perturbation_insufficient_data: insufficient,
    agreement_all_pass: JUDGE ? Object.values(agreement).length > 0 && Object.values(agreement).every((x) => x.pass) : null,
    probes_all_pass: probes.every((p) => p.pass !== false),
  };
  return {
    version: VERSION, generated_at: new Date().toISOString(), spec_version: spec.version, judge_prompt_version: JUDGE_PROMPT_VERSION,
    config: { normalizer: NORMALIZER, judge: JUDGE ? JUDGE_MODEL : null, reference_model: JUDGE ? REF_MODEL : null, reps: REPS },
    corpus: { n: rows.length, full_text_share: mean(rows.map((r) => (r.full_text ? 1 : 0))), sources: countBy(rows, (r) => r.source) },
    composite: { mean: mean(comps), p10: q(0.1), p25: q(0.25), median: q(0.5), p75: q(0.75), p90: q(0.9), gates_pass_rate: mean(rows.map((r) => (r.scorecard.gates_passed ? 1 : 0))), verdicts: countBy(rows, (r) => r.scorecard.verdict) },
    gate_fail_rate: gateFailRate, metrics: metricDist, detection, agreement, probes, cost, exit,
  };
}

function renderMd(r: ReturnType<typeof buildReport>): string {
  const pct = (x: number | undefined | null) => (x == null ? "–" : `${Math.round(x * 100)}%`);
  const f = (x: number | undefined) => (x == null ? "–" : Number.isInteger(x) ? String(x) : x.toFixed(2));
  const L: string[] = [];
  L.push(`# Phase 0 scorer benchmark — ${r.version}`, "", `Generated ${r.generated_at}. Spec ${r.spec_version}, judge prompt ${r.judge_prompt_version}. Normalizer: ${r.config.normalizer}; judge: ${r.config.judge ?? "off"}${r.config.reference_model ? `; reference: ${r.config.reference_model}; reps: ${r.config.reps}` : ""}.`, "");
  L.push(`## Exit criteria`, "", `| Criterion | Result |`, `|---|---|`, `| Perturbation detection ≥ ${TARGETS.det} (det) / ${TARGETS.judge} (judge) on every target | ${r.exit.perturbation_all_pass ? "PASS" : "FAIL"}${r.exit.perturbation_insufficient_data.length ? ` (insufficient data: ${r.exit.perturbation_insufficient_data.join(", ")})` : ""} |`, `| Judge–reference κ ≥ ${TARGETS.kappa} (${TARGETS.kappa_gate} gates) or MAE ≤ ${TARGETS.mae} for ratios, self-consistency ≥ ${TARGETS.consistency} | ${r.exit.agreement_all_pass == null ? "not run (judge off)" : r.exit.agreement_all_pass ? "PASS" : "FAIL"} |`, `| Null / oracle probes | ${r.exit.probes_all_pass ? "PASS" : "FAIL"} |`, "");
  L.push(`## Corpus and real-ad distribution`, "", `| | |`, `|---|---|`, `| Ads | ${r.corpus.n} (full text ${pct(r.corpus.full_text_share)}) |`, `| Sources | ${Object.entries(r.corpus.sources).map(([k, v]) => `${k}: ${v}`).join(", ")} |`, `| Composite mean / median | ${f(r.composite.mean)} / ${f(r.composite.median)} |`, `| Composite p10 / p25 / p75 / p90 | ${f(r.composite.p10)} / ${f(r.composite.p25)} / ${f(r.composite.p75)} / ${f(r.composite.p90)} |`, `| Gates pass rate | ${pct(r.composite.gates_pass_rate)} |`, `| Verdicts | ${Object.entries(r.composite.verdicts).map(([k, v]) => `${k}: ${v}`).join(", ")} |`, "");
  if (Object.keys(r.gate_fail_rate).length) { L.push(`Gate failure rates: ${Object.entries(r.gate_fail_rate).map(([k, v]) => `${k} ${pct(v)}`).join("; ")}`, ""); }
  L.push(`## Metric distribution on real ads`, "", `| Metric | n | mean raw | mean norm | pass rate |`, `|---|---|---|---|---|`);
  for (const [id, m] of Object.entries(r.metrics)) L.push(`| ${id} | ${m.n} | ${f(m.mean_raw)} | ${f(m.mean_norm)} | ${pct(m.pass_rate)} |`);
  L.push("", `## Perturbation detection`, "", `Detection is measured only on ads with headroom (original normalised score > 0). "n" is eligible ads out of all perturbed; a pass needs n ≥ 5, rate ≥ target and zero false improvements (perturbed scoring higher than original by more than judge noise, ${TARGETS.judge_noise} for judged metrics).`, "", `| Perturbation | Target metric | n (of) | detected | false impr. | target | |`, `|---|---|---|---|---|---|---|`);
  for (const d of Object.values(r.detection)) L.push(`| ${d.perturbation} | ${d.target} | ${d.n} (${d.n_total}) | ${pct(d.rate)} | ${d.false_improvements} | ${pct(d.target_rate)} | ${d.pass ? "ok" : d.n < 5 ? "too few" : "FAIL"} |`);
  if (Object.keys(r.agreement).length) {
    L.push("", `## Judge agreement`, "", `Categorical metrics: Cohen's κ vs the reference model. Ratio metrics: mean absolute error vs the reference (κ on binned ratios punishes near-boundary values). Self-consistency: same label (or ratio spread ≤ ${TARGETS.ratio_spread}, about one bullet on a short list) across ${r.config.reps} reps.`, "", `| Metric | n | agreement | self-consistency | target | |`, `|---|---|---|---|---|---|`);
    for (const [id, x] of Object.entries(r.agreement)) L.push(`| ${id} | ${x.n} | ${x.type === "ratio" ? `MAE ${f(x.mae)}` : x.type.startsWith("categorical (rare") ? `agree ${pct(x.kappa)} (κ unstable)` : `κ ${f(x.kappa)}`} | ${pct(x.consistency)} | ${x.target} | ${x.pass ? "ok" : "FAIL"} |`);
  }
  L.push("", `## Probes`, "", `| Probe | Expectation | composite | gates | result |`, `|---|---|---|---|---|`);
  for (const p of r.probes) L.push(`| ${p.name} | ${p.expect} | ${f(p.composite)} | ${p.gates_passed == null ? "–" : p.gates_passed ? "pass" : `fail (${(p.gate_failures ?? []).join(", ")})`} | ${p.pass == null ? "n/a" : p.pass ? "ok" : "FAIL"} |`);
  if (r.cost.judge_calls) L.push("", `## Cost and latency`, "", `Judge calls: ${r.cost.judge_calls}; mean input tokens ${f(r.cost.judge_mean_input_tokens)} (cache-read share ${pct(r.cost.judge_cache_read_share)}); mean output tokens ${f(r.cost.judge_mean_output_tokens)}; mean latency ${f(r.cost.judge_mean_latency_s)} s. Normalize calls: ${r.cost.normalize_calls}, mean tokens ${f(r.cost.normalize_mean_tokens)}.`);
  return L.join("\n") + "\n";
}

// ---------------- stats & utils
async function pool<T>(items: T[], n: number, fn: (item: T) => Promise<void>): Promise<void> {
  let i = 0;
  const workers = Array.from({ length: Math.min(n, items.length) }, async () => { while (i < items.length) { const item = items[i++]; await fn(item); } });
  await Promise.all(workers);
}
function cohenKappa(a: number[], b: number[]): number {
  const n = a.length; if (!n) return 0;
  const cats = [...new Set([...a, ...b])];
  const po = a.filter((x, i) => x === b[i]).length / n;
  const pe = cats.reduce((s, c) => s + (a.filter((x) => x === c).length / n) * (b.filter((x) => x === c).length / n), 0);
  if (pe === 1) return po === 1 ? 1 : 0;
  return (po - pe) / (1 - pe);
}
/** Bin judged values so κ is over categories: pass/fail stay 0/1; ratios -> {0: <0.5, 1: 0.5-0.85, 2: >=0.85}; counts -> {0, 1, 2+}. */
function bin(v: number): number { if (v === 0 || v === 1) return v; if (v > 1) return 2; return v < 0.5 ? 0 : v < 0.85 ? 1 : 2; }
const mean = (xs: number[]) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0);
function groupBy<T>(xs: T[], k: (x: T) => string): Record<string, T[]> { const o: Record<string, T[]> = {}; for (const x of xs) (o[k(x)] ??= []).push(x); return o; }
function countBy<T>(xs: T[], k: (x: T) => string): Record<string, number> { const o: Record<string, number> = {}; for (const x of xs) o[k(x)] = (o[k(x)] ?? 0) + 1; return o; }
function readJsonl<T>(file: string): T[] { return fs.existsSync(file) ? fs.readFileSync(file, "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l) as T) : []; }
function appendErr(stage: string, id: string, e: unknown) { fs.appendFileSync(path.join(OUT, "errors.jsonl"), JSON.stringify({ stage, id, error: String(e), at: new Date().toISOString() }) + "\n"); log(`error in ${stage} for ${id}: ${String(e).slice(0, 200)}`); }
const log = (s: string) => console.error(`[bench] ${s}`);
function parseArgs(argv: string[]): Record<string, string> { const o: Record<string, string> = {}; for (let i = 0; i < argv.length; i++) if (argv[i].startsWith("--")) { const k = argv[i].slice(2); const v = argv[i + 1] && !argv[i + 1].startsWith("--") ? argv[++i] : "true"; o[k] = v; } return o; }

main().catch((e) => { console.error(e); process.exit(1); });
