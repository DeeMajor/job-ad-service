from fastapi.testclient import TestClient

from job_ad.api import app as appmod
from job_ad.offer.draft import draft_template
from job_ad.offer.rules import check, hourly_equivalent
from job_ad.offer.terms import OfferRequest

BRIEF = {"title": "Creditors Clerk", "company": {"name": "Acme (Pty) Ltd"}, "responsibilities": ["Capture supplier invoices in Sage"], "must_have": ["Sage"],
         "location": "Cape Town", "employment_type": "permanent", "pay": {"min": 18000, "max": 22000, "period": "month"}}
TERMS = {"contract_type": "permanent", "start_date": "2026-12-01", "probation_months": 3, "place_of_work": "14 Loop Street, Cape Town",
         "hours": {"per_week": 40, "per_day": 8, "days_per_week": 5, "schedule": "Mon–Fri 08:00–17:00", "meal_interval_min": 60},
         "pay": {"amount": 18500, "period": "month", "basis": "basic salary", "pay_day": "25th", "method": "EFT", "overtime_rate": 1.5},
         "deductions": ["PAYE", "UIF 1%"], "leave": {"annual_days": 15, "sick_cycle_days": 30, "family_responsibility_days": 3, "maternity_months": 4, "parental_days": 10},
         "notice": {"statutory_ladder": True}, "employer": {"address": "1 Main Road, Cape Town", "registration_number": "2010/123456/07"}, "employee_is_15_or_older": True,
         "clauses": {"confidentiality": True, "restraint_of_trade": {"months": 6, "area": "Western Cape"}}}


def req(**over):
    t = {**TERMS, **over}
    return OfferRequest.model_validate({"brief": BRIEF, "terms": t})


def test_compliant_terms_pass_and_arithmetic():
    comp, cons = check(req())
    assert comp.level == "compliant", [f.model_dump() for f in comp.findings if f.severity != "could_improve"]
    assert abs(hourly_equivalent(req().terms) - 18500 * 12 / 52 / 40) < 1e-9
    assert comp.checked_against.earnings_threshold_applies and cons.pay_in_ad_range and cons.employment_type_matches and cons.location_matches


def test_floors_and_particulars_detected():
    comp, _ = check(req(pay={**TERMS["pay"], "amount": 20, "period": "hour"}))
    assert comp.level == "not_compliant" and any(f.rule == "pay.nmw_hourly" and "28.79" in f.evidence for f in comp.findings)
    comp, _ = check(req(hours={**TERMS["hours"], "per_week": 48, "per_day": 9.6}))
    assert any(f.rule == "hours.ordinary_hours_week" and f.severity == "must_fix" for f in comp.findings)
    comp, _ = check(req(leave={**TERMS["leave"], "annual_days": 20, "annual_basis": "consecutive_days"}))
    assert any(f.rule == "leave.annual_leave" for f in comp.findings)
    comp, _ = check(req(notice={"weeks": 2}))
    assert any(f.rule == "termination.notice_gt_12_months" and "s37" in f.evidence for f in comp.findings)
    comp, _ = check(req(employer={}))
    assert any(f.rule == "particulars.employer_name_address" for f in comp.findings)


def test_threshold_switches_hours_rules_off():
    comp, _ = check(req(pay={**TERMS["pay"], "amount": 40000}, hours={**TERMS["hours"], "per_week": 50, "per_day": 10}))
    assert not comp.checked_against.earnings_threshold_applies and not any(f.rule.startswith("hours.") for f in comp.findings)
    assert any(f.rule == "thresholds.earnings_threshold" and f.severity == "could_improve" for f in comp.findings)


def test_fixed_term_needs_justification_below_threshold():
    comp, cons = check(req(contract_type="fixed_term", fixed_term={"end_date": "2027-06-30"}, notice={}))
    assert any(f.rule == "fixed_term.fixed_term_justification" and "s198B" in f.evidence for f in comp.findings) and cons.employment_type_matches is False
    comp, _ = check(req(contract_type="fixed_term", fixed_term={"end_date": "2027-06-30", "justification": "maternity cover"}, notice={}))
    assert not any(f.rule == "fixed_term.fixed_term_justification" for f in comp.findings)


def test_consistency_with_ad():
    comp, cons = check(req(pay={**TERMS["pay"], "amount": 15000}, place_of_work="Durban office"))
    # 15000/month is above NMW but below the ad's range
    assert cons.pay_in_ad_range is False and cons.location_matches is False and comp.level == "review"
    assert {f.rule for f in comp.findings} >= {"consistency.pay_in_ad_range", "consistency.location_matches"}


def test_template_contract_has_every_particular_and_placeholders():
    d = draft_template(req())
    refs = " ".join(c.particular or "" for c in d.contract.clauses)
    for p in ("(a)", "(c)", "(d)", "(e)", "(f)", "(g)", "(h)", "(l)", "(m)", "(n)", "(o)", "(q)"):
        assert p in refs, p
    assert "{{employee.full_name}}" in d.contract.markdown and "{{employee.id_number}}" in d.contract.markdown and "employee.full_name" in d.contract.placeholders
    assert all(e.explanation for e in d.plain_language) and len(d.plain_language) >= 12
    assert "Not legal advice" in d.disclaimer and d.meta.mode == "template" and d.meta.cost_usd == 0
    assert "Restraint of trade" in d.contract.markdown and "Dear {{employee.full_name}}" in d.offer_letter.markdown
    # no identity fields anywhere in the request contract
    assert not any(k in OfferRequest.model_json_schema()["$defs"]["Terms"]["properties"] for k in ("employee_name", "id_number", "date_of_birth", "gender", "race"))


def test_api_check_and_template(monkeypatch):
    client = TestClient(appmod.app)
    body = {"brief": BRIEF, "terms": TERMS}
    r = client.post("/v1/offers/check", json=body); assert r.status_code == 200 and r.json()["compliance"]["level"] == "compliant"
    r = client.post("/v1/offers/template", json=body); assert r.status_code == 200 and r.json()["contract"]["markdown"].startswith("# Contract of employment")
    r = client.post("/v1/offers/template?format=markdown", json=body); assert r.headers["content-type"].startswith("text/markdown") and r.headers["x-compliance-level"] == "compliant"
    assert client.get("/healthz").json()["versions"]["offer_rules"] == "0.1.0"
    bad = client.post("/v1/offers/check", json={"brief": BRIEF, "terms": {**TERMS, "contract_type": "fixed_term"}}); assert bad.status_code == 422


def test_api_draft_with_fake_model(monkeypatch):
    from job_ad.offer import draft as draftmod
    def fake_draft(req, client=None, model="claude-opus-5", effort="medium", model_explanations=False):
        d = draftmod.draft_template(req); d.meta.mode = "model"; d.meta.model = model; d.meta.cost_usd = 0.05; d.meta.usage = {"input_tokens": 10, "output_tokens": 5}
        return d
    monkeypatch.setattr(appmod, "draft_with_model", fake_draft)
    client = TestClient(appmod.app)
    r = client.post("/v1/offers/draft", json={"brief": BRIEF, "terms": TERMS}); assert r.status_code == 200 and r.json()["meta"]["model"] == "claude-opus-5" and r.json()["meta"]["mode"] == "model"
    r = client.post("/v1/offers/draft?format=markdown", json={"brief": BRIEF, "terms": TERMS, "options": {"model": "claude-sonnet-5"}}); assert r.headers["content-type"].startswith("text/markdown") and "# Offer of employment" in r.text and "# Contract of employment" in r.text
    r = client.post("/v1/offer-jobs", json={"brief": BRIEF, "terms": TERMS}); assert r.status_code == 202
    import time
    for _ in range(100):
        j = client.get(r.json()["status_url"]).json()
        if j["status"] in ("done", "failed"):
            break
        time.sleep(0.05)
    assert j["status"] == "done" and j["result"]["compliance"]["level"] == "compliant"
    assert client.get("/healthz").json()["versions"]["offer_prompt"] == "0.1.0"
