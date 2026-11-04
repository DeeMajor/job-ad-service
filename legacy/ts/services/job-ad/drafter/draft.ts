import Anthropic from "@anthropic-ai/sdk";
import { zodOutputFormat } from "@anthropic-ai/sdk/helpers/zod";
import type { JobAd, Scorecard, ScoringContext } from "../metrics/types.js";
import { JobAdSchema, fromSchema } from "../schema.js";
import { score } from "../metrics/scorecard.js";
import type { JudgeRun } from "../metrics/judge/index.js";
import { type HiringBrief, renderBrief } from "./brief.js";
import { DRAFTER_PROMPT_VERSION, DRAFTER_SYSTEM, renderDrafterInput } from "./prompts/system.js";

export interface DraftOptions {
  client?: Anthropic;
  /** Default claude-opus-5. */
  model?: string;
  effort?: "low" | "medium" | "high";
  /** Run the scorer after drafting (default true). */
  score?: boolean;
  judgeModel?: string;
}

export interface DraftResult {
  ad: JobAd;
  scorecard?: Scorecard;
  judge?: JudgeRun;
  model: string;
  usage: Anthropic.Usage;
  latency_s: number;
  prompt_version: string;
  /** What the drafter saw: the brief as a SOURCE block (also what the grounding judge checks against). */
  brief_text: string;
}

/** Phase 1 baseline: brief → structured ad, no retrieval, no revision loop. */
export async function draft(brief: HiringBrief, opts: DraftOptions = {}): Promise<DraftResult> {
  const client = opts.client ?? new Anthropic();
  const model = opts.model ?? "claude-opus-5";
  const briefText = renderBrief(brief);
  const t0 = Date.now();
  const res = await client.messages.parse({
    model,
    max_tokens: 8000,
    thinking: { type: "adaptive" },
    output_config: { effort: opts.effort ?? "medium", format: zodOutputFormat(JobAdSchema) },
    system: [{ type: "text", text: DRAFTER_SYSTEM, cache_control: { type: "ephemeral" } }],
    messages: [{ role: "user", content: renderDrafterInput(briefText) }],
  });
  const latency_s = (Date.now() - t0) / 1000;
  if (res.stop_reason === "refusal") throw new Error(`drafter refused: ${res.stop_details?.explanation ?? ""}`);
  if (!res.parsed_output) throw new Error("drafter output failed to parse");
  const ad = fromSchema(res.parsed_output);
  const out: DraftResult = { ad, model: res.model, usage: res.usage, latency_s, prompt_version: DRAFTER_PROMPT_VERSION, brief_text: briefText };
  if (opts.score !== false) {
    const ctx = scoringContextFor(brief, briefText);
    const s = await score(ad, ctx, { client, model: opts.judgeModel });
    out.scorecard = s.scorecard; out.judge = s.judge;
  }
  return out;
}

/** The brief is the only source: grounding is judged against it. */
export function scoringContextFor(brief: HiringBrief, briefText = renderBrief(brief)): ScoringContext {
  return {
    jurisdiction: brief.jurisdiction as ScoringContext["jurisdiction"],
    channel: brief.channel,
    designated_employer: brief.designated_employer,
    hosted_apply: brief.hosted_apply,
    sources: [{ id: "brief", text: briefText }],
  };
}
