from job_ad.drafter.brief import HiringBrief
from job_ad.drafter.enrich import Fact, _domain
from job_ad.drafter.prompts import get_prompt, render_drafter_input
from job_ad.metrics.types import Source


def test_domain_extraction():
    assert _domain("https://www.absa.co.za/careers") == "absa.co.za"
    assert _domain("ozow.com") == "ozow.com"
    assert _domain(None) is None


def test_prompt_versions():
    v, p = get_prompt("0.2.1")
    assert "SOURCE blocks" in p and "Never take pay, Employment Equity, POPIA or accessibility statements from a SOURCE block" in p
    assert get_prompt("0.2.0")[1].count("SOURCE") == 0
    assert "world-knowledge detail" in get_prompt("0.2.2")[1] and "world-knowledge detail" not in get_prompt("0.2.0")[1]
    assert "world-knowledge detail" in get_prompt("0.2.3")[1] and "SOURCE blocks" in get_prompt("0.2.3")[1]
    from job_ad.drafter.prompts import DRAFTER_PROMPT_VERSION
    assert DRAFTER_PROMPT_VERSION == "0.2.2"


def test_render_input_with_sources():
    t = render_drafter_input("Title: X", '<SOURCE id="web:1">\nSource URL: https://a.co.za\n[about] A does B.\n</SOURCE>')
    assert t.startswith("<BRIEF>") and '<SOURCE id="web:1">' in t and t.endswith("Write the advertisement.")


def test_brief_accepts_website():
    b = HiringBrief(title="Clerk", company={"name": "Absa", "website": "https://www.absa.co.za"}, responsibilities=["x"], must_have=["y"])
    assert b.company.website == "https://www.absa.co.za"


def test_banned_fact_filter_logic():
    import re
    banned = re.compile(r"\b(salary|salaries|pay range|per month|per annum|R\s?\d{2,3}[ ,]?\d{3}|employment equity|affirmative action|designated group|POPIA|personal information|accommodation)\b", re.I)
    ok = Fact(text="Absa operates in 12 African countries.", url="https://absa.africa", kind="about")
    bad = Fact(text="Salaries range from R20 000 per month.", url="https://x", kind="benefits")
    assert not banned.search(ok.text) and banned.search(bad.text)
