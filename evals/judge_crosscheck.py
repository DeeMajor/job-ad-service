"""H1.0: cross-check the three Phase-0-deferred judge metrics against a claude-opus-5 reference on existing drafts.

  .venv/bin/python -m evals.judge_crosscheck --variant baseline --limit 20

Reads evals/runs/<variant>/traces/*.json (the Sonnet judge's results are in the trace); re-judges each draft once with the
reference model; reports agreement per metric (κ / % agreement for pass-fail, MAE for ratios). Writes evals/runs/<variant>/crosscheck.{jsonl,md}.
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import anthropic

from job_ad.drafter.brief import HiringBrief, scoring_context_for
from job_ad.metrics.judge.run import run_judge
from job_ad.metrics.types import JobAd

METRICS = ["evp.team_context", "evp.why_this_role", "specific.requirement_traceability"]
ALL_JUDGED = ["structure.title_matches_content", "specific.responsibility_concreteness", "specific.requirement_traceability", "pay.context_present", "honesty.grounding",
              "inclusive.proxy_requirements", "compliance.protected_grounds", "compliance.no_prohibited_requests", "evp.why_this_role", "evp.benefits_specific", "evp.team_context", "evp.work_mode_clarity", "process.steps_and_timeline"]
RATIO = {"specific.responsibility_concreteness", "specific.requirement_traceability", "honesty.grounding"}


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--variant", default="baseline"); ap.add_argument("--limit", type=int, default=20); ap.add_argument("--reference-model", default="claude-opus-5"); ap.add_argument("--concurrency", type=int, default=3)
    a = ap.parse_args(argv)
    out = Path("evals/runs") / a.variant
    cases = {c["prompt_id"]: c for c in (json.loads(l) for l in Path("evals/cases/briefs.jsonl").read_text(encoding="utf-8").splitlines() if l.strip())}
    traces = sorted(glob.glob(str(out / "traces" / "*_rep0.json")))[: a.limit]
    client = anthropic.Anthropic()
    rows_p = out / "crosscheck.jsonl"
    done = {json.loads(l)["prompt_id"] for l in rows_p.read_text(encoding="utf-8").splitlines() if l.strip()} if rows_p.exists() else set()

    def one(p):
        pid = Path(p).name.replace("_rep0.json", "")
        if pid in done:
            return
        t = json.load(open(p, encoding="utf-8")); ad = JobAd.model_validate(t["ad"])
        judged = {m["id"]: m for m in json.loads(t["trace"][-1]["content"])["metrics"]}
        brief = HiringBrief.model_validate(cases[pid]["brief"])
        try:
            ref = run_judge(ad, scoring_context_for(brief, t["trace"][1]["content"]), client=client, model=a.reference_model, effort="high")
        except Exception as e:
            print(f"[crosscheck] {pid}: {str(e)[:160]}", file=sys.stderr); return
        row = {"prompt_id": pid, "metrics": {}}
        for m in ref.results:
            if m.status != "ok" or m.id not in judged:
                continue
            row["metrics"][m.id] = {"judge": judged[m.id]["raw"], "reference": m.raw, "judge_reasoning": judged[m.id].get("reasoning"), "reference_reasoning": m.reasoning}
        with rows_p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    with ThreadPoolExecutor(max_workers=a.concurrency) as ex:
        list(ex.map(one, traces))
    rows = [json.loads(l) for l in rows_p.read_text(encoding="utf-8").splitlines() if l.strip()]
    L = [f"# Judge cross-check vs {a.reference_model} — {a.variant}, {len(rows)} drafts", "", "| Metric | n | agreement | note |", "|---|---|---|---|"]
    for mid in ALL_JUDGED:
        pairs = [(r["metrics"][mid]["judge"], r["metrics"][mid]["reference"]) for r in rows if mid in r["metrics"]]
        if not pairs:
            continue
        flag = " **(deferred from Phase 0)**" if mid in METRICS else ""
        if mid in RATIO:
            mae = sum(abs(j - r) for j, r in pairs) / len(pairs)
            L.append(f"| {mid} | {len(pairs)} | MAE {mae:.2f} | target ≤ 0.2 → {'ok' if mae <= 0.2 else 'FAIL'}{flag} |")
        else:
            agree = sum(1 for j, r in pairs if (j >= 1) == (r >= 1)) / len(pairs)
            pos = max(sum(1 for j, _ in pairs if j >= 1), sum(1 for _, r in pairs if r >= 1))
            try:
                from sklearn.metrics import cohen_kappa_score
                k = cohen_kappa_score([int(j >= 1) for j, _ in pairs], [int(r >= 1) for _, r in pairs]) if pos not in (0, len(pairs)) else 1.0
            except Exception:
                k = float("nan")
            note = "rare positives: % agreement" if pos <= 2 else f"κ {k:.2f}"
            ok = agree >= 0.9 if pos <= 2 else k >= 0.7
            L.append(f"| {mid} | {len(pairs)} | agree {round(agree * 100)}% | {note} → {'ok' if ok else 'FAIL'}{flag} |")
    L += ["", "## Disagreements on the deferred metrics", ""]
    for r in rows:
        for mid in METRICS:
            x = r["metrics"].get(mid)
            if x and abs(x["judge"] - x["reference"]) > 0.05:
                L += [f"- **{r['prompt_id']} · {mid}** judge={x['judge']:.2f} ref={x['reference']:.2f}", f"  - judge: {x['judge_reasoning']}", f"  - ref: {x['reference_reasoning']}"]
    md = "\n".join(L) + "\n"
    (out / "crosscheck.md").write_text(md, encoding="utf-8"); print(md)


if __name__ == "__main__":
    main()
