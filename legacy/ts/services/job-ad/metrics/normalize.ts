import type { MetricSpec, Norm } from "./spec.js";

/**
 * Map a raw value to 0..1.
 * band:   1 inside [lo, hi]; linear decay to 0 at lo-slack / hi+slack. Missing lo or hi = unbounded on that side.
 * linear: raw / lo (capped at 1) — for ratios where lo is the full-score value.
 */
export function normalize(raw: number, norm: Norm | undefined, type: MetricSpec["type"]): number {
  if (type === "pass_fail") return raw >= 1 ? 1 : 0;
  if (!norm) return clamp01(raw);
  if (norm.kind === "linear") return clamp01(raw / (norm.lo ?? 1));
  const lo = norm.lo ?? -Infinity;
  const hi = norm.hi ?? Infinity;
  const slack = norm.slack ?? 0;
  if (raw >= lo && raw <= hi) return 1;
  if (slack <= 0) return 0;
  if (raw < lo) return clamp01(1 - (lo - raw) / slack);
  return clamp01(1 - (raw - hi) / slack);
}

export function pickNorm(m: MetricSpec, channel?: string): Norm | undefined {
  if (channel && m.overrides && m.overrides[channel]) return m.overrides[channel];
  return m.norm;
}

export function gatePasses(raw: number, gate: { op: string; value: number }): boolean {
  switch (gate.op) {
    case "==": return raw === gate.value;
    case ">=": return raw >= gate.value;
    case "<=": return raw <= gate.value;
    default: throw new Error(`unknown gate op ${gate.op}`);
  }
}

function clamp01(x: number): number {
  if (Number.isNaN(x)) return 0;
  return Math.max(0, Math.min(1, x));
}
