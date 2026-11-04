from fastapi.testclient import TestClient

from job_ad.api.app import app
from job_ad.drafter.brief import HiringBrief, brief_from_job_ad
from job_ad.drafter.completeness import check
from tests.fixtures import GOOD_AD

client = TestClient(app)


def test_minimal_valid_brief_has_low_ceiling_and_ranked_suggestions():
    c = check(HiringBrief(title="Driver", company={"name": "Acme"}, responsibilities=["Deliver stock to 40 pharmacies daily"], must_have=["Code 10 licence"]))
    assert c.valid and not c.would_be_not_ready
    assert 50 < c.estimated_ceiling < 70  # four required fields only; publishable needs 75
    fields = [s.field for s in c.suggestions]
    assert "pay" in fields and "statements.popia" in fields  # purpose is not suggested: responsibilities already feed why_this_role
    assert all(c.suggestions[i].estimated_lift >= c.suggestions[i + 1].estimated_lift for i in range(len(c.suggestions) - 1))


def test_rich_brief_has_high_ceiling_and_few_suggestions():
    c = check(brief_from_job_ad(GOOD_AD))
    assert not c.would_be_not_ready and c.estimated_ceiling >= 95 and c.unattainable_metrics == []


def test_hosted_apply_and_non_designated_excuse_metrics():
    b = HiringBrief(title="Clerk", company={"name": "Acme"}, responsibilities=["Capture invoices in Sage"], must_have=["Sage"], hosted_apply=True, designated_employer=False)
    c = check(b)
    assert "process.contact_or_link" not in c.unattainable_metrics and "compliance.ee_statement" not in c.unattainable_metrics
    assert not c.would_be_not_ready


def test_designated_without_ee_blocks():
    b = HiringBrief(title="Clerk", company={"name": "Acme"}, responsibilities=["x"], must_have=["y"], designated_employer=True)
    assert check(b).would_be_not_ready


def test_endpoint():
    r = client.post("/v1/briefs/check", json={"brief": {"title": "Driver", "company": {"name": "Acme"}, "responsibilities": ["Deliver stock"], "must_have": ["Code 10 licence"]}})
    assert r.status_code == 200
    j = r.json()
    assert j["would_be_not_ready"] is False and j["suggestions"][0]["estimated_lift"] > 0 and "unlocks" in j["suggestions"][0]
    assert client.post("/v1/briefs/check", json={"brief": {"title": "Driver", "company": {"name": "Acme"}}}).status_code == 422
