import json

from fastapi.testclient import TestClient

from job_ad.api.app import app
from job_ad.publish.platforms import PLATFORMS
from job_ad.publish.render import PublishExtras, parse_location, render_all, render_html, render_teaser
from tests.fixtures import GOOD_AD, BAD_AD

client = TestClient(app)
EXTRAS = PublishExtras(apply_url="https://jobs.example.co.za/ap-clerk", reference="FIN-0042", category="Finance / Accounting", employment_type="permanent", company_url="https://mzansilogistics.example")


def test_location_parsing_sa():
    l = parse_location("Durban, KwaZulu-Natal"); assert (l.city, l.province, l.country) == ("Durban", "KwaZulu-Natal", "ZA")
    l = parse_location("Sandton"); assert (l.city, l.province) == ("Sandton", "Gauteng")
    l = parse_location("Western Cape"); assert l.city is None and l.province == "Western Cape"
    l = parse_location("Cape Town, South Africa", work_mode="hybrid"); assert l.province == "Western Cape" and l.hybrid and not l.remote
    l = parse_location(None, work_mode="remote"); assert l.remote and l.city is None


def test_normalised_fields_and_json_ld():
    r = render_all(GOOD_AD, EXTRAS)
    f = r.fields
    assert f.title == "Accounts Payable Clerk" and f.employment_type_schema == "FULL_TIME" and f.salary.unit == "MONTH" and f.salary.min == 18000
    assert str(f.closing_date) == "2026-11-30" and f.location.province == "KwaZulu-Natal" and f.reference == "FIN-0042"
    j = r.renderings.json_ld
    assert j["@type"] == "JobPosting" and j["validThrough"] == "2026-11-30" and j["employmentType"] == "FULL_TIME"
    assert j["jobLocation"]["address"]["addressRegion"] == "KwaZulu-Natal" and j["baseSalary"]["value"]["minValue"] == 18000 and j["directApply"] is True
    assert j["hiringOrganization"]["sameAs"] == "https://mzansilogistics.example"


def test_html_is_conservative_and_escaped():
    h = render_html(BAD_AD.model_copy(update={"summary": "Use <script>alert(1)</script> & stuff"}))
    assert "<script>" not in h and "&lt;script&gt;" in h and "&amp;" in h
    assert set(t for t in __import__("re").findall(r"<(\w+)", h)) <= {"h2", "h3", "p", "strong", "ul", "li", "br"}


def test_teaser_fits_280():
    t = render_teaser(GOOD_AD, EXTRAS.apply_url)
    assert len(t) <= 280 and t.startswith("We're hiring: Accounts Payable Clerk at Mzansi Logistics in Durban") and "R18,000–R22,000/month" in t and t.endswith(EXTRAS.apply_url)


def test_channel_payloads_and_validation():
    r = render_all(GOOD_AD, EXTRAS)
    assert set(r.channels) == set(PLATFORMS)
    assert r.channels["linkedin"].ready and r.channels["linkedin"].payload["description_format"] == "text" and r.channels["linkedin"].payload["employment_type"] == "Full-time"
    assert r.channels["indeed"].payload["description_format"] == "html" and r.channels["indeed"].payload["employment_type"] == "fulltime"
    # indeed recommends 700+ words: our 450-word ad gets a warning, not an error
    assert r.channels["indeed"].ready and any(i.severity == "warning" and "performs best" in i.message for i in r.channels["indeed"].issues)
    assert r.channels["pnet"].ready and r.channels["pnet"].payload["category"] == "Finance / Accounting"
    assert r.channels["careers_site"].payload["json_ld"]["@type"] == "JobPosting"
    assert r.channels["social_teaser"].payload["teaser"].startswith("We're hiring")


def test_missing_extras_make_channels_not_ready():
    r = render_all(GOOD_AD, PublishExtras(), ["pnet", "linkedin", "generic_text"])
    assert not r.channels["pnet"].ready and {i.field for i in r.channels["pnet"].issues} >= {"category", "apply_url"}
    assert not r.channels["linkedin"].ready and r.channels["generic_text"].ready


def test_province_required_for_sa_boards():
    ad = GOOD_AD.model_copy(update={"location": "Somewhere Obscure"})
    r = render_all(ad, EXTRAS, ["careers24"])
    assert not r.channels["careers24"].ready and any(i.field == "location" for i in r.channels["careers24"].issues)


def test_endpoints():
    ps = client.get("/v1/platforms").json()
    assert {p["id"] for p in ps} == set(PLATFORMS) and all("limits" in p and "requires" in p for p in ps)
    r = client.post("/v1/ads/render", json={"ad": GOOD_AD.model_dump(), "extras": EXTRAS.model_dump(mode="json"), "platforms": ["linkedin", "careers_site"]})
    assert r.status_code == 200 and set(r.json()["channels"]) == {"linkedin", "careers_site"} and r.json()["renderings"]["json_ld"]["@type"] == "JobPosting"
    bad = client.post("/v1/ads/render", json={"ad": GOOD_AD.model_dump(), "platforms": ["myspace"]})
    assert bad.status_code == 422 and bad.json()["detail"]["error"] == "unknown_platform"
