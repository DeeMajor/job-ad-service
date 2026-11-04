import { describe, expect, it } from "vitest";
import { runDeterministic } from "../deterministic/index.js";
import { scoreDeterministic } from "../scorecard.js";
import { fleschKincaidGrade, longestSentence, syllables, words, sentences } from "../text.js";
import { normalize } from "../normalize.js";
import { BAD_AD, EMPTY_AD, GOOD_AD } from "./fixtures.js";

const ZA = { jurisdiction: "ZA" as const, designated_employer: true };
const get = (rs: ReturnType<typeof runDeterministic>, id: string) => {
  const r = rs.find((x) => x.id === id);
  if (!r) throw new Error(`missing ${id}`);
  return r;
};

describe("text utils", () => {
  it("counts syllables roughly right", () => {
    expect(syllables("cat")).toBe(1);
    expect(syllables("logistics")).toBe(3);
    expect(syllables("reconcile")).toBe(3);
    expect(syllables("accommodation")).toBe(5);
  });
  it("splits sentences and bullets", () => {
    expect(sentences("One. Two! Three?\n• four").length).toBe(4);
  });
  it("FK grade: simple text is low, dense text is high", () => {
    expect(fleschKincaidGrade("The cat sat. The dog ran. We went home.")).toBeLessThan(3);
    expect(fleschKincaidGrade(BAD_AD.company!.about!)).toBeGreaterThan(14);
  });
  it("longest sentence", () => {
    expect(longestSentence("Short one. This sentence has exactly seven words in it.")).toBe(8);
  });
  it("words ignores punctuation and numbers", () => {
    expect(words("R1,500 a month; 20 days' leave")).toEqual(["a", "month", "days'", "leave"]);
  });
});

describe("normalize", () => {
  it("band is 1 inside and decays with slack", () => {
    const n = { kind: "band" as const, lo: 300, hi: 650, slack: 250 };
    expect(normalize(400, n, "count")).toBe(1);
    expect(normalize(300, n, "count")).toBe(1);
    expect(normalize(775, n, "count")).toBeCloseTo(0.5);
    expect(normalize(900, n, "count")).toBe(0);
    expect(normalize(50, n, "count")).toBe(0);
  });
  it("pass_fail maps 1/0", () => {
    expect(normalize(1, undefined, "pass_fail")).toBe(1);
    expect(normalize(0, undefined, "pass_fail")).toBe(0);
  });
});

describe("deterministic graders on the good ad", () => {
  const rs = runDeterministic(GOOD_AD, ZA);
  it("has all sections", () => expect(get(rs, "structure.sections_present").raw).toBe(1));
  it("title is clean", () => expect(get(rs, "structure.title_quality").pass).toBe(true));
  it("word count in band", () => {
    const wc = get(rs, "clarity.word_count").raw!;
    expect(wc).toBeGreaterThan(250); expect(wc).toBeLessThan(650);
  });
  it("readable, no run-on sentences", () => {
    expect(get(rs, "clarity.reading_grade").raw!).toBeLessThan(11);
    expect(get(rs, "clarity.longest_sentence").raw!).toBeLessThanOrEqual(35);
  });
  it("3 must-haves, nice-to-haves split", () => {
    expect(get(rs, "specific.must_have_count").raw).toBe(3);
    expect(get(rs, "specific.nice_to_have_split").pass).toBe(true);
  });
  it("no years inflation", () => expect(get(rs, "specific.years_inflation").raw).toBe(0));
  it("pay present with narrow range", () => {
    expect(get(rs, "pay.range_present").pass).toBe(true);
    expect(get(rs, "pay.range_width").raw).toBeCloseTo(0.22);
  });
  it("few buzzwords", () => expect(get(rs, "honesty.buzzword_density").raw!).toBeLessThan(0.5));
  it("gender coding near neutral", () => expect(Math.abs(get(rs, "inclusive.gender_coding").raw!)).toBeLessThan(1.5));
  it("no exclusionary terms", () => expect(get(rs, "inclusive.exclusionary_terms").raw).toBe(0));
  it("accessibility, EE, POPIA present", () => {
    expect(get(rs, "inclusive.accessibility_statement").pass).toBe(true);
    expect(get(rs, "compliance.ee_statement").pass).toBe(true);
    expect(get(rs, "compliance.popia_notice").pass).toBe(true);
  });
  it("addresses the candidate directly", () => expect(get(rs, "inclusive.candidate_address").raw!).toBeGreaterThanOrEqual(1));
  it("contact present", () => expect(get(rs, "process.contact_or_link").pass).toBe(true));
});

describe("deterministic graders on the bad ad", () => {
  const rs = runDeterministic(BAD_AD, ZA);
  it("misses sections", () => expect(get(rs, "structure.sections_present").raw!).toBeLessThan(0.8));
  it("title fails (gimmick, level code, length)", () => {
    const r = get(rs, "structure.title_quality");
    expect(r.pass).toBe(false);
    expect(r.evidence!.join(" ")).toMatch(/gimmick/);
    expect(r.evidence!.join(" ")).toMatch(/level code/);
  });
  it("too many must-haves, no split", () => {
    expect(get(rs, "specific.must_have_count").raw).toBe(8);
    expect(get(rs, "specific.nice_to_have_split").pass).toBe(false);
  });
  it("flags 15+ years", () => expect(get(rs, "specific.years_inflation").raw).toBe(1));
  it("wide pay range", () => expect(get(rs, "pay.range_width").raw).toBe(3));
  it("buzzword heavy", () => expect(get(rs, "honesty.buzzword_density").raw!).toBeGreaterThan(3));
  it("masculine coded", () => expect(get(rs, "inclusive.gender_coding").raw!).toBeGreaterThan(1));
  it("exclusionary terms found", () => {
    const r = get(rs, "inclusive.exclusionary_terms");
    expect(r.raw!).toBeGreaterThanOrEqual(4);
    expect(r.evidence).toEqual(expect.arrayContaining(["able-bodied", "native english speaker"]));
    expect(r.evidence!.some((e) => /young, energetic/.test(e))).toBe(true);
    expect(r.evidence!.some((e) => /under 35/.test(e))).toBe(true);
  });
  it("ambiguous words alone do not trip the gate", () => {
    const ad = { ...GOOD_AD, company: { name: "X", about: "We are a young company with a mature product and a single source of truth." } };
    const r = get(runDeterministic(ad, ZA), "inclusive.exclusionary_terms");
    expect(r.raw).toBe(0);
    expect(r.evidence).toEqual(expect.arrayContaining(["review: young", "review: mature", "review: single"]));
  });
  it("level codes: Grade 7 and P3 flagged, NDT Level 2 not", () => {
    const t = (title: string) => get(runDeterministic({ ...GOOD_AD, title }, ZA), "structure.title_quality");
    expect(t("Accountant (Grade 7)").pass).toBe(false);
    expect(t("Software Engineer P3").pass).toBe(false);
    expect(t("Non-Destructive Testing Technician – Level 2").pass).toBe(true);
  });
  it("third-person candidate language", () => expect(get(rs, "inclusive.candidate_address").raw!).toBeLessThan(1));
  it("hosted apply makes contact_or_link not applicable", () => {
    expect(get(runDeterministic(BAD_AD, { ...ZA, hosted_apply: true }), "process.contact_or_link").status).toBe("not_applicable");
  });
  it("no EE or POPIA", () => {
    expect(get(rs, "compliance.ee_statement").pass).toBe(false);
    expect(get(rs, "compliance.popia_notice").pass).toBe(false);
  });
});

describe("scorecard", () => {
  it("good ad: gates pass, high deterministic composite", () => {
    const sc = scoreDeterministic(GOOD_AD, ZA);
    expect(sc.gates_passed).toBe(true);
    expect(sc.composite).toBeGreaterThan(80);
    expect(sc.metrics.filter((m) => m.grader === "judge").every((m) => m.status === "skipped")).toBe(true);
    expect(sc.metrics.find((m) => m.id === "seo.title_matches_taxonomy")!.status).toBe("not_implemented");
  });
  it("bad ad: blocked by exclusionary terms and, for a designated employer, missing EE statement", () => {
    const sc = scoreDeterministic(BAD_AD, ZA);
    expect(sc.gates_passed).toBe(false);
    expect(sc.gate_failures).toEqual(expect.arrayContaining(["inclusive.exclusionary_terms", "compliance.ee_statement"]));
    expect(sc.gate_failures).not.toContain("compliance.popia_notice");
    const unknown = scoreDeterministic(BAD_AD, { jurisdiction: "ZA" });
    expect(unknown.gate_failures).not.toContain("compliance.ee_statement");
    expect(sc.composite).toBe(0);
    expect(sc.verdict).toBe("blocked");
  });
  it("empty ad: blocked and near zero", () => {
    const sc = scoreDeterministic(EMPTY_AD, ZA);
    expect(sc.gates_passed).toBe(false);
    expect(sc.dimensions.clarity.score).toBeLessThan(0.1);
  });
  it("non-designated ZA employer: EE statement not applicable", () => {
    const sc = scoreDeterministic({ ...GOOD_AD, ee_statement: undefined }, { jurisdiction: "ZA", designated_employer: false });
    expect(sc.metrics.find((m) => m.id === "compliance.ee_statement")!.status).toBe("not_applicable");
    expect(sc.gates_passed).toBe(true);
  });
  it("empty ad is blocked by the minimum-content gate even when designation is unknown", () => {
    const sc = scoreDeterministic(EMPTY_AD, { jurisdiction: "ZA" });
    expect(sc.gate_failures).toContain("structure.minimum_content");
    expect(sc.composite).toBe(0);
  });
  it("good ad passes minimum content", () => {
    expect(scoreDeterministic(GOOD_AD, ZA).gate_failures).not.toContain("structure.minimum_content");
  });
  it("linkedin channel shifts the word-count band", () => {
    const def = scoreDeterministic(GOOD_AD, ZA).metrics.find((m) => m.id === "clarity.word_count")!;
    const li = scoreDeterministic(GOOD_AD, { ...ZA, channel: "linkedin" }).metrics.find((m) => m.id === "clarity.word_count")!;
    expect(def.normalized).toBe(1);
    expect(li.normalized!).toBeLessThan(1);
  });
});
