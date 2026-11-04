import type { JobAd } from "./types.js";

/** Render the structured ad as plain text, the way a candidate would read it. */
export function renderAd(ad: JobAd, opts: { headings?: boolean } = {}): string {
  const h = (label: string, body: string) => (opts.headings === false ? body : `${label}\n${body}`);
  const parts: string[] = [];
  parts.push(ad.title);
  if (ad.company?.name) parts.push(ad.company.name);
  if (ad.location || ad.work_mode) parts.push([ad.location, ad.work_mode && ad.work_mode !== "unspecified" ? ad.work_mode : undefined, ad.work_mode_detail].filter(Boolean).join(" · "));
  if (ad.pay && (ad.pay.min || ad.pay.max)) parts.push(renderPay(ad.pay));
  if (ad.company?.about) parts.push(h("About us", ad.company.about));
  if (ad.summary) parts.push(h("About the role", ad.summary));
  if (ad.team) parts.push(h("Your team", ad.team));
  if (ad.responsibilities.length) parts.push(h("What you'll do", bullets(ad.responsibilities)));
  if (ad.must_have.length) parts.push(h("What you need", bullets(ad.must_have)));
  if (ad.nice_to_have.length) parts.push(h("Nice to have", bullets(ad.nice_to_have)));
  if (ad.benefits.length) parts.push(h("What we offer", bullets(ad.benefits)));
  if (ad.process) parts.push(h("How to apply", ad.process));
  if (ad.closing_date) parts.push("Closing date: " + ad.closing_date);
  if (ad.apply_contact) parts.push(ad.apply_contact);
  if (ad.accessibility_statement) parts.push(ad.accessibility_statement);
  if (ad.ee_statement) parts.push(ad.ee_statement);
  if (ad.popia_notice) parts.push(ad.popia_notice);
  if (ad.other) parts.push(ad.other);
  return parts.join("\n\n");
}

export function renderPay(p: NonNullable<JobAd["pay"]>): string {
  const cur = p.currency ?? "";
  const per = p.period ? ` per ${p.period}` : "";
  const range = p.min && p.max ? `${cur} ${fmt(p.min)} – ${fmt(p.max)}` : `${cur} ${fmt(p.min ?? p.max ?? 0)}`;
  return `Salary: ${range.trim()}${per}${p.basis ? `. ${p.basis}` : ""}`;
}
const fmt = (n: number) => n.toLocaleString("en-ZA");
const bullets = (xs: string[]) => xs.map((x) => `• ${x}`).join("\n");

/** Prose paragraphs (not bullet lists) of the ad, for paragraph-length checks. */
export function proseParagraphs(ad: JobAd): string[] {
  return [ad.company?.about, ad.summary, ad.team, ad.process, ad.other]
    .filter((x): x is string => !!x)
    .flatMap((x) => x.split(/\n{2,}/))
    .map((x) => x.trim())
    .filter(Boolean);
}

export function bulletItems(ad: JobAd): string[] {
  return [...ad.responsibilities, ...ad.must_have, ...ad.nice_to_have, ...ad.benefits];
}

export function words(text: string): string[] {
  return text.toLowerCase().match(/(?<![a-z0-9])[a-z][a-z'’-]*(?![a-z0-9])/g) ?? [];
}

export function sentences(text: string): string[] {
  return text
    .replace(/•/g, "\n")
    .split(/(?<=[.!?])\s+|\n+/)
    .map((s) => s.trim())
    .filter((s) => words(s).length > 0);
}

/** Heuristic English syllable count; adequate for Flesch–Kincaid at document scale. */
export function syllables(word: string): number {
  let w = word.toLowerCase().replace(/[^a-z]/g, "");
  if (w.length <= 3) return 1;
  w = w.replace(/^y/, "");
  if (!/[^aeiouy]le$/.test(w)) w = w.replace(/(?:es|ed|e)$/, "");
  const groups = w.match(/[aeiouy]{1,2}/g);
  return Math.max(1, groups ? groups.length : 1);
}

export function fleschKincaidGrade(text: string): number {
  const ws = words(text);
  const ss = sentences(text);
  if (ws.length === 0 || ss.length === 0) return 0;
  const syl = ws.reduce((a, w) => a + syllables(w), 0);
  return 0.39 * (ws.length / ss.length) + 11.8 * (syl / ws.length) - 15.59;
}

export function longestSentence(text: string): number {
  return sentences(text).reduce((a, s) => Math.max(a, words(s).length), 0);
}

/** Count stem/phrase hits. Stems match word-initially (Gaucher lexicon style); phrases match as whole phrases. */
export function countHits(text: string, terms: string[]): { count: number; hits: string[] } {
  const lower = text.toLowerCase();
  const hits: string[] = [];
  for (const t of terms) {
    const re = t.includes(" ")
      ? new RegExp(`\\b${escapeRe(t)}\\b`, "g")
      : new RegExp(`\\b${escapeRe(t)}[a-z]*`, "g");
    const m = lower.match(re);
    if (m) hits.push(...m);
  }
  return { count: hits.length, hits };
}

export function escapeRe(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
