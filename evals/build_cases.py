"""Build Phase 1 eval cases from Phase 0's normalised real ads → evals/cases/briefs.jsonl.
Each case = a HiringBrief derived from a real ad + that ad's own scorecard composite (the number to beat)."""
from __future__ import annotations

import json
import re
from pathlib import Path

from job_ad.drafter.brief import brief_from_job_ad
from job_ad.metrics.types import JobAd

SOURCES = [("v1", "r3"), ("v1d", "r1")]
HOSTED = re.compile(r"^(workday|greenhouse|lever|workable):")


def main():
    role_of = {}
    p = Path("bench/data/raw/v1d/ads.jsonl")
    if p.exists():
        role_of = {j["id"]: j.get("role_family", "other") for j in (json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip())}
    rows = []
    i = 0
    for version, run in SOURCES:
        norm = Path("bench/data/out") / version / "normalized.jsonl"
        scores = Path("bench/data/out") / version / run / "scores.jsonl"
        if not (norm.exists() and scores.exists()):
            continue
        sc = {j["id"]: j for j in (json.loads(l) for l in scores.read_text(encoding="utf-8").splitlines() if l.strip())}
        for l in norm.read_text(encoding="utf-8").splitlines():
            if not l.strip():
                continue
            j = json.loads(l); real = sc.get(j["id"])
            if not real:
                continue
            ad = JobAd.model_validate(j["ad"])
            brief = brief_from_job_ad(ad, jurisdiction="ZA", hosted_apply=bool(HOSTED.match(j["id"])))
            split = "test" if i % 5 == 0 else "validation" if i % 5 == 2 else "train"
            thin = "thin" if len(brief.responsibilities) <= 3 or len(brief.must_have) <= 1 else "rich"
            role = "bank_sales" if version == "v1" else role_of.get(j["id"], "other")
            rows.append({"prompt_id": f"case_{i:03d}", "source_ad_id": j["id"], "split": split, "tags": [role, thin, version], "brief": json.loads(brief.model_dump_json()),
                         "real_ad": {"composite": real["scorecard"]["composite"], "gates_passed": real["scorecard"]["gates_passed"], "verdict": real["scorecard"]["verdict"]}})
            i += 1
    Path("evals/cases").mkdir(parents=True, exist_ok=True)
    Path("evals/cases/briefs.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    count = lambda k: {v: sum(1 for r in rows if k(r) == v) for v in sorted({k(r) for r in rows})}
    print(json.dumps({"cases": len(rows), "splits": count(lambda r: r["split"]), "roles": count(lambda r: r["tags"][0]), "richness": count(lambda r: r["tags"][1]),
                      "real_composite_mean": round(sum(r["real_ad"]["composite"] for r in rows) / len(rows), 1) if rows else None}, indent=1))


if __name__ == "__main__":
    main()
