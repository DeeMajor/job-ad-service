"""Phase 0 scorer benchmark runner (Python port; same contract and output files as the TS version).

  .venv/bin/python -m bench.run --version v1 [--run r4] [--normalizer llm|heuristic] [--judge on|off] [--limit N]
         [--judge-model claude-sonnet-5] [--reference-model claude-opus-5] [--reps 3] [--agreement-sample 40] [--concurrency 6]

Reads  bench/data/raw/<version>/ads.jsonl
Writes bench/data/out/<version>/normalized.jsonl (shared) and bench/data/out/<version>/<run>/{scores,perturbations,agreement,errors}.jsonl + report.{json,md}
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Optional

from job_ad.metrics.judge.prompt import JUDGE_PROMPT_VERSION
from job_ad.metrics.judge.run import run_judge
from job_ad.metrics.scorecard import build_scorecard
from job_ad.metrics.deterministic import run_deterministic
from job_ad.metrics.spec import load_spec
from job_ad.metrics.text import render_ad
from job_ad.metrics.types import JobAd, Scorecard, ScoringContext, Source
from tests.fixtures import EMPTY_AD, GOOD_AD

from .normalize import normalize_heuristic, normalize_llm
from .perturb import PERTURBATIONS

TARGETS = dict(det=0.9, judge=0.85, kappa=0.7, kappa_gate=0.8, mae=0.2, consistency=0.9, judge_noise=0.1, ratio_spread=0.2)
GATE_IDS = {"honesty.grounding", "compliance.protected_grounds", "compliance.no_prohibited_requests"}
HOSTED = {"workday", "greenhouse", "lever", "workable", "arbeitnow", "remotive"}


def jl_read(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []


def jl_append(p: Path, row: dict) -> None:
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="v1"); ap.add_argument("--run", default="r1"); ap.add_argument("--normalizer", default="llm", choices=["llm", "heuristic"])
    ap.add_argument("--judge", default="on", choices=["on", "off"]); ap.add_argument("--limit", type=int); ap.add_argument("--judge-model", default="claude-sonnet-5")
    ap.add_argument("--reference-model", default="claude-opus-5"); ap.add_argument("--reps", type=int, default=3); ap.add_argument("--agreement-sample", type=int, default=40)
    ap.add_argument("--concurrency", type=int, default=6)
    a = ap.parse_args(argv)
    spec = load_spec()
    judge_on = a.judge == "on"
    client = None
    if judge_on or a.normalizer == "llm":
        import anthropic
        client = anthropic.Anthropic()
    raw_p = Path("bench/data/raw") / a.version / "ads.jsonl"
    out_shared = Path("bench/data/out") / a.version
    out = out_shared / a.run
    out.mkdir(parents=True, exist_ok=True)
    raws = jl_read(raw_p)[: a.limit] if a.limit else jl_read(raw_p)
    log = lambda s: print(f"[bench] {s}", file=sys.stderr)
    log(f"corpus: {len(raws)} ads; run={a.run} normalizer={a.normalizer} judge={a.judge_model if judge_on else 'off'} judge_prompt={JUDGE_PROMPT_VERSION} spec={spec.version}")

    def ctx_of(r: dict, sources=None) -> ScoringContext:
        j = "ZA" if r["country"] == "ZA" else "EU" if r["country"] == "DE" else "US"
        return ScoringContext(jurisdiction=j, hosted_apply=r["source"] in HOSTED, sources=sources)

    def err(stage, id_, e):
        jl_append(out / "errors.jsonl", {"stage": stage, "id": id_, "error": str(e), "at": time.strftime("%Y-%m-%dT%H:%M:%S")})
        log(f"error in {stage} for {id_}: {str(e)[:200]}")

    def pool(items, fn, n=a.concurrency):
        with ThreadPoolExecutor(max_workers=max(1, n)) as ex:
            list(ex.map(fn, items))

    # 1. normalise (shared, resumable)
    norm_p = out_shared / "normalized.jsonl"
    normalized: dict[str, JobAd] = {x["id"]: JobAd.model_validate(x["ad"]) for x in jl_read(norm_p)}
    norm_usage: list = []

    def do_norm(r):
        try:
            if a.normalizer == "llm":
                n = normalize_llm(r, client); norm_usage.append(n.usage); ad = n.ad
            else:
                ad = normalize_heuristic(r)
            normalized[r["id"]] = ad
            jl_append(norm_p, {"id": r["id"], "ad": ad.model_dump()})
        except Exception as e:
            err("normalize", r["id"], e)
    pool([r for r in raws if r["id"] not in normalized], do_norm)
    log(f"normalized: {len(normalized)}")

    def score_one(r, ad: JobAd, ctx: ScoringContext) -> dict:
        det = run_deterministic(ad, ctx)
        if not judge_on:
            return {"scorecard": build_scorecard(det, ctx, spec)}
        j = run_judge(ad, ctx, client=client, model=a.judge_model)
        return {"scorecard": build_scorecard([*det, *j.results], ctx, spec), "judge_model": j.model, "judge_usage": j.usage.model_dump(), "latency_s": j.latency_s}

    # 2. score originals
    score_p = out / "scores.jsonl"
    scored: dict[str, dict] = {x["id"]: x for x in jl_read(score_p)}

    def do_score(r):
        try:
            s = score_one(r, normalized[r["id"]], ctx_of(r))
            row = {"id": r["id"], "title": r["title"], "source": r["source"], "full_text": r.get("full_text", True), "scorecard": s["scorecard"].model_dump(by_alias=True),
                   "judge_model": s.get("judge_model"), "judge_usage": s.get("judge_usage"), "latency_s": s.get("latency_s")}
            scored[r["id"]] = row; jl_append(score_p, row)
        except Exception as e:
            err("score", r["id"], e)
    pool([r for r in raws if r["id"] in normalized and r["id"] not in scored], do_score)
    log(f"scored: {len(scored)}")

    # 3. perturbation detection
    pert_p = out / "perturbations.jsonl"
    pert = jl_read(pert_p)
    done = {f"{p['id']}|{p['perturbation']}" for p in pert}
    jobs = []
    for r in raws:
        ad = normalized.get(r["id"]); orig = scored.get(r["id"])
        if not ad or not orig:
            continue
        for p in PERTURBATIONS:
            if f"{r['id']}|{p.name}" in done or (p.needs_judge and not judge_on):
                continue
            pa = p.apply(ad)
            if pa is not None:
                jobs.append((r, ad, orig, p, pa))

    def do_pert(job):
        r, ad, orig, p, pa = job
        try:
            ctx = ctx_of(r, sources=[Source(id="original_ad", text=render_ad(ad))] if p.uses_original_as_source else None)
            orig_card = score_one(r, ad, ctx)["scorecard"] if p.uses_original_as_source else Scorecard.model_validate(orig["scorecard"])
            pc = score_one(r, pa, ctx)["scorecard"]
            for t in p.targets:
                o = orig_card.metric(t); q = pc.metric(t)
                both = o.status == "ok" and q.status == "ok"
                headroom = both and (o.normalized or 0) > 0
                tol = TARGETS["judge_noise"] if p.needs_judge else 0
                row = {"id": r["id"], "perturbation": p.name, "target": t, "needs_judge": p.needs_judge, "original": o.normalized, "perturbed": q.normalized,
                       "detected": (q.normalized < o.normalized) if headroom else None, "false_improvement": bool(both and q.normalized > o.normalized + tol)}
                pert.append(row); jl_append(pert_p, row)
        except Exception as e:
            err("perturb", f"{r['id']}|{p.name}", e)
    pool(jobs, do_pert)
    log(f"perturbation rows: {len(pert)}")

    # 4. judge agreement
    agree_p = out / "agreement.jsonl"
    agree = jl_read(agree_p)
    if judge_on and not agree:
        sample = [r for r in raws if r["id"] in normalized][: a.agreement_sample]

        def do_agree(r):
            ad = normalized[r["id"]]
            try:
                ref = run_judge(ad, ctx_of(r), client=client, model=a.reference_model, effort="high")
                reps = [run_judge(ad, ctx_of(r), client=client, model=a.judge_model) for _ in range(a.reps)]
                for m in ref.results:
                    if m.status != "ok":
                        continue
                    jr = [next(x for x in j.results if x.id == m.id) for j in reps]
                    row = {"id": r["id"], "metric": m.id, "reference": m.raw, "judge": [x.raw for x in jr], "reference_reasoning": m.reasoning, "judge_reasoning": jr[0].reasoning if jr else None}
                    agree.append(row); jl_append(agree_p, row)
            except Exception as e:
                err("agreement", r["id"], e)
        pool(sample, do_agree, max(1, a.concurrency // 2))

    # 5. probes
    probes = []
    pctx = ScoringContext(jurisdiction="ZA", designated_employer=True, hosted_apply=False)
    for name, ad, expect in [("empty", EMPTY_AD, "not ready (must-fix reasons)"), ("i_dont_know", EMPTY_AD.model_copy(update={"title": "Job", "summary": "I don't know what this role is. Apply if you like."}), "not ready (must-fix reasons)"),
                             ("wrong_role_confident", GOOD_AD.model_copy(update={"title": "Senior Boilermaker"}), "structure.title_matches_content fails when judged"), ("oracle_good_fixture", GOOD_AD, "no must-fix reasons, composite >= 80")]:
        try:
            sc = score_one({"id": f"probe:{name}", "title": name, "source": "probe", "country": "ZA"}, ad, pctx)["scorecard"]
        except Exception as e:
            probes.append({"name": name, "expect": expect, "pass": False, "error": str(e)}); continue
        if name == "oracle_good_fixture":
            ok = sc.gates_passed and sc.composite >= 80
        elif name == "wrong_role_confident":
            ok = (sc.metric("structure.title_matches_content").pass_ is False) if judge_on else None
        else:
            ok = (not sc.gates_passed) or sc.composite < 20
        probes.append({"name": name, "expect": expect, "composite": sc.composite, "gates_passed": sc.gates_passed, "gate_failures": sc.gate_failures, "pass": ok})

    # 6. report
    rows = list(scored.values())
    report = build_report(a, spec, judge_on, rows, pert, agree, probes, norm_usage)
    (out / "report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    md = render_md(report, a)
    (out / "report.md").write_text(md, encoding="utf-8")
    print(md)


def cohen_kappa(a: list, b: list) -> float:
    try:
        from sklearn.metrics import cohen_kappa_score
        return float(cohen_kappa_score(a, b))
    except Exception:
        return 0.0


def bin_(v: float) -> int:
    if v in (0, 1):
        return int(v)
    if v > 1:
        return 2
    return 0 if v < 0.5 else 1 if v < 0.85 else 2


def build_report(a, spec, judge_on, rows, pert, agree, probes, norm_usage) -> dict:
    comps = sorted(r["scorecard"]["composite"] for r in rows)
    q = lambda p: comps[min(len(comps) - 1, int(p * len(comps)))] if comps else 0
    metric_dist = {}
    for m in spec.metrics:
        vals = [mm for r in rows for mm in r["scorecard"]["metrics"] if mm["id"] == m.id and mm["status"] == "ok"]
        if vals:
            d = {"n": len(vals), "mean_norm": mean(v["normalized"] for v in vals), "mean_raw": mean(v["raw"] for v in vals)}
            if m.type == "pass_fail":
                d["pass_rate"] = mean(1 if v.get("pass") else 0 for v in vals)
            metric_dist[m.id] = d
    gate_fail = {}
    for r in rows:
        for g in r["scorecard"]["gate_failures"]:
            gate_fail[g] = gate_fail.get(g, 0) + 1 / len(rows)
    detection: dict[str, dict] = {}
    for p in pert:
        k = f"{p['perturbation']}→{p['target']}"
        d = detection.setdefault(k, {"perturbation": p["perturbation"], "target": p["target"], "n_total": 0, "n": 0, "hits": 0, "false_improvements": 0, "target_rate": TARGETS["judge"] if p["needs_judge"] else TARGETS["det"]})
        d["n_total"] += 1
        if p["false_improvement"]:
            d["false_improvements"] += 1
        if p["detected"] is None:
            continue
        d["n"] += 1; d["hits"] += 1 if p["detected"] else 0
    for d in detection.values():
        d["rate"] = d["hits"] / d["n"] if d["n"] else 0.0
        d["pass"] = d["n"] >= 5 and d["rate"] >= d["target_rate"] and d["false_improvements"] == 0
    ratio_ids = {m.id for m in spec.metrics if m.type == "ratio" and m.grader == "judge"}
    agreement = {}
    by_metric: dict[str, list] = {}
    for x in agree:
        by_metric.setdefault(x["metric"], []).append(x)
    for metric, xs in by_metric.items():
        if metric in ratio_ids:
            mae = mean(abs(x["reference"] - x["judge"][0]) for x in xs)
            cons = mean(1 if (max(x["judge"]) - min(x["judge"])) <= TARGETS["ratio_spread"] else 0 for x in xs)
            agreement[metric] = {"n": len(xs), "type": "ratio", "mae": mae, "consistency": cons, "target": f"MAE ≤ {TARGETS['mae']}", "pass": mae <= TARGETS["mae"] and cons >= TARGETS["consistency"]}
        else:
            ref = [bin_(x["reference"]) for x in xs]; j = [bin_(x["judge"][0]) for x in xs]
            cons = mean(1 if all(bin_(v) == bin_(x["judge"][0]) for v in x["judge"]) else 0 for x in xs)
            identical = ref == j
            positives = max(sum(1 for v in ref if v != 0), sum(1 for v in j if v != 0))
            pct = mean(1 if r_ == j_ else 0 for r_, j_ in zip(ref, j))
            tk = TARGETS["kappa_gate"] if metric in GATE_IDS else TARGETS["kappa"]
            if positives <= 2 and not identical:
                agreement[metric] = {"n": len(xs), "type": "categorical (rare positives: κ unstable, % agreement used)", "kappa": pct, "consistency": cons, "target": "agree ≥ 0.9", "pass": pct >= 0.9 and cons >= TARGETS["consistency"]}
            else:
                k = 1.0 if identical else cohen_kappa(ref, j)
                agreement[metric] = {"n": len(xs), "type": "categorical", "kappa": k, "consistency": cons, "target": f"κ ≥ {tk}", "pass": (identical or k >= tk) and cons >= TARGETS["consistency"]}
    ju = [r for r in rows if r.get("judge_usage")]
    tot_in = lambda u: u["input_tokens"] + (u.get("cache_read_input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0)
    cost = {"judge_calls": len(ju), "judge_mean_input_tokens": mean(tot_in(r["judge_usage"]) for r in ju), "judge_mean_output_tokens": mean(r["judge_usage"]["output_tokens"] for r in ju),
            "judge_mean_latency_s": mean(r["latency_s"] for r in ju), "judge_cache_read_share": mean((r["judge_usage"].get("cache_read_input_tokens") or 0) / max(1, tot_in(r["judge_usage"])) for r in ju),
            "normalize_calls": len(norm_usage), "normalize_mean_tokens": mean(getattr(u, "input_tokens", 0) + getattr(u, "output_tokens", 0) for u in norm_usage)}
    evaluable = [d for d in detection.values() if d["n"] >= 5]
    insufficient = [f"{d['perturbation']}→{d['target']}" for d in detection.values() if d["n"] < 5]
    exit_ = {"perturbation_all_pass": bool(evaluable) and all(d["pass"] for d in evaluable), "perturbation_insufficient_data": insufficient,
             "agreement_all_pass": (bool(agreement) and all(x["pass"] for x in agreement.values())) if judge_on else None, "probes_all_pass": all(p.get("pass") is not False for p in probes)}
    return {"version": a.version, "run": a.run, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "spec_version": spec.version, "judge_prompt_version": JUDGE_PROMPT_VERSION,
            "config": {"normalizer": a.normalizer, "judge": a.judge_model if judge_on else None, "reference_model": a.reference_model if judge_on else None, "reps": a.reps},
            "corpus": {"n": len(rows), "full_text_share": mean(1 if r.get("full_text") else 0 for r in rows), "sources": {s: sum(1 for r in rows if r["source"] == s) for s in {r["source"] for r in rows}}},
            "composite": {"mean": mean(comps), "p10": q(.1), "p25": q(.25), "median": q(.5), "p75": q(.75), "p90": q(.9), "gates_pass_rate": mean(1 if r["scorecard"]["gates_passed"] else 0 for r in rows),
                          "verdicts": {v: sum(1 for r in rows if r["scorecard"]["verdict"] == v) for v in {r["scorecard"]["verdict"] for r in rows}}},
            "gate_fail_rate": gate_fail, "metrics": metric_dist, "detection": detection, "agreement": agreement, "probes": probes, "cost": cost, "exit": exit_}


def render_md(r: dict, a) -> str:
    pct = lambda x: "–" if x is None else f"{round(x * 100)}%"
    f = lambda x: "–" if x is None else (str(x) if isinstance(x, int) or float(x).is_integer() else f"{x:.2f}")
    L = [f"# Phase 0 scorer benchmark — {r['version']} / {r['run']}", "", f"Generated {r['generated_at']}. Spec {r['spec_version']}, judge prompt {r['judge_prompt_version']}. Normalizer: {r['config']['normalizer']}; judge: {r['config']['judge'] or 'off'}"
         + (f"; reference: {r['config']['reference_model']}; reps: {r['config']['reps']}" if r['config']['reference_model'] else "") + ". (Python runner)", ""]
    e = r["exit"]
    L += ["## Exit criteria", "", "| Criterion | Result |", "|---|---|",
          f"| Perturbation detection ≥ {TARGETS['det']} (det) / {TARGETS['judge']} (judge) on every target | {'PASS' if e['perturbation_all_pass'] else 'FAIL'}" + (f" (insufficient data: {', '.join(e['perturbation_insufficient_data'])})" if e['perturbation_insufficient_data'] else "") + " |",
          f"| Judge–reference κ ≥ {TARGETS['kappa']} ({TARGETS['kappa_gate']} gates) or MAE ≤ {TARGETS['mae']} for ratios, self-consistency ≥ {TARGETS['consistency']} | {'not run (judge off)' if e['agreement_all_pass'] is None else 'PASS' if e['agreement_all_pass'] else 'FAIL'} |",
          f"| Null / oracle probes | {'PASS' if e['probes_all_pass'] else 'FAIL'} |", ""]
    c = r["composite"]
    L += ["## Corpus and real-ad distribution", "", "| | |", "|---|---|", f"| Ads | {r['corpus']['n']} (full text {pct(r['corpus']['full_text_share'])}) |", f"| Sources | {', '.join(f'{k}: {v}' for k, v in r['corpus']['sources'].items())} |",
          f"| Composite mean / median | {f(c['mean'])} / {f(c['median'])} |", f"| Composite p10 / p25 / p75 / p90 | {f(c['p10'])} / {f(c['p25'])} / {f(c['p75'])} / {f(c['p90'])} |", f"| Gates pass rate | {pct(c['gates_pass_rate'])} |",
          f"| Verdicts | {', '.join(f'{k}: {v}' for k, v in c['verdicts'].items())} |", ""]
    if r["gate_fail_rate"]:
        L += ["Gate failure rates: " + "; ".join(f"{k} {pct(v)}" for k, v in r["gate_fail_rate"].items()), ""]
    L += ["## Metric distribution on real ads", "", "| Metric | n | mean raw | mean norm | pass rate |", "|---|---|---|---|---|"]
    L += [f"| {id_} | {m['n']} | {f(m['mean_raw'])} | {f(m['mean_norm'])} | {pct(m.get('pass_rate'))} |" for id_, m in r["metrics"].items()]
    L += ["", "## Perturbation detection", "", f"Detection is measured only on ads with headroom (original normalised score > 0). \"n\" is eligible ads out of all perturbed; a pass needs n ≥ 5, rate ≥ target and zero false improvements (perturbed scoring higher than original by more than judge noise, {TARGETS['judge_noise']} for judged metrics).", "",
          "| Perturbation | Target metric | n (of) | detected | false impr. | target | |", "|---|---|---|---|---|---|---|"]
    L += [f"| {d['perturbation']} | {d['target']} | {d['n']} ({d['n_total']}) | {pct(d['rate'])} | {d['false_improvements']} | {pct(d['target_rate'])} | {'ok' if d['pass'] else 'too few' if d['n'] < 5 else 'FAIL'} |" for d in r["detection"].values()]
    if r["agreement"]:
        L += ["", "## Judge agreement", "", f"Categorical metrics: Cohen's κ vs the reference model. Ratio metrics: mean absolute error vs the reference. Self-consistency: same label (or ratio spread ≤ {TARGETS['ratio_spread']}) across {r['config']['reps']} reps.", "",
              "| Metric | n | agreement | self-consistency | target | |", "|---|---|---|---|---|---|"]
        for id_, x in r["agreement"].items():
            ag = f"MAE {f(x['mae'])}" if x["type"] == "ratio" else f"agree {pct(x['kappa'])} (κ unstable)" if x["type"].startswith("categorical (rare") else f"κ {f(x['kappa'])}"
            L.append(f"| {id_} | {x['n']} | {ag} | {pct(x['consistency'])} | {x['target']} | {'ok' if x['pass'] else 'FAIL'} |")
    L += ["", "## Probes", "", "| Probe | Expectation | composite | gates | result |", "|---|---|---|---|---|"]
    for p in r["probes"]:
        gates = "–" if p.get("gates_passed") is None else "pass" if p["gates_passed"] else f"fail ({', '.join(p.get('gate_failures', []))})"
        L.append(f"| {p['name']} | {p['expect']} | {f(p.get('composite'))} | {gates} | {'n/a' if p.get('pass') is None else 'ok' if p['pass'] else 'FAIL'} |")
    co = r["cost"]
    if co["judge_calls"]:
        L += ["", "## Cost and latency", "", f"Judge calls: {co['judge_calls']}; mean input tokens {f(co['judge_mean_input_tokens'])} (cache-read share {pct(co['judge_cache_read_share'])}); mean output tokens {f(co['judge_mean_output_tokens'])}; mean latency {f(co['judge_mean_latency_s'])} s. Normalize calls: {co['normalize_calls']}, mean tokens {f(co['normalize_mean_tokens'])}."]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    main()
