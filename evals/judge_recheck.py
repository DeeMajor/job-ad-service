"""EXP-102: re-score existing drafts with the (new) Sonnet judge and compare with the Opus labels already stored in crosscheck.jsonl.
Costs Sonnet calls only.    .venv/bin/python -m evals.judge_recheck --variant baseline --out crosscheck-j051.md
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import anthropic

from job_ad.drafter.brief import HiringBrief, scoring_context_for
from job_ad.metrics.judge.prompt import JUDGE_PROMPT_VERSION
from job_ad.metrics.judge.run import run_judge
from job_ad.metrics.types import JobAd
from evals.judge_crosscheck import ALL_JUDGED, METRICS, RATIO


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--variant", default="baseline"); ap.add_argument("--out", default="crosscheck-recheck.md"); ap.add_argument("--concurrency", type=int, default=4)
    a = ap.parse_args(argv)
    out = Path("evals/runs") / a.variant
    refs = {r["prompt_id"]: r for r in (json.loads(l) for l in (out / "crosscheck.jsonl").read_text(encoding="utf-8").splitlines() if l.strip())}
    cases = {c["prompt_id"]: c for c in (json.loads(l) for l in Path("evals/cases/briefs.jsonl").read_text(encoding="utf-8").splitlines() if l.strip())}
    client = anthropic.Anthropic()
    results = {}

    def one(pid):
        t = json.load(open(out / "traces" / f"{pid}_rep0.json", encoding="utf-8"))
        try:
            j = run_judge(JobAd.model_validate(t["ad"]), scoring_context_for(HiringBrief.model_validate(cases[pid]["brief"]), t["trace"][1]["content"]), client=client)
            results[pid] = {m.id: (m.raw, m.reasoning) for m in j.results if m.status == "ok"}
        except Exception as e:
            print(f"[recheck] {pid}: {str(e)[:160]}", file=sys.stderr)

    with ThreadPoolExecutor(max_workers=a.concurrency) as ex:
        list(ex.map(one, list(refs)))
    L = [f"# Judge {JUDGE_PROMPT_VERSION} re-check vs stored claude-opus-5 labels — {a.variant}, {len(results)} drafts", "", "| Metric | n | agreement | note |", "|---|---|---|---|"]
    for mid in ALL_JUDGED:
        pairs = [(results[p][mid][0], refs[p]["metrics"][mid]["reference"]) for p in results if mid in results[p] and mid in refs[p]["metrics"]]
        if not pairs:
            continue
        flag = " **(deferred)**" if mid in METRICS else ""
        if mid in RATIO:
            mae = sum(abs(j - r) for j, r in pairs) / len(pairs); L.append(f"| {mid} | {len(pairs)} | MAE {mae:.2f} | {'ok' if mae <= 0.2 else 'FAIL'}{flag} |")
        else:
            agree = sum(1 for j, r in pairs if (j >= 1) == (r >= 1)) / len(pairs)
            pos = max(sum(1 for j, _ in pairs if j >= 1), sum(1 for _, r in pairs if r >= 1))
            from sklearn.metrics import cohen_kappa_score
            k = cohen_kappa_score([int(j >= 1) for j, _ in pairs], [int(r >= 1) for _, r in pairs]) if 0 < pos < len(pairs) else 1.0
            ok = agree >= 0.9 if pos <= 2 else k >= 0.7
            L.append(f"| {mid} | {len(pairs)} | agree {round(agree*100)}% | {'rare positives' if pos <= 2 else f'κ {k:.2f}'} → {'ok' if ok else 'FAIL'}{flag} |")
    L += ["", "## Remaining disagreements on why_this_role", ""]
    for p in sorted(results):
        x = results[p].get("evp.why_this_role"); r = refs[p]["metrics"].get("evp.why_this_role")
        if x and r and abs(x[0] - r["reference"]) > 0.05:
            L += [f"- **{p}** judge={x[0]:.0f} ref={r['reference']:.0f}", f"  - judge: {x[1]}", f"  - ref: {r['reference_reasoning']}"]
    md = "\n".join(L) + "\n"; (out / a.out).write_text(md, encoding="utf-8"); print(md)


if __name__ == "__main__":
    main()
