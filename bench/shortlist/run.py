"""Phase 0 benchmark for the shortlist ranker.

  .venv/bin/python -m bench.shortlist.run                 # deterministic pools: monotonicity, perturbation, invariance — free
  .venv/bin/python -m bench.shortlist.run --judge --briefs 20   # text pools through the real judge (PAID; quote first)

Writes bench/data/out/shortlist-<tag>/summary.json and prints the table."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from scipy.stats import kendalltau

from job_ad.shortlist.contract import RankRequest
from job_ad.shortlist.rank import rank_pool
from .synth import build_pool, load_briefs

OUT = Path(__file__).resolve().parents[1] / "data" / "out"


def tau_vs_design(res, design: dict[str, int]) -> float:
    ranks = {c.candidate_id: c.rank for c in res.shortlist}
    ids = [i for i in design if i in ranks]
    t, _ = kendalltau([design[i] for i in ids], [ranks[i] for i in ids])
    return float(t)


def run(judge_mode: bool, n_briefs: int, tag: str, model: str) -> dict:
    judge = None
    if judge_mode:
        from job_ad.shortlist.judge import make_claude_judge
        judge = make_claude_judge(model=model)
    kind = "text" if judge_mode else "deterministic"
    rows, t0 = [], time.time()
    for b in load_briefs(n_briefs):
        pool = build_pool(b, kind)
        req = RankRequest.model_validate({"job": pool["job"], "candidates": pool["candidates"], "options": {"judge": judge_mode}})
        res = rank_pool(req, judge=judge)
        row = {"brief": pool["brief_id"], "tau": round(tau_vs_design(res, pool["design"]), 3), "cost_usd": res.meta.cost_usd, "redaction_clean": res.meta.fairness_check.redaction_clean,
               "tiers": {c.candidate_id: c.tier for c in res.shortlist}, "scores": {c.candidate_id: c.score for c in res.shortlist}}
        # perturbation: flip the top candidate's first graded item to 0 → test component must drop by exactly its share
        top = res.shortlist[0]
        pert = json.loads(json.dumps(pool["candidates"]))
        pc = next(c for c in pert if c["candidate_id"] == top.candidate_id)
        it = next(i for i in pc["assessment"]["items"] if i.get("points") is not None and i["points"] > 0)
        lost, it["points"] = it["points"], 0
        req_p = RankRequest.model_validate({"job": pool["job"], "candidates": [pc], "options": {"judge": judge_mode}})
        res_p = rank_pool(req_p, judge=judge)
        before, after = top.components.skills_test, res_p.shortlist[0].components.skills_test
        row["perturb_exact"] = abs((before.score - after.score) - lost / before.max) < 1e-6 and after.score < before.score
        if judge_mode:
            # invariance: identity-injected twins must score the same as their originals
            req_t = RankRequest.model_validate({"job": pool["job"], "candidates": pool["twins"], "options": {"judge": True}})
            res_t = rank_pool(req_t, judge=judge)
            tw = {c.candidate_id.removesuffix("_twin"): c for c in res_t.shortlist}
            diffs = {c.candidate_id: round(tw[c.candidate_id].score - c.score, 1) for c in res.shortlist}
            row["twin_score_diffs"] = diffs
            row["invariance_max_abs_diff"] = max(abs(d) for d in diffs.values())
            row["cost_usd"] = round(row["cost_usd"] + res_p.meta.cost_usd + res_t.meta.cost_usd, 4)
            row["twin_redaction_clean"] = res_t.meta.fairness_check.redaction_clean
        else:
            # invariance on the deterministic path: identity text in the answer must change nothing
            noisy = json.loads(json.dumps(pool["candidates"]))
            for c in noisy:
                c["application"]["answers"][0]["answer"] = "Mr Sipho Zulu, 58 years old, male, ID 6801015800083. " + c["application"]["answers"][0]["answer"]
            res_n = rank_pool(RankRequest.model_validate({"job": pool["job"], "candidates": noisy, "options": {"judge": False}}), judge=None)
            row["invariance_max_abs_diff"] = max(abs(a.score - b.score) for a, b in zip(res.shortlist, res_n.shortlist))
            row["twin_redaction_clean"] = res_n.meta.fairness_check.redaction_clean
        rows.append(row)
        print(f"{row['brief']:<10} tau={row['tau']:+.2f} perturb={'ok' if row['perturb_exact'] else 'FAIL'} inv_diff={row['invariance_max_abs_diff']:.1f} clean={row['twin_redaction_clean']} cost=${row['cost_usd']:.3f}")
    summary = {"tag": tag, "kind": kind, "model": model if judge_mode else None, "n_pools": len(rows), "tau_min": min(r["tau"] for r in rows), "tau_mean": round(sum(r["tau"] for r in rows) / len(rows), 3),
               "perturb_pass": sum(r["perturb_exact"] for r in rows), "invariance_max_abs_diff": max(r["invariance_max_abs_diff"] for r in rows),
               "redaction_clean_all": all(r["redaction_clean"] and r["twin_redaction_clean"] for r in rows), "cost_usd": round(sum(r["cost_usd"] for r in rows), 3),
               "elapsed_s": round(time.time() - t0, 1), "rows": rows}
    d = OUT / f"shortlist-{tag}"; d.mkdir(parents=True, exist_ok=True)
    (d / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps({k: v for k, v in summary.items() if k != "rows"}, indent=2))
    return summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--judge", action="store_true", help="run text pools through the real judge (paid)")
    ap.add_argument("--briefs", type=int, default=40)
    ap.add_argument("--model", default="claude-sonnet-5")
    ap.add_argument("--tag", default=None)
    a = ap.parse_args()
    run(a.judge, a.briefs, a.tag or ("judge" if a.judge else "det"), a.model)
