import Anthropic from "@anthropic-ai/sdk";
import { zodOutputFormat } from "@anthropic-ai/sdk/helpers/zod";
import type { JobAd, MetricResult, ScoringContext } from "../types.js";
import { renderAd } from "../text.js";
import { JudgeOutput } from "./schema.js";
import { JUDGE_SYSTEM, renderJudgeInput } from "./prompt.js";

export type Raw = Pick<MetricResult, "id" | "status" | "raw" | "pass" | "evidence" | "reasoning">;

export interface JudgeOptions {
  client?: Anthropic;
  /** Never the model under test. Default claude-sonnet-5. */
  model?: string;
  effort?: "low" | "medium" | "high";
}

export interface JudgeRun {
  results: Raw[];
  parsed: JudgeOutput;
  model: string;
  usage: Anthropic.Usage;
  latency_s: number;
}

export async function runJudge(ad: JobAd | string, ctx: ScoringContext, opts: JudgeOptions = {}): Promise<JudgeRun> {
  const client = opts.client ?? new Anthropic();
  const model = opts.model ?? "claude-sonnet-5";
  const adText = typeof ad === "string" ? ad : renderAd(ad);
  const t0 = Date.now();
  // one retry on a malformed structured output (seen ~1 in 600 calls: unterminated JSON string)
  const call = () => client.messages.parse({
    model,
    max_tokens: 8000,
    thinking: { type: "adaptive" },
    output_config: { effort: opts.effort ?? "medium", format: zodOutputFormat(JudgeOutput) },
    system: [{ type: "text", text: JUDGE_SYSTEM, cache_control: { type: "ephemeral" } }],
    messages: [{ role: "user", content: renderJudgeInput({ adText, sources: ctx.sources }) }],
  });
  let res: Awaited<ReturnType<typeof call>>;
  try { res = await call(); } catch (e) { if (String(e).includes("Failed to parse structured output")) res = await call(); else throw e; }
  const latency_s = (Date.now() - t0) / 1000;
  if (res.stop_reason === "refusal") throw new Error(`judge refused: ${res.stop_details?.explanation ?? ""}`);
  if (!res.parsed_output) throw new Error("judge output failed to parse");
  const parsed = res.parsed_output;
  const results: Raw[] = [];
  const pf = (id: string, j: { pass: boolean; evidence: string[]; reasoning: string }) => results.push({ id, status: "ok", raw: j.pass ? 1 : 0, pass: j.pass, evidence: j.evidence, reasoning: j.reasoning });
  const ratio = (num: number, den: number) => (den <= 0 ? 1 : Math.min(1, num / den));

  pf("structure.title_matches_content", parsed.title_matches_content);
  const r = parsed.responsibilities;
  results.push({ id: "specific.responsibility_concreteness", status: r.total === 0 ? "not_applicable" : "ok", raw: ratio(r.concrete.length, r.total), evidence: r.concrete, reasoning: `${r.concrete.length}/${r.total} concrete. ${r.reasoning}` });
  const q = parsed.specific_requirements;
  const traced = q.items.filter((i) => i.supporting_responsibility.trim().length > 0);
  results.push({ id: "specific.requirement_traceability", status: q.items.length === 0 ? "not_applicable" : "ok", raw: ratio(traced.length, q.items.length), evidence: q.items.map((i) => `${i.requirement} ← ${i.supporting_responsibility || "(none)"}`), reasoning: `${traced.length}/${q.items.length} specific requirements traceable (generic education and experience bands excluded). ${q.reasoning}` });
  pf("pay.context_present", parsed.pay_context_present);
  const g = parsed.grounding;
  const hasSources = (ctx.sources?.length ?? 0) > 0;
  results.push({ id: "honesty.grounding", status: hasSources ? "ok" : "not_applicable", raw: hasSources ? ratio(Math.max(0, g.factual_claims_total - g.unsupported_claims.length), g.factual_claims_total) : 1, evidence: g.unsupported_claims.map((c) => `unsupported: ${c.claim} — "${c.sentence}"`), reasoning: hasSources ? `${g.unsupported_claims.length}/${g.factual_claims_total} unsupported. ${g.reasoning}` : "no sources provided; grounding not assessable" });
  const px = parsed.proxy_requirements;
  results.push({ id: "inclusive.proxy_requirements", status: "ok", raw: px.items.length, evidence: px.items, reasoning: px.reasoning });
  pf("compliance.protected_grounds", parsed.protected_grounds_ok);
  pf("compliance.no_prohibited_requests", parsed.no_prohibited_requests);
  const wr = parsed.why_this_role;
  const draw = wr.role_specific_draw.trim();
  results.push({ id: "evp.why_this_role", status: "ok", raw: draw ? 1 : 0, pass: !!draw, evidence: draw ? [draw] : [], reasoning: wr.reasoning });
  pf("evp.benefits_specific", parsed.evp_benefits_specific);
  const tc = parsed.team_context;
  const teamPass = tc.reports_to.trim().length > 0 || /\d/.test(tc.team_size);
  results.push({ id: "evp.team_context", status: "ok", raw: teamPass ? 1 : 0, pass: teamPass, evidence: [tc.reports_to && `reports to: ${tc.reports_to}`, tc.team_size && `team size: ${tc.team_size}`].filter((x): x is string => !!x), reasoning: tc.reasoning });
  pf("evp.work_mode_clarity", parsed.evp_work_mode_clarity);
  pf("process.steps_and_timeline", parsed.process_steps_and_timeline);
  return { results, parsed, model: res.model, usage: res.usage, latency_s };
}
