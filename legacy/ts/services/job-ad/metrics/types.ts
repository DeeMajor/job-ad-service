/** Structured job ad. Both the drafter's output and the benchmark's normalised form of real ads. */
export type WorkMode = "remote" | "hybrid" | "onsite" | "unspecified";

export interface Pay {
  min?: number;
  max?: number;
  currency?: string;
  period?: "year" | "month" | "hour" | "day" | "week";
  /** How placement in the range is decided, if stated. */
  basis?: string;
}

export interface JobAd {
  title: string;
  company?: { name?: string; about?: string };
  summary?: string;
  responsibilities: string[];
  must_have: string[];
  nice_to_have: string[];
  pay?: Pay | null;
  location?: string;
  work_mode?: WorkMode;
  work_mode_detail?: string;
  benefits: string[];
  team?: string;
  /** Application steps, rounds, timeline. */
  process?: string;
  closing_date?: string;
  accessibility_statement?: string;
  ee_statement?: string;
  popia_notice?: string;
  apply_contact?: string;
  /** Anything that did not fit a section. */
  other?: string;
}

export type Jurisdiction = "ZA" | "EU" | "US" | `US-${string}`;
export type Channel = "default" | "linkedin" | "indeed";

/** Facts about the employer the scorer may need (not the ad text). */
export interface ScoringContext {
  jurisdiction: Jurisdiction;
  channel?: Channel;
  /** EEA designated employer (50+ employees or turnover threshold). */
  designated_employer?: boolean;
  /** True when the ad is published on an ATS/job board with its own apply button, so "how to apply" text is not expected. */
  hosted_apply?: boolean;
  /** Source material the ad's factual claims must be grounded in (brief + retrieved chunks). */
  sources?: { id: string; text: string }[];
}

export type MetricStatus = "ok" | "skipped" | "not_implemented" | "not_applicable" | "error";

export interface MetricResult {
  id: string;
  dimension: string;
  grader: "deterministic" | "lexicon" | "judge";
  status: MetricStatus;
  /** Raw measurement: count, ratio, number, or 0/1 for pass-fail. */
  raw?: number;
  /** 0..1 after normalisation; undefined when status != ok. */
  normalized?: number;
  pass?: boolean;
  /** True when this metric is a gate and it failed. */
  gate_failed?: boolean;
  /** Quoted spans or counts that justify the value. */
  evidence?: string[];
  reasoning?: string;
}

export interface Scorecard {
  spec_version: string;
  metrics: MetricResult[];
  gates_passed: boolean;
  gate_failures: string[];
  /** 0..100; 0 when any gate fails. */
  composite: number;
  /** Per-dimension mean of normalised metrics, 0..1. */
  dimensions: Record<string, { score: number; n: number }>;
  verdict: "publishable" | "review" | "regenerate" | "blocked";
}
