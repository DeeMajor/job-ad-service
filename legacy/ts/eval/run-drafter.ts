/**
 * Phase 1 drafter eval.
 *
 *   tsx eval/run-drafter.ts --variant baseline [--split test|validation|train|all] [--limit N] [--reps 1]
 *                           [--model claude-opus-5] [--effort medium] [--judge-model claude-sonnet-5] [--concurrency 4]
 *
 * Reads  eval/cases/briefs.jsonl
 * Writes eval/runs/<variant>/results.jsonl, traces/<id>_rep<k>.json, errors.jsonl, report.md
 * Resumable: existing (prompt_id, rep) rows are skipped.
 */
import fs from "node:fs";
import path from "node:path";
import Anthropic from "@anthropic-ai/sdk";
import { draft } from "../services/job-ad/drafter/draft.js";
import { HiringBriefSchema } from "../services/job-ad/drafter/brief.js";
import { renderAd } from "../services/job-ad/metrics/text.js";
import { DRAFTER_PROMPT_VERSION, DRAFTER_SYSTEM } from "../services/job-ad/drafter/prompts/system.js";
import { JUDGE_PROMPT_VERSION } from "../services/job-ad/metrics/judge/prompt.js";
import { loadSpec } from "../services/job-ad/metrics/spec.js";

const a = parseArgs(process.argv.slice(2));
const VARIANT = a.variant ?? "baseline";
const SPLIT = a.split ?? "all";
const LIMIT = a.limit ? Number(a.limit) : Infinity;
const REPS = Number(a.reps ?? 1);
const MODEL = a.model ?? "claude-opus-5";
const EFFORT = (a.effort ?? "medium") as "low" | "medium" | "high";
const JUDGE_MODEL = a["judge-model"] ?? "claude-sonnet-5";
const CONC = Number(a.concurrency ?? 4);
const OUT = path.join("eval/runs", VARIANT);
const spec = loadSpec();
const client = new Anthropic();

interface Case { prompt_id: string; source_ad_id: string; split: string; tags: string[]; brief: unknown; real_ad: { composite: number; gates_passed: boolean; verdict: string } }

async function main() {
  fs.mkdirSync(path.join(OUT, "traces"), { recursive: true });
  const cases: Case[] = fs.readFileSync("eval/cases/briefs.jsonl", "utf8").trim().split("\n").map((l) => JSON.parse(l)).filter((c: Case) => SPLIT === "all" || c.split === SPLIT).slice(0, LIMIT);
  const resFile = path.join(OUT, "results.jsonl");
  const done = new Set(readJsonl<any>(resFile).map((r) => `${r.prompt_id}|${r.rep}`));
  const jobs = cases.flatMap((c) => Array.from({ length: REPS }, (_, rep) => ({ c, rep }))).filter(({ c, rep }) => !done.has(`${c.prompt_id}|${rep}`));
  log(`variant=${VARIANT} split=${SPLIT} cases=${cases.length} reps=${REPS} todo=${jobs.length} model=${MODEL}/${EFFORT} judge=${JUDGE_MODEL} drafter_prompt=${DRAFTER_PROMPT_VERSION} judge_prompt=${JUDGE_PROMPT_VERSION} spec=${spec.version}`);

  await pool(jobs, CONC, async ({ c, rep }) => {
    const brief = HiringBriefSchema.parse(c.brief);
    try {
      const d = await draft(brief, { client, model: MODEL, effort: EFFORT, judgeModel: JUDGE_MODEL });
      if (d.model !== MODEL && !d.model.startsWith(MODEL)) throw new Error(`served model ${d.model} != requested ${MODEL}`);
      const sc = d.scorecard!;
      const grade: Record<string, number> = { composite: sc.composite, gates_passed: sc.gates_passed ? 1 : 0, publishable: sc.verdict === "publishable" ? 1 : 0, beats_real: sc.composite > c.real_ad.composite ? 1 : 0 };
      for (const m of sc.metrics) if (m.status === "ok" && m.normalized != null) grade[m.id] = m.normalized;
      const row = {
        prompt_id: c.prompt_id, rep, prompt: d.brief_text, tags: c.tags, split: c.split, status: "ok", stop_reason: "end_turn",
        grade, gate_failures: sc.gate_failures, verdict: sc.verdict, real_ad_composite: c.real_ad.composite,
        model: d.model, usage: d.usage, judge_model: d.judge?.model, judge_usage: d.judge?.usage, latency_s: d.latency_s, judge_latency_s: d.judge?.latency_s,
        words: renderAd(d.ad).split(/\s+/).length, drafter_prompt_version: DRAFTER_PROMPT_VERSION, judge_prompt_version: JUDGE_PROMPT_VERSION, spec_version: spec.version,
      };
      fs.appendFileSync(resFile, JSON.stringify(row) + "\n");
      const trace = [
        { role: "system", content: DRAFTER_SYSTEM },
        { role: "user", content: d.brief_text },
        { role: "assistant", content: renderAd(d.ad), attachments: undefined },
        { role: "tool_call", name: "score", content: JSON.stringify({ judge_model: JUDGE_MODEL }) },
        { role: "tool_result", content: JSON.stringify({ composite: sc.composite, verdict: sc.verdict, gate_failures: sc.gate_failures, metrics: sc.metrics.filter((m) => m.status === "ok").map((m) => ({ id: m.id, raw: m.raw, normalized: m.normalized, evidence: m.evidence, reasoning: m.reasoning })) }, null, 1) },
      ];
      fs.writeFileSync(path.join(OUT, "traces", `${c.prompt_id}_rep${rep}.json`), JSON.stringify({ ad: d.ad, trace }, null, 1));
    } catch (e) {
      fs.appendFileSync(path.join(OUT, "errors.jsonl"), JSON.stringify({ prompt_id: c.prompt_id, rep, error: String(e), at: new Date().toISOString() }) + "\n");
      log(`error ${c.prompt_id} rep${rep}: ${String(e).slice(0, 160)}`);
    }
  });

  const rows = readJsonl<any>(resFile);
  const md = report(rows);
  fs.writeFileSync(path.join(OUT, "report.md"), md);
  console.log(md);
}

function report(rows: any[]): string {
  const f = (x: number) => (Number.isInteger(x) ? String(x) : x.toFixed(2));
  const pct = (x: number) => `${Math.round(x * 100)}%`;
  const mean = (xs: number[]) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0);
  const L: string[] = [`# Drafter eval — variant ${VARIANT}`, "", `Generated ${new Date().toISOString()}. ${rows.length} rows. Drafter ${MODEL}/${EFFORT}, prompt ${DRAFTER_PROMPT_VERSION}; judge ${JUDGE_MODEL}, prompt ${JUDGE_PROMPT_VERSION}; spec ${spec.version}.`, ""];
  const bySplit = groupBy(rows, (r) => r.split);
  L.push(`## Headline`, "", `| Split | n | composite mean | median | publishable | gates pass | beats real ad | real ad mean |`, `|---|---|---|---|---|---|---|---|`);
  for (const [s, xs] of Object.entries(bySplit)) {
    const comps = xs.map((r) => r.grade.composite).sort((a, b) => a - b);
    L.push(`| ${s} | ${xs.length} | ${f(mean(comps))} | ${f(comps[Math.floor(comps.length / 2)])} | ${pct(mean(xs.map((r) => r.grade.publishable)))} | ${pct(mean(xs.map((r) => r.grade.gates_passed)))} | ${pct(mean(xs.map((r) => r.grade.beats_real)))} | ${f(mean(xs.map((r) => r.real_ad_composite)))} |`);
  }
  const gf: Record<string, number> = {};
  for (const r of rows) for (const g of r.gate_failures) gf[g] = (gf[g] ?? 0) + 1;
  if (Object.keys(gf).length) L.push("", `Gate failures: ${Object.entries(gf).map(([k, v]) => `${k} ${v}/${rows.length}`).join("; ")}`);
  L.push("", `## By role`, "", `| Role | n | composite | beats real | real mean |`, `|---|---|---|---|---|`);
  for (const [role, xs] of Object.entries(groupBy(rows, (r) => r.tags[0]))) L.push(`| ${role} | ${xs.length} | ${f(mean(xs.map((r) => r.grade.composite)))} | ${pct(mean(xs.map((r) => r.grade.beats_real)))} | ${f(mean(xs.map((r) => r.real_ad_composite)))} |`);
  // noise floor from reps
  const byCase = groupBy(rows, (r) => r.prompt_id);
  const spreads = Object.values(byCase).filter((xs) => xs.length > 1).map((xs) => Math.max(...xs.map((r) => r.grade.composite)) - Math.min(...xs.map((r) => r.grade.composite)));
  if (spreads.length) L.push("", `Noise floor: ${spreads.length} cases with repeats; mean composite spread ${f(mean(spreads))}, max ${f(Math.max(...spreads))}.`);
  L.push("", `## Weakest metrics (mean normalised, lowest first)`, "", `| Metric | mean | n |`, `|---|---|---|`);
  const ids = new Set<string>(); for (const r of rows) for (const k of Object.keys(r.grade)) if (k.includes(".")) ids.add(k);
  const weak = [...ids].map((id) => { const v = rows.map((r) => r.grade[id]).filter((x) => x != null); return { id, m: mean(v), n: v.length }; }).sort((a, b) => a.m - b.m).slice(0, 10);
  for (const w of weak) L.push(`| ${w.id} | ${f(w.m)} | ${w.n} |`);
  const inTok = rows.map((r) => r.usage.input_tokens + (r.usage.cache_read_input_tokens ?? 0) + (r.usage.cache_creation_input_tokens ?? 0));
  const cost = rows.map((r) => (r.usage.input_tokens * 5 + (r.usage.cache_read_input_tokens ?? 0) * 0.5 + (r.usage.cache_creation_input_tokens ?? 0) * 6.25 + r.usage.output_tokens * 25) / 1e6 + (r.judge_usage ? (r.judge_usage.input_tokens * 2 + (r.judge_usage.cache_read_input_tokens ?? 0) * 0.2 + (r.judge_usage.cache_creation_input_tokens ?? 0) * 2.5 + r.judge_usage.output_tokens * 10) / 1e6 : 0));
  L.push("", `## Cost and latency`, "", `Drafter: mean input ${f(mean(inTok))} tokens, output ${f(mean(rows.map((r) => r.usage.output_tokens)))}, latency ${f(mean(rows.map((r) => r.latency_s)))} s. Mean words per ad ${f(mean(rows.map((r) => r.words)))}. **Mean cost per draft incl. judge: $${mean(cost).toFixed(3)}** (total $${cost.reduce((a, b) => a + b, 0).toFixed(2)}).`);
  return L.join("\n") + "\n";
}

async function pool<T>(items: T[], n: number, fn: (item: T) => Promise<void>) { let i = 0; await Promise.all(Array.from({ length: Math.min(n, items.length) }, async () => { while (i < items.length) await fn(items[i++]); })); }
function groupBy<T>(xs: T[], k: (x: T) => string): Record<string, T[]> { const o: Record<string, T[]> = {}; for (const x of xs) (o[k(x)] ??= []).push(x); return o; }
function readJsonl<T>(file: string): T[] { return fs.existsSync(file) ? fs.readFileSync(file, "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l) as T) : []; }
const log = (s: string) => console.error(`[eval] ${s}`);
function parseArgs(argv: string[]): Record<string, string> { const o: Record<string, string> = {}; for (let i = 0; i < argv.length; i++) if (argv[i].startsWith("--")) { const k = argv[i].slice(2); const v = argv[i + 1] && !argv[i + 1].startsWith("--") ? argv[++i] : "true"; o[k] = v; } return o; }
main().catch((e) => { console.error(e); process.exit(1); });
