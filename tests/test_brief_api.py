from fastapi.testclient import TestClient

from job_ad.api.app import app
from job_ad.drafter.brief import HiringBrief, brief_from_job_ad, render_brief, scoring_context_for
from tests.fixtures import BAD_AD, GOOD_AD

client = TestClient(app)


class TestBrief:
    def test_from_job_ad(self):
        b = brief_from_job_ad(GOOD_AD)
        assert b.schema_version == "0.3" and b.title == "Accounts Payable Clerk"
        assert b.pay.min == 18000 and b.pay.max == 22000 and b.pay.period == "month" and "Placement" in b.pay.basis
        assert len(b.must_have) == 3 and b.must_have[0].text.startswith("Two or more years")
        assert "designated employer" in b.statements.ee
        assert str(b.process.closing_date) == "2026-11-30"

    def test_render(self):
        t = render_brief(brief_from_job_ad(GOOD_AD))
        assert t.startswith("Title: Accounts Payable Clerk")
        assert "Pay: ZAR 18000.0 – 22000.0 per month; basis:" in t
        assert "Must-have requirements:\n  - Two or more years" in t
        thin = render_brief(brief_from_job_ad(BAD_AD.model_copy(update={"pay": None, "process": None})))
        assert "\nPay:" not in thin and "Application process" not in thin

    def test_minimal_and_rich(self):
        m = HiringBrief(title="Driver", company={"name": "Acme"}, responsibilities=["Deliver stock to 40 pharmacies daily"], must_have=["Code 10 licence"])
        assert m.work_mode is None and m.nice_to_have == [] and m.jurisdiction == "ZA"
        import pydantic, pytest
        with pytest.raises(pydantic.ValidationError) as e:
            HiringBrief(title="Driver", company={"name": "Acme"})
        paths = {".".join(str(p) for p in err["loc"]) for err in e.value.errors()}
        assert {"responsibilities", "must_have"} <= paths
        r = HiringBrief(title="Delivery Driver", company={"name": "Acme"}, responsibilities=["Deliver stock to 40 pharmacies daily"], seniority="mid", employment_type="permanent", purpose="Keep 40 pharmacies stocked daily",
                        success_measures=["98% on-time deliveries"], must_have=[{"text": "Code 10 licence with PDP", "justification": "drives a 4-ton truck daily"}, "Clean driving record"],
                        pay={"min": 14000, "max": 16000, "period": "month"}, team={"reports_to": "Fleet Supervisor", "size": 12}, process={"closing_date": "2026-12-15"}, hours="Mon–Sat 06:00–15:00")
        assert r.must_have[0].justification == "drives a 4-ton truck daily" and r.must_have[1].justification is None
        t = render_brief(r)
        assert "Code 10 licence with PDP (needed because: drives a 4-ton truck daily)" in t and "Team size: 12" in t

    def test_rejects_bad_input(self):
        import pydantic, pytest
        with pytest.raises(pydantic.ValidationError) as e:
            HiringBrief(title="", company={}, pay={"min": 1, "period": "fortnight"}, process={"closing_date": "15/12/2026"})
        paths = {".".join(str(p) for p in err["loc"]) for err in e.value.errors()}
        assert {"title", "company.name", "pay.period", "process.closing_date"} <= paths

    def test_context(self):
        ctx = scoring_context_for(brief_from_job_ad(GOOD_AD, hosted_apply=True))
        assert len(ctx.sources) == 1 and ctx.sources[0].id == "brief" and ctx.hosted_apply is True


class TestApi:
    def test_healthz(self):
        r = client.get("/healthz")
        assert r.status_code == 200 and r.json()["ok"] is True and r.headers["x-request-id"]
        assert set(r.json()["versions"]) == {"spec", "judge_prompt", "drafter_prompt", "brief_schema", "ranking_spec", "shortlist_judge_prompt", "offer_rules", "offer_prompt"}

    def test_spec(self):
        j = client.get("/v1/spec").json()
        assert len(j["metrics"]) > 30 and "honesty.grounding" in j["gates"]

    def test_scores_deterministic(self):
        r = client.post("/v1/scores", json={"ad": GOOD_AD.model_dump(), "context": {"jurisdiction": "ZA", "designated_employer": True}, "judge": False})
        assert r.status_code == 200
        sc = r.json()["scorecard"]
        assert sc["gates_passed"] is True and sc["composite"] > 80 and r.json()["meta"]["judge"] is None
        bad = client.post("/v1/scores", json={"ad": BAD_AD.model_dump(), "judge": False}).json()["scorecard"]
        assert bad["verdict"] == "not_ready" and bad["standard"]["level"] == "not_ready" and bad["standard"]["reasons"][0]["severity"] == "must_fix"

    def test_drafts_validation(self):
        r = client.post("/v1/drafts", json={"brief": {"title": "", "company": {}}})
        assert r.status_code == 422
        locs = {".".join(str(p) for p in e["loc"]) for e in r.json()["detail"]}
        assert {"body.brief.title", "body.brief.company.name", "body.brief.responsibilities", "body.brief.must_have"} <= locs

    def test_drafts_refuses_not_ready_before_spending(self):
        # designated employer without an EE statement → would be not_ready → refused with structured 422, no model call
        r = client.post("/v1/drafts", json={"brief": {"title": "Clerk", "company": {"name": "Acme"}, "responsibilities": ["Capture invoices"], "must_have": ["Sage"], "designated_employer": True}})
        assert r.status_code == 422
        d = r.json()["detail"]
        assert d["error"] == "brief_not_ready" and "designated employer" in d["not_ready_reasons"][0] and d["suggestions"]

    def test_enrichment_disabled_by_default(self):
        r = client.post("/v1/drafts", json={"brief": {"title": "Clerk", "company": {"name": "Acme"}, "responsibilities": ["Capture invoices"], "must_have": ["Sage"]}, "options": {"enrich": True}})
        assert r.status_code == 400 and r.json()["detail"]["error"] == "enrichment_disabled"
        assert client.get("/healthz").json()["features"]["enrichment"] is False

    def test_openapi(self):
        j = client.get("/openapi.json").json()
        assert "/v1/drafts" in j["paths"] and "HiringBrief" in j["components"]["schemas"]
