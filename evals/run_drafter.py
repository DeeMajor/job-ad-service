"""Phase 1 drafter eval.

  .venv/bin/python -m evals.run_drafter --variant baseline [--split test|validation|train|all] [--limit N] [--reps 1]
         [--model claude-opus-5] [--effort medium] [--judge-model claude-sonnet-5] [--concurrency 4]

Reads evals/cases/briefs.jsonl; writes evals/runs/<variant>/{results.jsonl, traces/<id>_rep<k>.json, errors.jsonl, report.md}. Resumable.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import anthropic

from job_ad.drafter.brief import HiringBrief
from job_ad.drafter.draft import draft
from job_ad.drafter.prompts import get_prompt
from job_ad.metrics.judge.prompt import JUDGE_PROMPT_VERSION
from job_ad.metrics.spec import load_spec
from job_ad.metrics.text import render_ad

PRICE = {"claude-opus-5": (5, 0.5, 6.25, 25), "claude-sonnet-5": (2, 0.2, 2.5, 10)}  # $/MTok: input, cache read, cache write, output


def cost_usd(model: str, u: dict) -> float:
    p = next((v for k, v in PRICE.items() if model.startswith(k)), (5, 0.5, 6.25, 25))
    return (u["input_tokens"] * p[0] + (u.get("cache_read_input_tokens") or 0) * p[1] + (u.get("cache_creation_input_tokens") or 0) * p[2] + u["output_tokens"] * p[3]) / 1e6


def mean(xs):
    xs = list(xs); return sum(xs) / len(xs) if xs else 0.0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default="baseline"); ap.add_argument("--split", default="all"); ap.add_argument("--limit", type=int); ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--model", default="claude-opus-5"); ap.add_argument("--effort", default="medium"); ap.add_argument("--judge-model", default="claude-sonnet-5"); ap.add_argument("--concurrency", type=int, default=4); ap.add_argument("--prompt-version"); ap.add_argument("--enrich", action="store_true")
    a = ap.parse_args(argv)
    DRAFTER_PROMPT_VERSION, DRAFTER_SYSTEM = get_prompt(a.prompt_version)
    spec = load_spec(); client = anthropic.Anthropic()
    out = Path("evals/runs") / a.variant; (out / "traces").mkdir(parents=True, exist_ok=True)
    cases = [json.loads(l) for l in Path("evals/cases/briefs.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    cases = [c for c in cases if a.split == "all" or c["split"] == a.split][: a.limit] if a.limit else [c for c in cases if a.split == "all" or c["split"] == a.split]
    res_p = out / "results.jsonl"
    done = {f"{r['prompt_id']}|{r['rep']}" for r in (json.loads(l) for l in res_p.read_text(encoding="utf-8").splitlines() if l.strip())} if res_p.exists() else set()
    jobs = [(c, rep) for c in cases for rep in range(a.reps) if f"{c['prompt_id']}|{rep}" not in done]
    log = lambda s: print(f"[eval] {s}", file=sys.stderr)
    log(f"variant={a.variant} split={a.split} cases={len(cases)} reps={a.reps} todo={len(jobs)} model={a.model}/{a.effort} judge={a.judge_model} drafter_prompt={DRAFTER_PROMPT_VERSION} judge_prompt={JUDGE_PROMPT_VERSION} spec={spec.version}")

    def run(job):
        c, rep = job
        brief = HiringBrief.model_validate(c["brief"])
        try:
            d = draft(brief, client=client, model=a.model, effort=a.effort, judge_model=a.judge_model, prompt_version=None if a.enrich else DRAFTER_PROMPT_VERSION, do_enrich=a.enrich)
            if not d.model.startswith(a.model):
                raise RuntimeError(f"served model {d.model} != requested {a.model}")
            sc = d.scorecard
            grade = {"composite": sc.composite, "gates_passed": 1 if sc.gates_passed else 0, "publishable": 1 if sc.verdict == "publishable" else 0, "beats_real": 1 if sc.composite > c["real_ad"]["composite"] else 0}
            grade.update({m.id: m.normalized for m in sc.metrics if m.status == "ok" and m.normalized is not None})
            du, ju = d.usage.model_dump(), d.judge.usage.model_dump()
            row = {"prompt_id": c["prompt_id"], "rep": rep, "prompt": d.brief_text, "tags": c["tags"], "split": c["split"], "status": "ok", "stop_reason": "end_turn", "grade": grade,
                   "gate_failures": sc.gate_failures, "verdict": sc.verdict, "real_ad_composite": c["real_ad"]["composite"], "model": d.model, "usage": du, "judge_model": d.judge.model, "judge_usage": ju,
                   "latency_s": d.latency_s, "judge_latency_s": d.judge.latency_s, "words": len(render_ad(d.ad).split()),
                   "cost_usd": cost_usd(d.model, du) + cost_usd(d.judge.model, ju) + ((cost_usd(d.enrichment.model, d.enrichment.usage) + 0.01 * d.enrichment.searches) if d.enrichment else 0.0),
                   "enrichment": {"searches": d.enrichment.searches, "facts": len(d.enrichment.facts), "sources": [s.id for s in d.sources], "latency_s": d.enrichment.latency_s} if d.enrichment else None,
                   "web_sources": [s.text for s in d.sources],
                   "drafter_prompt_version": DRAFTER_PROMPT_VERSION, "judge_prompt_version": JUDGE_PROMPT_VERSION, "spec_version": spec.version}
            with res_p.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            trace = [{"role": "system", "content": DRAFTER_SYSTEM}, {"role": "user", "content": d.brief_text}, {"role": "assistant", "content": render_ad(d.ad)},
                     {"role": "tool_call", "name": "score", "content": json.dumps({"judge_model": a.judge_model})},
                     {"role": "tool_result", "content": json.dumps({"composite": sc.composite, "verdict": sc.verdict, "gate_failures": sc.gate_failures,
                                                                      "metrics": [{"id": m.id, "raw": m.raw, "normalized": m.normalized, "evidence": m.evidence, "reasoning": m.reasoning} for m in sc.metrics if m.status == "ok"]}, indent=1, ensure_ascii=False)}]
            (out / "traces" / f"{c['prompt_id']}_rep{rep}.json").write_text(json.dumps({"ad": d.ad.model_dump(), "trace": trace}, indent=1, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            with (out / "errors.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps({"prompt_id": c["prompt_id"], "rep": rep, "error": str(e), "at": time.strftime("%Y-%m-%dT%H:%M:%S")}) + "\n")
            log(f"error {c['prompt_id']} rep{rep}: {str(e)[:160]}")

    with ThreadPoolExecutor(max_workers=max(1, a.concurrency)) as ex:
        list(ex.map(run, jobs))
    rows = [json.loads(l) for l in res_p.read_text(encoding="utf-8").splitlines() if l.strip()] if res_p.exists() else []
    md = report(rows, a, spec)
    (out / "report.md").write_text(md, encoding="utf-8"); print(md)


def report(rows, a, spec) -> str:
    DRAFTER_PROMPT_VERSION = rows[0]["drafter_prompt_version"] if rows else get_prompt(a.prompt_version)[0]
    f = lambda x: f"{x:.2f}" if isinstance(x, float) and not x.is_integer() else str(int(x)) if isinstance(x, (int, float)) else str(x)
    pct = lambda x: f"{round(x * 100)}%"
    group = lambda k: {v: [r for r in rows if k(r) == v] for v in sorted({k(r) for r in rows})}
    L = [f"# Drafter eval — variant {a.variant}", "", f"Generated {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}. {len(rows)} rows. Drafter {a.model}/{a.effort}, prompt {DRAFTER_PROMPT_VERSION}; judge {a.judge_model}, prompt {JUDGE_PROMPT_VERSION}; spec {spec.version}.", "",
         "## Headline", "", "| Split | n | composite mean | median | publishable | gates pass | beats real ad | real ad mean |", "|---|---|---|---|---|---|---|---|"]
    for s, xs in group(lambda r: r["split"]).items():
        comps = sorted(r["grade"]["composite"] for r in xs)
        L.append(f"| {s} | {len(xs)} | {f(mean(comps))} | {f(comps[len(comps) // 2])} | {pct(mean(r['grade']['publishable'] for r in xs))} | {pct(mean(r['grade']['gates_passed'] for r in xs))} | {pct(mean(r['grade']['beats_real'] for r in xs))} | {f(mean(r['real_ad_composite'] for r in xs))} |")
    gf = {}
    for r in rows:
        for g in r["gate_failures"]:
            gf[g] = gf.get(g, 0) + 1
    if gf:
        L += ["", "Gate failures: " + "; ".join(f"{k} {v}/{len(rows)}" for k, v in gf.items())]
    L += ["", "## By role", "", "| Role | n | composite | beats real | real mean |", "|---|---|---|---|---|"]
    L += [f"| {role} | {len(xs)} | {f(mean(r['grade']['composite'] for r in xs))} | {pct(mean(r['grade']['beats_real'] for r in xs))} | {f(mean(r['real_ad_composite'] for r in xs))} |" for role, xs in group(lambda r: r["tags"][0]).items()]
    by_case = group(lambda r: r["prompt_id"])
    spreads = [max(r["grade"]["composite"] for r in xs) - min(r["grade"]["composite"] for r in xs) for xs in by_case.values() if len(xs) > 1]
    if spreads:
        L += ["", f"Noise floor: {len(spreads)} cases with repeats; mean composite spread {f(mean(spreads))}, max {f(max(spreads))}."]
    ids = sorted({k for r in rows for k in r["grade"] if "." in k})
    weak = sorted(((id_, mean(r["grade"][id_] for r in rows if id_ in r["grade"]), sum(1 for r in rows if id_ in r["grade"])) for id_ in ids), key=lambda t: t[1])[:10]
    L += ["", "## Weakest metrics (mean normalised, lowest first)", "", "| Metric | mean | n |", "|---|---|---|"] + [f"| {i} | {f(m)} | {n} |" for i, m, n in weak]
    if rows:
        L += ["", "## Cost and latency", "", f"Drafter: mean input {f(mean(r['usage']['input_tokens'] + (r['usage'].get('cache_read_input_tokens') or 0) + (r['usage'].get('cache_creation_input_tokens') or 0) for r in rows))} tokens, output {f(mean(r['usage']['output_tokens'] for r in rows))}, latency {f(mean(r['latency_s'] for r in rows))} s. Mean words per ad {f(mean(r['words'] for r in rows))}. **Mean cost per draft incl. judge: ${mean(r['cost_usd'] for r in rows):.3f}** (total ${sum(r['cost_usd'] for r in rows):.2f})."]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    main()
