/**
 * Headless job-ad service. No UI. Node http + zod; runs under PM2 behind nginx like the rest of the fleet.
 *
 *   PORT=4310 npx tsx services/job-ad/api/server.ts
 *
 *   GET  /healthz                 → { ok, versions }
 *   GET  /v1/spec                 → the metric spec (ids, dimensions, gates, thresholds)
 *   POST /v1/scores  { ad, context?, judge? }        → { scorecard }           judge=false is free (deterministic only)
 *   POST /v1/drafts  { brief, options? }             → { ad, scorecard, meta }  one Opus call + one judge call
 *
 * Errors: 400 { error: "validation", issues[] } · 404 · 405 · 502 { error: "upstream", message } · 500.
 * Every response carries x-request-id. Bodies are JSON, max 256 KB.
 */
import http from "node:http";
import { randomUUID } from "node:crypto";
import { z } from "zod";
import Anthropic from "@anthropic-ai/sdk";
import { HiringBriefSchema } from "../drafter/brief.js";
import { draft } from "../drafter/draft.js";
import { DRAFTER_PROMPT_VERSION } from "../drafter/prompts/system.js";
import { JUDGE_PROMPT_VERSION } from "../metrics/judge/prompt.js";
import { loadSpec } from "../metrics/spec.js";
import { score, scoreDeterministic } from "../metrics/scorecard.js";
import { JobAdSchema, fromSchema } from "../schema.js";
import type { JobAd, ScoringContext } from "../metrics/types.js";

const spec = loadSpec();
const MAX_BODY = 256 * 1024;

/** Accept either the strict LLM-output shape (sentinels) or a natural JobAd (optionals). */
const JobAdInput = z.union([
  JobAdSchema.transform(fromSchema),
  z.object({
    title: z.string(), company: z.object({ name: z.string().optional(), about: z.string().optional() }).optional(), summary: z.string().optional(),
    responsibilities: z.array(z.string()).default([]), must_have: z.array(z.string()).default([]), nice_to_have: z.array(z.string()).default([]),
    pay: z.object({ min: z.number().optional(), max: z.number().optional(), currency: z.string().optional(), period: z.enum(["year", "month", "hour", "day", "week"]).optional(), basis: z.string().optional() }).nullable().optional(),
    location: z.string().optional(), work_mode: z.enum(["remote", "hybrid", "onsite", "unspecified"]).optional(), work_mode_detail: z.string().optional(),
    benefits: z.array(z.string()).default([]), team: z.string().optional(), process: z.string().optional(), closing_date: z.string().optional(),
    accessibility_statement: z.string().optional(), ee_statement: z.string().optional(), popia_notice: z.string().optional(), apply_contact: z.string().optional(), other: z.string().optional(),
  }),
]);
const ContextSchema = z.object({
  jurisdiction: z.string().default("ZA"), channel: z.enum(["default", "linkedin", "indeed"]).optional(), designated_employer: z.boolean().optional(), hosted_apply: z.boolean().optional(),
  sources: z.array(z.object({ id: z.string(), text: z.string() })).optional(),
}).prefault({});
const ScoreRequest = z.object({ ad: JobAdInput, context: ContextSchema, judge: z.boolean().default(true), judge_model: z.string().optional() });
const DraftRequest = z.object({ brief: HiringBriefSchema, options: z.object({ model: z.string().optional(), effort: z.enum(["low", "medium", "high"]).optional(), judge_model: z.string().optional(), score: z.boolean().default(true) }).prefault({}) });

export function createServer(deps: { client?: Anthropic } = {}) {
  const client = deps.client ?? new Anthropic();
  return http.createServer(async (req, res) => {
    const id = randomUUID();
    res.setHeader("x-request-id", id);
    const send = (status: number, body: unknown) => { res.writeHead(status, { "content-type": "application/json" }); res.end(JSON.stringify(body)); };
    try {
      const url = new URL(req.url ?? "/", "http://localhost");
      if (req.method === "GET" && url.pathname === "/healthz") return send(200, { ok: true, versions: { spec: spec.version, judge_prompt: JUDGE_PROMPT_VERSION, drafter_prompt: DRAFTER_PROMPT_VERSION, brief_schema: "0.2" } });
      if (req.method === "GET" && url.pathname === "/v1/spec") return send(200, spec);
      if (url.pathname !== "/v1/scores" && url.pathname !== "/v1/drafts") return send(404, { error: "not_found" });
      if (req.method !== "POST") return send(405, { error: "method_not_allowed" });
      const body = await readJson(req);
      if (body === undefined) return send(400, { error: "validation", issues: [{ path: [], message: "body must be JSON ≤ 256 KB" }] });

      if (url.pathname === "/v1/scores") {
        const p = ScoreRequest.safeParse(body);
        if (!p.success) return send(400, { error: "validation", issues: p.error.issues });
        const ad = p.data.ad as JobAd; const ctx = p.data.context as ScoringContext;
        if (!p.data.judge) return send(200, { scorecard: scoreDeterministic(ad, ctx), meta: { judge: null, spec: spec.version } });
        const r = await score(ad, ctx, { client, model: p.data.judge_model });
        return send(200, { scorecard: r.scorecard, meta: { judge: { model: r.judge.model, usage: r.judge.usage, latency_s: r.judge.latency_s, prompt_version: JUDGE_PROMPT_VERSION }, spec: spec.version } });
      }

      const p = DraftRequest.safeParse(body);
      if (!p.success) return send(400, { error: "validation", issues: p.error.issues });
      const d = await draft(p.data.brief, { client, model: p.data.options.model, effort: p.data.options.effort, judgeModel: p.data.options.judge_model, score: p.data.options.score });
      return send(200, {
        ad: d.ad, scorecard: d.scorecard ?? null,
        meta: { request_id: id, drafter: { model: d.model, usage: d.usage, latency_s: d.latency_s, prompt_version: d.prompt_version }, judge: d.judge ? { model: d.judge.model, usage: d.judge.usage, latency_s: d.judge.latency_s, prompt_version: JUDGE_PROMPT_VERSION } : null, spec: spec.version, brief_schema: p.data.brief.schema_version },
      });
    } catch (e) {
      if (e instanceof Anthropic.APIError) return send(502, { error: "upstream", status: e.status, message: e.message });
      console.error(`[${id}]`, e);
      return send(500, { error: "internal", message: String((e as Error).message ?? e) });
    }
  });
}

function readJson(req: http.IncomingMessage): Promise<unknown | undefined> {
  return new Promise((resolve) => {
    let size = 0; const chunks: Buffer[] = [];
    req.on("data", (c: Buffer) => { size += c.length; if (size > MAX_BODY) { resolve(undefined); req.destroy(); } else chunks.push(c); });
    req.on("end", () => { try { resolve(JSON.parse(Buffer.concat(chunks).toString("utf8") || "null")); } catch { resolve(undefined); } });
    req.on("error", () => resolve(undefined));
  });
}

if (process.argv[1] && /server\.ts$/.test(process.argv[1])) {
  const port = Number(process.env.PORT ?? 4310);
  createServer().listen(port, () => console.log(`job-ad service listening on :${port} (spec ${spec.version}, drafter ${DRAFTER_PROMPT_VERSION}, judge ${JUDGE_PROMPT_VERSION})`));
}
