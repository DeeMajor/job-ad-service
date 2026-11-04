import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import type { JobAd, MetricResult, ScoringContext } from "../types.js";
import { longestSentence, bulletItems, countHits, fleschKincaidGrade, proseParagraphs, renderAd, words } from "../text.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const lex = <T>(name: string): T => JSON.parse(fs.readFileSync(path.join(here, "..", "lexicons", name), "utf8")) as T;
const GENDERED = lex<{ masculine: string[]; feminine: string[] }>("gendered.json");
const BUZZ = lex<{ terms: string[] }>("buzzwords.json").terms;
const EXCL = lex<{ gate: string[]; contextual: string[]; review: string[] }>("exclusionary.json");
const EXCL_CONTEXT = EXCL.contextual.map((p) => new RegExp(p, "gi"));
const GIMMICK = lex<{ terms: string[] }>("gimmick_titles.json").terms;

/** Partial result: the scorecard layer fills in dimension/grader/normalisation from the spec. */
export type Raw = Pick<MetricResult, "id" | "status" | "raw" | "pass" | "evidence" | "reasoning">;

const ok = (id: string, raw: number, evidence?: string[], reasoning?: string): Raw => ({ id, status: "ok", raw, evidence, reasoning });
const pf = (id: string, pass: boolean, evidence?: string[], reasoning?: string): Raw => ({ id, status: "ok", raw: pass ? 1 : 0, pass, evidence, reasoning });
const na = (id: string, reasoning: string): Raw => ({ id, status: "not_applicable", reasoning });
const ni = (id: string, reasoning: string): Raw => ({ id, status: "not_implemented", reasoning });

export function runDeterministic(ad: JobAd, ctx: ScoringContext): Raw[] {
  const text = renderAd(ad);
  const content = renderAd(ad, { headings: false }); // lexicon and pronoun metrics must not count our own section headings
  const body = words(text);
  const per100 = (n: number) => (body.length ? (n / body.length) * 100 : 0);
  const out: Raw[] = [];

  // ---- gate: an ad without the basics is unpublishable; without this, "absence of bad things" metrics reward an empty ad
  const missing: string[] = [];
  if (!ad.title?.trim()) missing.push("title");
  if (ad.responsibilities.length === 0) missing.push("responsibilities");
  if (ad.must_have.length === 0 && ad.nice_to_have.length === 0) missing.push("requirements");
  if (body.length < 100) missing.push(`only ${body.length} words`);
  out.push(pf("structure.minimum_content", missing.length === 0, missing));

  // ---- D1 clarity & structure
  const sections: [string, boolean][] = [
    ["title", !!ad.title?.trim()],
    ["about", !!ad.company?.about?.trim()],
    ["summary", !!ad.summary?.trim()],
    ["responsibilities", ad.responsibilities.length > 0],
    ["must_have", ad.must_have.length > 0],
    ["nice_to_have", ad.nice_to_have.length > 0],
    ["pay", !!(ad.pay && (ad.pay.min || ad.pay.max))],
    ["location_or_work_mode", !!ad.location?.trim() || (!!ad.work_mode && ad.work_mode !== "unspecified")],
    ["process", !!ad.process?.trim()],
  ];
  const present = sections.filter(([, p]) => p);
  out.push(ok("structure.sections_present", present.length / sections.length, sections.filter(([, p]) => !p).map(([n]) => `missing: ${n}`)));

  const title = ad.title ?? "";
  const gim = countHits(title, GIMMICK);
  const titleProblems: string[] = [];
  if (!title.trim()) titleProblems.push("empty title");
  if (title.length > 60) titleProblems.push(`title is ${title.length} chars`);
  if (gim.count) titleProblems.push(`gimmick words: ${gim.hits.join(", ")}`);
  if (/\((?:grade|band|level|job level|jl|ic|p|l|m)\s*\d{1,2}\)|\b(?:grade|band|job level|jl)\s*\d{1,2}\b/i.test(title) || /\b(?:P|L|M|IC|JL)\d{1,2}\b/.test(title)) titleProblems.push("internal level code in title");
  if (/\b(m\/w\/d|m\/f\/d|f\/m\/x)\b/i.test(title)) titleProblems.push("gender marker in title");
  out.push(pf("structure.title_quality", titleProblems.length === 0, titleProblems));

  out.push(ok("clarity.word_count", body.length));
  if (body.length < 20) {
    out.push(na("clarity.reading_grade", "too short to measure"));
    out.push(na("clarity.longest_sentence", "too short to measure"));
  } else {
    out.push(ok("clarity.reading_grade", round(fleschKincaidGrade(text))));
    out.push(ok("clarity.longest_sentence", longestSentence(text)));
  }

  // share of the ad a reader can scan: everything except prose paragraphs longer than 80 words
  const paras = proseParagraphs(ad);
  const longest = paras.reduce((a, p) => Math.max(a, words(p).length), 0);
  const wallWords = paras.reduce((a, p) => { const n = words(p).length; return a + (n > 80 ? n : 0); }, 0);
  const wallShare = body.length ? wallWords / body.length : 0;
  const bulletShare = body.length ? bulletItems(ad).reduce((a, b) => a + words(b).length, 0) / body.length : 0;
  if (body.length < 20) out.push(na("clarity.scannability", "too short to measure"));
  else out.push(ok("clarity.scannability", round4(1 - wallShare), longest > 80 ? [`longest paragraph ${longest} words`] : [], `wall-of-text share ${round(wallShare)}, bullet share ${round(bulletShare)}`));

  // ---- D2 specificity & honesty (deterministic part)
  out.push(ok("specific.must_have_count", ad.must_have.length));
  out.push(pf("specific.nice_to_have_split", ad.nice_to_have.length > 0 || ad.must_have.length <= 3, [], ad.nice_to_have.length ? "nice-to-haves separated" : "no nice-to-have list"));

  const yearsThreshold = 8; // seniority-agnostic placeholder until the taxonomy provides a band (Phase 3)
  const inflated = ad.must_have.filter((r) => {
    const m = r.match(/(\d{1,2})\s*\+?\s*(?:-\s*\d{1,2}\s*)?(?:years?|yrs?)/i);
    return m && Number(m[1]) > yearsThreshold;
  });
  out.push(ok("specific.years_inflation", inflated.length, inflated));

  const hasPay = !!(ad.pay && (ad.pay.min || ad.pay.max));
  out.push(pf("pay.range_present", hasPay));
  if (ad.pay?.min && ad.pay?.max && ad.pay.min > 0) {
    out.push(ok("pay.range_width", round((ad.pay.max - ad.pay.min) / ad.pay.min)));
  } else if (hasPay) {
    out.push(ok("pay.range_width", 0, [], "single figure disclosed"));
  } else {
    out.push(na("pay.range_width", "no pay disclosed"));
  }

  const buzz = countHits(content, BUZZ);
  out.push(ok("honesty.buzzword_density", round(per100(buzz.count)), buzz.hits));

  // ---- D3 inclusivity (lexicon part)
  const masc = countHits(content, GENDERED.masculine);
  const fem = countHits(content, GENDERED.feminine);
  out.push(ok("inclusive.gender_coding", round(per100(masc.count - fem.count)), [`masculine: ${masc.hits.join(", ") || "-"}`, `feminine: ${fem.hits.join(", ") || "-"}`]));

  const exclGate = countHits(content, EXCL.gate);
  const exclCtx = EXCL_CONTEXT.flatMap((re) => content.match(re) ?? []).map((h) => h.toLowerCase());
  const exclReview = countHits(content, EXCL.review).hits.filter((h) => !exclCtx.some((c) => c.includes(h)));
  out.push(ok("inclusive.exclusionary_terms", exclGate.count + exclCtx.length, [...exclGate.hits, ...exclCtx, ...exclReview.map((h) => `review: ${h}`)],
    exclReview.length ? "review-only hits are not counted; the judge assesses them in context" : undefined));

  out.push(pf("inclusive.accessibility_statement", !!ad.accessibility_statement?.trim() || /\b(accommodat|reasonable adjustment|accessib)/i.test(text)));

  // candidate address: second-person mentions per 100 words, each "the candidate"-style mention costing two
  const second = (content.match(/\b(you|your|yours|you'll|you’ll|you're|you’re|you've|you’ve|yourself)\b/gi) ?? []).length;
  const third = (content.match(/\b(the (?:ideal|successful|right|suitable|preferred) (?:candidate|applicant|person|incumbent)|the candidate|the applicant|the incumbent|the (?:successful|appointed) (?:individual|employee)|he\/she|she\/he|s\/he|him\/her|his\/her)\b/gi) ?? []).length;
  out.push(ok("inclusive.candidate_address", round(per100(second - 2 * third)), [`second-person ${second}`, `third-person-candidate ${third}`]));

  // ---- D4 compliance (deterministic part)
  if (ctx.jurisdiction === "ZA") {
    if (ctx.designated_employer === false) out.push(na("compliance.ee_statement", "not a designated employer"));
    else out.push(pf("compliance.ee_statement", !!ad.ee_statement?.trim() || /\b(employment equity|affirmative action|designated groups|EE (?:plan|targets|candidates))\b/i.test(text)));
    out.push(pf("compliance.popia_notice", !!ad.popia_notice?.trim() || /\b(POPIA|protection of personal information|personal information will be|privacy (?:notice|policy))\b/i.test(text)));
    out.push(na("compliance.pay_disclosure_law", "no mandatory pay disclosure in ZA"));
  } else {
    out.push(na("compliance.ee_statement", "ZA only"));
    out.push(na("compliance.popia_notice", "ZA only"));
    const mandated = ctx.jurisdiction === "EU" || /^US-(CO|CA|NY|WA|IL|HI|MD|MN|NJ|VT)$/.test(ctx.jurisdiction);
    out.push(mandated ? pf("compliance.pay_disclosure_law", hasPay) : na("compliance.pay_disclosure_law", "no mandate in jurisdiction"));
  }

  // ---- D6 searchability
  out.push(ni("seo.title_matches_taxonomy", "ESCO/OFO taxonomy arrives in Phase 3"));
  const first100 = words(text).slice(0, 100).join(" ");
  const titleTokens = words(title).filter((w) => w.length > 2 && !STOP.has(w));
  const titleEarly = titleTokens.length === 0 || titleTokens.some((t) => first100.includes(t));
  const locEarly = !ad.location || words(ad.location).some((t) => first100.includes(t));
  out.push(pf("seo.key_terms_early", titleEarly && locEarly, [], `title early: ${titleEarly}, location early: ${locEarly}`));
  const stuffLimit = Math.max(4, Math.ceil(body.length * 0.015)); // > 1.5 per 100 words, and at least 5
  const stuffed = titleTokens.filter((t) => body.filter((w) => w === t).length > stuffLimit);
  out.push(pf("seo.no_stuffing", stuffed.length === 0, stuffed.map((t) => `"${t}" repeated >${stuffLimit}×`)));

  // ---- D7 process
  if (ctx.hosted_apply) out.push(na("process.contact_or_link", "hosted on a job board with its own apply button"));
  else out.push(pf("process.contact_or_link", !!ad.apply_contact?.trim() || /\b(apply (?:here|now|via|at|online|by)|https?:\/\/|www\.|@[a-z0-9.-]+\.[a-z]{2,}|send your (?:cv|resume|application)|email your)\b/i.test(text)));

  return out;
}

const STOP = new Set(["and", "the", "for", "with", "of", "in", "to", "senior", "junior", "lead", "head", "manager", "officer", "specialist", "assistant", "intern"]);
const round = (n: number) => Math.round(n * 100) / 100;
const round4 = (n: number) => Math.round(n * 10000) / 10000;
