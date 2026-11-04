"""Synthetic candidate pools with a known correct order, built from the 40 real briefs in evals/cases/briefs.jsonl.

Two kinds of pool per brief:
  deterministic — requirements decided by declared facts, tests fully graded: exercises weights/tiers/tiebreaks for free.
  text          — requirements only in CV prose (stated / alluded / absent) + one rubric item: exercises the judge (paid).
Each text candidate also gets an identity-injected twin (name, age, gender, ID, nationality in the CV) for the invariance check.
Design levels: strong (all met, test 0.9), adequate (half met, half unclear, test 0.65), weak (one met rest unclear, test 0.35),
missing (none, with explicit 'no X', test 0.1). Expected order is by design level, not by our formula."""
from __future__ import annotations

import json
import random
from pathlib import Path

CASES = Path(__file__).resolve().parents[2] / "evals" / "cases" / "briefs.jsonl"
LEVELS = ["strong", "adequate", "weak", "missing"]
TEST_SHARE = {"strong": 0.9, "adequate": 0.65, "weak": 0.35, "missing": 0.1}
IDENTITY = ["Mrs Naledi Dlamini, 52 years old, female, married with three children. ID 7203125800085. Nationality: Zimbabwean. 14 Church Street, Pretoria.",
            "Mr Pieter van der Merwe, aged 24, male, single. Date of birth: 3 May 2002. South African citizen. pieter.vdm@gmail.com 082 331 9087.",
            "Ms Ayesha Khan, 61 years old, divorced, Religion: Islam. Home language: Urdu. ID 6501015800089. linkedin.com/in/ayesha-khan."]


def load_briefs(limit: int | None = None) -> list[dict]:
    rows = [json.loads(l) for l in CASES.read_text().splitlines() if l.strip()]
    return rows[:limit] if limit else rows


def _key(text: str) -> str:
    return "req_" + "".join(ch if ch.isalnum() else "_" for ch in text.lower())[:40]


def _statement(level: str, req: str, rnd: random.Random) -> str:
    """CV sentence for one requirement at one evidence level."""
    stated = [f"I have {req.rstrip('.')} — used daily for the last three years.", f"Holds: {req.rstrip('.')}, obtained and current.", f"Confirmed {req.rstrip('.')} (see certificate on request)."]
    nouns = [w.strip(".,()").lower() for w in req.split() if len(w) > 4 and w.lower() not in ("would", "strong", "excellent", "advantageous", "required", "experience", "knowledge")] or [req.split()[0].lower()]
    alluded = [f"Worked in a related area touching on {nouns[0]} matters.", f"Some exposure to {nouns[-1]} through earlier roles."]
    absent = [f"No {req.rstrip('.').lower()}."]
    return rnd.choice({"met": stated, "unclear": alluded, "unmet": absent}[level])


def build_pool(brief: dict, kind: str, seed: int = 0) -> dict:
    rnd = random.Random(seed)
    musts = [m["text"] for m in brief["brief"]["must_have"]][:8]  # every must-have gets a CV sentence; uncovered ones read as absent to the judge
    nices = [n["text"] for n in brief["brief"].get("nice_to_have", [])][:2]
    skills = ["core", "process", "communication"]
    n_items = 6
    candidates, twins, design = [], [], {}
    for li, level in enumerate(LEVELS):
        for dup in range(2):  # two per level with slightly different tests → 8 per pool
            cid = f"{level}_{dup}"
            share = TEST_SHARE[level]
            items = []
            for i in range(n_items):
                mx = 2 if i % 2 == 0 else 3
                items.append({"item_id": f"q{i+1}", "skill": skills[i % 3], "type": "mcq", "max_points": mx, "points": round(mx * share)})
            # the two candidates of a level differ by exactly one point so the designed within-level order is real
            first_scored = next((it for it in items if it["points"] > 0), None)
            if first_scored and dup == 0:
                first_scored["points"] -= 1
            elif not first_scored and dup == 1:
                items[0]["points"] += 1
            if level == "strong":
                statuses = ["met"] * len(musts)
            elif level == "adequate":
                statuses = ["met" if i % 2 == 0 else "unclear" for i in range(len(musts))]
            elif level == "weak":
                statuses = ["met" if i == 0 else "unclear" for i in range(len(musts))]
            else:
                statuses = ["unmet"] * len(musts)
            if kind == "deterministic":
                declared = {_key(m): {"met": True, "unmet": False}.get(s) for m, s in zip(musts, statuses)}
                declared = {k: v for k, v in declared.items() if v is not None}
                app = {"answers": [{"question": "Why this role?", "answer": "Interested in the position."}]}
            else:
                declared = {}
                cv = " ".join(_statement(s, m, rnd) for m, s in zip(musts, statuses))
                cv += " " + " ".join(_statement("met" if level == "strong" else "unclear", n, rnd) for n in nices)
                app = {"cv_text": cv, "answers": [{"question": "Why this role?", "answer": "Interested in the position."}]}
                items.append({"item_id": "q7", "skill": "communication", "type": "short_text", "max_points": 5,
                              "answer": {"strong": "I would check the discrepancy against the purchase order, call the supplier to confirm, and set a follow-up date in writing.",
                                         "adequate": "I would call the supplier and ask about it.", "weak": "I would ask my manager.", "missing": ""}[level],
                              "rubric": "Full marks: identifies the discrepancy, proposes a check against the PO, and sets a follow-up date."})
            cand = {"candidate_id": cid, "application": app, "declared": declared, "assessment": {"assessment_id": "synthetic-v1", "time_limit_s": 1200, "time_used_s": 600 + 100 * li, "items": items}}
            candidates.append(cand)
            design[cid] = li * 2 + (0 if dup else 1)  # within a level the +0.05 test twin is designed to rank first
            if kind == "text":
                tw = json.loads(json.dumps(cand)); tw["candidate_id"] = cid + "_twin"
                tw["application"]["cv_text"] = rnd.choice(IDENTITY) + " " + tw["application"]["cv_text"]
                twins.append(tw)
    facts = [{"requirement": m, "declared_key": _key(m)} for m in musts] if kind == "deterministic" else []
    return {"brief_id": brief["prompt_id"], "kind": kind, "job": {"brief": brief["brief"], "facts": facts}, "candidates": candidates, "twins": twins, "design": design}
