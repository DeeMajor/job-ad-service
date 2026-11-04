/**
 * Build Phase 1 eval cases from the real ads already normalised in Phase 0.
 * Each case = a HiringBrief derived from a real ad + the real ad's own scorecard composite (the number to beat).
 *
 *   tsx eval/build-cases.ts            → eval/cases/briefs.jsonl
 */
import fs from "node:fs";
import path from "node:path";
import { briefFromJobAd } from "../services/job-ad/drafter/brief.js";
import type { JobAd } from "../services/job-ad/metrics/types.js";

interface Src { version: string; run: string; role: (id: string, title: string) => string; }
const SOURCES: Src[] = [
  { version: "v1", run: "r3", role: () => "bank_sales" },
  { version: "v1d", run: "r1", role: (id) => roleOf.get(id) ?? "other" },
];
const roleOf = new Map<string, string>(fs.existsSync("bench/data/raw/v1d/ads.jsonl") ? fs.readFileSync("bench/data/raw/v1d/ads.jsonl", "utf8").trim().split("\n").map((l) => { const j = JSON.parse(l); return [j.id, j.role_family]; }) : []);
const HOSTED = /^(workday|greenhouse|lever|workable):/;

const out: string[] = [];
let i = 0;
for (const s of SOURCES) {
  const normFile = path.join("bench/data/out", s.version, "normalized.jsonl");
  const scoreFile = path.join("bench/data/out", s.version, s.run, "scores.jsonl");
  if (!fs.existsSync(normFile) || !fs.existsSync(scoreFile)) continue;
  const scores = new Map(fs.readFileSync(scoreFile, "utf8").trim().split("\n").map((l) => { const j = JSON.parse(l); return [j.id, j]; }));
  for (const line of fs.readFileSync(normFile, "utf8").trim().split("\n")) {
    const { id, ad } = JSON.parse(line) as { id: string; ad: JobAd };
    const real = scores.get(id);
    if (!real) continue;
    const brief = briefFromJobAd(ad, { jurisdiction: "ZA", hosted_apply: HOSTED.test(id) });
    // split: every 5th case to test, every 5th+2 to validation, rest train (deterministic by index)
    const split = i % 5 === 0 ? "test" : i % 5 === 2 ? "validation" : "train";
    const thin = brief.responsibilities.length <= 3 || brief.must_have.length <= 1 ? "thin" : "rich";
    out.push(JSON.stringify({ prompt_id: `case_${String(i).padStart(3, "0")}`, source_ad_id: id, split, tags: [s.role(id, ad.title), thin, s.version], brief, real_ad: { composite: real.scorecard.composite, gates_passed: real.scorecard.gates_passed, verdict: real.scorecard.verdict, judge_prompt_version: real.judge_prompt_version ?? null } }));
    i++;
  }
}
fs.mkdirSync("eval/cases", { recursive: true });
fs.writeFileSync("eval/cases/briefs.jsonl", out.join("\n") + "\n");
const rows = out.map((l) => JSON.parse(l));
const count = (k: (r: any) => string) => rows.reduce((a: Record<string, number>, r) => ((a[k(r)] = (a[k(r)] ?? 0) + 1), a), {});
console.log(JSON.stringify({ cases: rows.length, splits: count((r) => r.split), roles: count((r) => r.tags[0]), richness: count((r) => r.tags[1]), real_composite_mean: Math.round(rows.reduce((a, r) => a + r.real_ad.composite, 0) / rows.length * 10) / 10 }, null, 1));
