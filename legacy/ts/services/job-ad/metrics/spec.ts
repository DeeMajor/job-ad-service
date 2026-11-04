import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import YAML from "yaml";

export interface Norm {
  kind: "band" | "linear";
  lo?: number;
  hi?: number;
  slack?: number;
}
export interface Gate { op: "==" | ">=" | "<="; value: number }
export interface MetricSpec {
  id: string;
  dimension: string;
  grader: "deterministic" | "lexicon" | "judge";
  type: "pass_fail" | "count" | "ratio" | "number";
  norm?: Norm;
  overrides?: Record<string, Norm>;
  gate?: Gate;
  params?: Record<string, unknown>;
  jurisdictions?: string[];
  applies_when?: string;
  /** Name of a boolean ScoringContext field; the metric is a gate only when that field is true. */
  gate_when?: string;
}
export interface Spec {
  version: string;
  publish_threshold: number;
  review_threshold: number;
  gates: string[];
  dimensions: Record<string, { weight: number; gate?: boolean }>;
  metrics: MetricSpec[];
}

const here = path.dirname(fileURLToPath(import.meta.url));
const DEFAULT_PATH = path.resolve(here, "../../../docs/job-ad-drafter/metrics/job-ad-metrics.yaml");

let cached: Spec | undefined;
export function loadSpec(file = DEFAULT_PATH): Spec {
  if (cached && file === DEFAULT_PATH) return cached;
  const spec = YAML.parse(fs.readFileSync(file, "utf8")) as Spec;
  const ids = new Set<string>();
  for (const m of spec.metrics) {
    if (ids.has(m.id)) throw new Error(`duplicate metric id ${m.id}`);
    ids.add(m.id);
    if (!spec.dimensions[m.dimension]) throw new Error(`metric ${m.id} has unknown dimension ${m.dimension}`);
  }
  if (file === DEFAULT_PATH) cached = spec;
  return spec;
}

export function metricSpec(spec: Spec, id: string): MetricSpec {
  const m = spec.metrics.find((x) => x.id === id);
  if (!m) throw new Error(`unknown metric ${id}`);
  return m;
}

/** A metric is a gate if listed in spec.gates (supports "prefix.*") or carries its own gate clause. */
export function isGate(spec: Spec, m: MetricSpec, ctx?: Record<string, unknown>): boolean {
  if (m.gate_when) return ctx?.[m.gate_when] === true;
  if (m.gate) return true;
  return spec.gates.some((g) => (g.endsWith(".*") ? m.id.startsWith(g.slice(0, -1)) : g === m.id));
}
