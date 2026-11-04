import json

from fastapi.testclient import TestClient

from job_ad.api import app as appmod
from job_ad.shortlist.contract import RankRequest
from job_ad.shortlist.judge import CandidateJudgeOut, ItemJudgement, JudgeInput, JudgeResult, ReqJudgement
from job_ad.shortlist.rank import rank_pool
from job_ad.shortlist.redact import redact, residual_scan

BRIEF = {"title": "Creditors Clerk", "company": {"name": "Acme"}, "responsibilities": ["Capture supplier invoices in Sage", "Reconcile supplier statements monthly"],
         "must_have": [{"text": "Working knowledge of Sage", "justification": "invoices are captured in Sage 300"}, "Two or more years in a creditors role"],
         "nice_to_have": ["Pivot tables in Excel"]}


def keyword_judge(inp: JudgeInput) -> JudgeResult:
    """Offline stand-in: 'met' when a keyword of the requirement appears in the text, 'unmet' when 'no <keyword>' appears, else unclear."""
    text = " ".join(a for _, a in inp.answers) + " " + inp.cv_text + " " + inp.cover_note
    low = text.lower()
    reqs = []
    stop = {"working", "knowledge", "more", "years", "role", "tables", "with", "from", "that", "this"}
    for r in inp.requirements:
        kws = [w.strip(".,").lower() for w in r.split() if len(w) >= 4 and w.lower() not in stop]
        hit = next((k for k in kws if k in low), None)
        if any(f"no {k}" in low for k in kws):
            reqs.append(ReqJudgement(requirement=r, status="unmet", evidence="", source="none", note="states no " + kws[0]))
        elif hit:
            i = low.index(hit); reqs.append(ReqJudgement(requirement=r, status="met", evidence=text[max(0, i - 10):i + len(hit) + 10].strip(), source="cv_text", note=""))
        else:
            reqs.append(ReqJudgement(requirement=r, status="unclear", evidence="", source="none", note="not mentioned"))
    items = [ItemJudgement(item_id=it.item_id, points=it.max_points if "supplier" in (it.answer or "").lower() else 0, evidence=(it.answer or "")[:20], reasoning="keyword") for it in inp.items]
    return JudgeResult(out=CandidateJudgeOut(requirements=reqs, items=items), usage={"input_tokens": 100, "output_tokens": 50}, model="fake")


def assessment(pts, free_answer=None):
    items = [{"item_id": "q1", "skill": "reconciliation", "type": "mcq", "max_points": 2, "points": pts[0]},
             {"item_id": "q2", "skill": "reconciliation", "type": "mcq", "max_points": 2, "points": pts[1]},
             {"item_id": "q3", "skill": "excel", "type": "numeric", "max_points": 3, "points": pts[2]}]
    if free_answer is not None:
        items.append({"item_id": "q4", "skill": "communication", "type": "short_text", "max_points": 5, "answer": free_answer, "rubric": "Mentions checking with the supplier."})
    return {"assessment_id": "ap-v1", "time_limit_s": 1200, "time_used_s": 900, "items": items}


def cand(cid, cv, pts, **kw):
    return {"candidate_id": cid, "application": {"cv_text": cv}, "assessment": assessment(pts, kw.pop("free", None)), **kw}


def test_redaction_removes_identifiers_and_is_clean():
    txt = ("Mr Thabo Nkosi, born 12 March 1990, ID 9003125800085, email thabo@x.co.za, cell 082 555 1234. Gender: Male. Married, 2 children.\n"
           "12 Long Street, Cape Town. South African citizen. 34 years old. Three years capturing invoices in Sage 300.")
    r = redact(txt)
    for s in ("Thabo", "9003125800085", "thabo@x", "082", "Male", "Married", "Long Street", "citizen", "34 years"):
        assert s not in r.text, s
    assert "Sage 300" in r.text and r.count >= 8 and residual_scan(r.text) == 0


def test_ranking_order_tiers_and_reasons():
    req = RankRequest.model_validate({"job": {"brief": BRIEF, "knockouts": [{"text": "Code 10 licence", "declared_key": "has_code_10"}]},
        "candidates": [
            cand("strong", "Three years capturing supplier invoices in Sage 300 in a creditors role. Pivot tables daily.", [2, 2, 3], declared={"has_code_10": True}),
            cand("mid", "Bookkeeping assistant; some exposure to Sage.", [2, 0, 1], declared={"has_code_10": True}),
            cand("knocked", "Three years in a creditors role using Sage.", [2, 2, 3], declared={"has_code_10": False}),
            cand("weak", "Retail cashier, no sage experience.", [0, 0, 0], declared={"has_code_10": True}),
            {"candidate_id": "noassess", "application": {"cv_text": "Sage expert"}},
        ]})
    res = rank_pool(req, judge=keyword_judge)
    order = [c.candidate_id for c in res.shortlist]
    assert order == ["strong", "mid", "weak", "knocked"], order
    assert [c.rank for c in res.shortlist] == [1, 2, 3, 4]
    assert res.excluded_from_ranking[0].candidate_id == "noassess" and "assessment" in res.excluded_from_ranking[0].reason
    top = res.shortlist[0]
    assert top.tier == "strong" and top.components.requirements.matched == 2 and top.components.skills_test.score == 1.0 and top.components.nice_to_have.matched == 1
    kinds = [r.kind for r in top.reasons]
    assert "requirement_met" in kinds and "test_strength" in kinds and "nice_to_have_met" in kinds
    kn = res.shortlist[-1]
    assert kn.tier == "does_not_meet_inherent_requirement" and kn.reasons[0].kind == "knockout_failed" and kn.reasons[0].source == "declared"
    weak = next(c for c in res.shortlist if c.candidate_id == "weak")
    assert weak.tier == "weak" and any(r.kind == "requirement_unmet" and "Sage" in r.requirement for r in weak.reasons) and any(r.kind == "test_gap" for r in weak.reasons)
    mid = next(c for c in res.shortlist if c.candidate_id == "mid")
    assert any("unclear" in h for h in mid.needs_human_check)
    assert res.meta.judged_candidates == 4 and res.meta.cost_usd > 0 and res.meta.fairness_check.redaction_clean
    # justified must-have counts double: Sage met (2×1.0) + creditors unclear (1×0.5) → 2.5/3
    assert abs(mid.components.requirements.score - 2.5 / 3) < 1e-9


def test_graded_item_flip_moves_test_component_exactly():
    base = RankRequest.model_validate({"job": {"brief": BRIEF}, "candidates": [cand("a", "Sage creditors role", [2, 2, 3])]})
    flipped = RankRequest.model_validate({"job": {"brief": BRIEF}, "candidates": [cand("a", "Sage creditors role", [2, 2, 0])]})
    b = rank_pool(base, judge=keyword_judge).shortlist[0]; f = rank_pool(flipped, judge=keyword_judge).shortlist[0]
    assert abs((b.components.skills_test.score - f.components.skills_test.score) - 3 / 7) < 1e-6
    assert abs((b.score - f.score) - round(100 * 0.40 * 3 / 7, 1)) <= 0.1
    assert f.components.skills_test.by_skill["excel"] == 0.0 and b.components.skills_test.by_skill["excel"] == 1.0


def test_identity_injection_is_invariant_after_redaction():
    cv = "Three years capturing supplier invoices in Sage 300 in a creditors role."
    noisy = "Mrs Naledi Dlamini, 52 years old, female, married, ID 7203125800085. " + cv + " Nationality: Zimbabwean."
    a = rank_pool(RankRequest.model_validate({"job": {"brief": BRIEF}, "candidates": [cand("x", cv, [2, 1, 3])]}), judge=keyword_judge).shortlist[0]
    b = rank_pool(RankRequest.model_validate({"job": {"brief": BRIEF}, "candidates": [cand("x", noisy, [2, 1, 3])]}), judge=keyword_judge).shortlist[0]
    assert a.score == b.score and a.components == b.components and b.redactions_applied >= 5 and any(r.kind == "redaction" for r in b.reasons)


def test_judged_items_and_judge_off_mode():
    r = RankRequest.model_validate({"job": {"brief": BRIEF}, "candidates": [cand("a", "Sage creditors role", [2, 2, 3], free="I would check with the supplier and the PO.")]})
    on = rank_pool(r, judge=keyword_judge).shortlist[0]
    assert on.components.skills_test.judged_items == 1 and on.components.skills_test.points == 12 and on.components.skills_test.max == 12
    assert any(k.kind == "test_item_judged" for k in on.reasons)
    r.options.judge = False
    off = rank_pool(r, judge=keyword_judge).shortlist[0]
    assert off.components.skills_test.ungraded_items == ["q4"] and off.components.skills_test.max == 7
    assert off.components.requirements.unclear == 2 and any("ungraded" in h for h in off.needs_human_check)


def test_fact_links_decide_requirements_without_judge():
    r = RankRequest.model_validate({"job": {"brief": BRIEF, "facts": [{"requirement": "Working knowledge of Sage", "declared_key": "sage"}]},
                                    "candidates": [cand("a", "", [2, 2, 3], declared={"sage": "yes"}), cand("b", "", [2, 2, 3], declared={"sage": False})],
                                    "options": {"judge": False}})
    res = rank_pool(r, judge=None)
    a, b = res.shortlist
    assert a.candidate_id == "a" and a.components.requirements.matched == 1 and b.components.requirements.unmet == 1 and res.meta.judged_candidates == 0 and res.meta.cost_usd == 0


def test_no_assessment_allowed_redistributes_weight():
    r = RankRequest.model_validate({"job": {"brief": BRIEF}, "candidates": [{"candidate_id": "a", "application": {"cv_text": "Sage creditors role pivot tables"}}], "options": {"require_assessment": False}})
    c = rank_pool(r, judge=keyword_judge).shortlist[0]
    assert c.components.skills_test is None and c.score == 100.0 and any(k.kind == "test_missing" for k in c.reasons) and "no assessment" in c.needs_human_check


def test_contract_validation():
    import pytest
    with pytest.raises(Exception):
        RankRequest.model_validate({"job": {"brief": BRIEF}, "candidates": [cand("a", "", [3, 2, 3])]})  # points > max
    with pytest.raises(Exception):
        RankRequest.model_validate({"job": {"brief": BRIEF}, "candidates": [cand("a", "", [2, 2, 3]), cand("a", "", [2, 2, 3])]})  # duplicate id


def test_api_rank_sync_and_async(monkeypatch):
    monkeypatch.setattr(appmod, "_shortlist_judge", lambda model: keyword_judge)
    client = TestClient(appmod.app)
    body = {"job": {"brief": BRIEF}, "candidates": [cand("a", "Sage creditors role", [2, 2, 3]), cand("b", "cashier", [0, 0, 0])]}
    r = client.post("/v1/shortlists/rank", json=body)
    assert r.status_code == 200, r.text
    d = r.json(); assert [c["candidate_id"] for c in d["shortlist"]] == ["a", "b"] and d["spec_version"] and d["meta"]["fairness_check"]["ran"]
    r2 = client.post("/v1/shortlist-jobs", json=body); assert r2.status_code == 202
    jid = r2.json()["job_id"]
    import time
    for _ in range(100):
        j = client.get(f"/v1/shortlist-jobs/{jid}").json()
        if j["status"] in ("done", "failed"):
            break
        time.sleep(0.05)
    assert j["status"] == "done" and j["result"]["shortlist"][0]["candidate_id"] == "a"
    assert client.get("/healthz").json()["versions"]["ranking_spec"]
