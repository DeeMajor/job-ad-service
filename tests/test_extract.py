from fastapi.testclient import TestClient

from job_ad.api.app import app
from job_ad.drafter.brief import HiringBrief
from job_ad.drafter.extract import BriefOut, ReqOut, to_brief_dict

client = TestClient(app)


def _out(**kw) -> BriefOut:
    base = dict(title="Accounts Payable Clerk", company_name="", company_about="", company_website="", seniority="unspecified", employment_type="unspecified", purpose="", success_measures=[],
                responsibilities=["Capture invoices in Sage"], tools=[], must_have=[ReqOut(text="Sage experience", justification="")], nice_to_have=[], location="Durban", work_mode="unspecified",
                work_mode_detail="", hours="", start_date="", positions=0, pay_min=18000, pay_max=22000, pay_currency="", pay_period="month", pay_basis="", benefits=[], reports_to="", team_size=0,
                team_notes="", process_steps="", closing_date="", contact="", reference="", statement_ee="", statement_popia="", statement_accessibility="", questions=["Who does this person report to?"])
    base.update(kw)
    return BriefOut(**base)


def test_conversion_produces_valid_brief_with_sentinels_removed():
    d = to_brief_dict(_out(), company_name="Mzansi Logistics", jurisdiction="ZA", hosted_apply=False, designated_employer=None)
    b = HiringBrief.model_validate(d)
    assert b.company.name == "Mzansi Logistics" and b.seniority is None and b.pay.currency == "ZAR" and b.pay.min == 18000 and b.team is None and b.process is None


def test_conversion_reports_missing_required():
    d = to_brief_dict(_out(responsibilities=[], must_have=[]), company_name="Acme", jurisdiction="ZA", hosted_apply=False, designated_employer=None)
    assert d["responsibilities"] == [] and d["must_have"] == []
    import pydantic, pytest
    with pytest.raises(pydantic.ValidationError):
        HiringBrief.model_validate(d)


def test_pay_without_period_is_dropped_not_invented():
    d = to_brief_dict(_out(pay_period="unspecified"), company_name="Acme", jurisdiction="ZA", hosted_apply=False, designated_employer=None)
    assert d["pay"] is None


def test_extract_endpoint_validates_input():
    r = client.post("/v1/briefs/extract", json={"description": "too short"})
    assert r.status_code == 422
    assert "/v1/briefs/extract" in client.get("/openapi.json").json()["paths"]
