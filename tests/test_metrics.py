import pytest

from job_ad.metrics.deterministic import run_deterministic
from job_ad.metrics.normalize import normalize
from job_ad.metrics.scorecard import score_deterministic
from job_ad.metrics.spec import Norm, load_spec
from job_ad.metrics.text import flesch_kincaid_grade, longest_sentence, sentences, syllables, words
from job_ad.metrics.types import Company, ScoringContext
from tests.fixtures import BAD_AD, EMPTY_AD, GOOD_AD, ZA


def get(rs, id):
    return next(r for r in rs if r.id == id)


class TestText:
    def test_syllables(self):
        assert syllables("cat") == 1
        assert syllables("logistics") == 3
        assert syllables("reconcile") == 3
        assert syllables("accommodation") == 5

    def test_sentences_and_bullets(self):
        assert len(sentences("One. Two! Three?\n• four")) == 4

    def test_fk_grade(self):
        assert flesch_kincaid_grade("The cat sat. The dog ran. We went home.") < 3
        assert flesch_kincaid_grade(BAD_AD.company.about) > 14

    def test_longest_sentence(self):
        assert longest_sentence("Short one. This sentence has exactly seven words in it.") == 8

    def test_words(self):
        assert words("R1,500 a month; 20 days' leave") == ["a", "month", "days'", "leave"]


class TestRender:
    def test_markdown_structure(self):
        from job_ad.metrics.text import render_markdown
        md = render_markdown(GOOD_AD)
        assert md.startswith("# Accounts Payable Clerk\n")
        assert "**Mzansi Logistics · Durban, KwaZulu-Natal · onsite**" in md
        assert "## What you'll do\n\n- Capture and match" in md and "## What we offer" in md
        assert "**Closing date:** 30 November 2026" in md and md.rstrip().endswith("link above.")
        assert "## Nice to have" in render_markdown(GOOD_AD) and "## Nice to have" not in render_markdown(GOOD_AD.model_copy(update={"nice_to_have": []}))


class TestNormalize:
    def test_band(self):
        n = Norm(kind="band", lo=300, hi=650, slack=250)
        assert normalize(400, n, "count") == 1
        assert normalize(300, n, "count") == 1
        assert normalize(775, n, "count") == pytest.approx(0.5)
        assert normalize(900, n, "count") == 0
        assert normalize(50, n, "count") == 0

    def test_pass_fail(self):
        assert normalize(1, None, "pass_fail") == 1
        assert normalize(0, None, "pass_fail") == 0


class TestGoodAd:
    rs = run_deterministic(GOOD_AD, ZA)

    def test_sections(self):
        assert get(self.rs, "structure.sections_present").raw == 1

    def test_title(self):
        assert get(self.rs, "structure.title_quality").pass_ is True

    def test_words_band(self):
        assert 250 < get(self.rs, "clarity.word_count").raw < 650

    def test_readable(self):
        assert get(self.rs, "clarity.reading_grade").raw < 11
        assert get(self.rs, "clarity.longest_sentence").raw <= 35

    def test_requirements(self):
        assert get(self.rs, "specific.must_have_count").raw == 3
        assert get(self.rs, "specific.nice_to_have_split").pass_ is True
        assert get(self.rs, "specific.years_inflation").raw == 0

    def test_pay(self):
        assert get(self.rs, "pay.range_present").pass_ is True
        assert get(self.rs, "pay.range_width").raw == pytest.approx(0.22)

    def test_lexicons(self):
        assert get(self.rs, "honesty.buzzword_density").raw < 0.5
        assert abs(get(self.rs, "inclusive.gender_coding").raw) < 1.5
        assert get(self.rs, "inclusive.exclusionary_terms").raw == 0

    def test_statements(self):
        assert get(self.rs, "inclusive.accessibility_statement").pass_ is True
        assert get(self.rs, "compliance.ee_statement").pass_ is True
        assert get(self.rs, "compliance.popia_notice").pass_ is True

    def test_candidate_address_and_contact(self):
        assert get(self.rs, "inclusive.candidate_address").raw >= 1
        assert get(self.rs, "process.contact_or_link").pass_ is True


class TestBadAd:
    rs = run_deterministic(BAD_AD, ZA)

    def test_sections(self):
        assert get(self.rs, "structure.sections_present").raw < 0.8

    def test_title(self):
        r = get(self.rs, "structure.title_quality")
        assert r.pass_ is False
        assert any("gimmick" in e for e in r.evidence)
        assert any("level code" in e for e in r.evidence)

    def test_requirements(self):
        assert get(self.rs, "specific.must_have_count").raw == 8
        assert get(self.rs, "specific.nice_to_have_split").pass_ is False
        assert get(self.rs, "specific.years_inflation").raw == 1

    def test_pay_and_buzz(self):
        assert get(self.rs, "pay.range_width").raw == 3
        assert get(self.rs, "honesty.buzzword_density").raw > 3

    def test_inclusivity(self):
        assert get(self.rs, "inclusive.gender_coding").raw > 1
        r = get(self.rs, "inclusive.exclusionary_terms")
        assert r.raw >= 4
        assert "able-bodied" in r.evidence and "native english speaker" in r.evidence
        assert any("young, energetic" in e for e in r.evidence)
        assert any("under 35" in e for e in r.evidence)
        assert get(self.rs, "inclusive.candidate_address").raw < 1

    def test_compliance(self):
        assert get(self.rs, "compliance.ee_statement").pass_ is False
        assert get(self.rs, "compliance.popia_notice").pass_ is False

    def test_ambiguous_words_do_not_gate(self):
        ad = GOOD_AD.model_copy(update={"company": Company(name="X", about="We are a young company with a mature product and a single source of truth.")})
        r = get(run_deterministic(ad, ZA), "inclusive.exclusionary_terms")
        assert r.raw == 0
        assert {"review: young", "review: mature", "review: single"} <= set(r.evidence)

    def test_level_codes(self):
        def t(title):
            return get(run_deterministic(GOOD_AD.model_copy(update={"title": title}), ZA), "structure.title_quality")
        assert t("Accountant (Grade 7)").pass_ is False
        assert t("Software Engineer P3").pass_ is False
        assert t("Non-Destructive Testing Technician – Level 2").pass_ is True

    def test_hosted_apply(self):
        r = get(run_deterministic(BAD_AD, ScoringContext(jurisdiction="ZA", designated_employer=True, hosted_apply=True)), "process.contact_or_link")
        assert r.status == "not_applicable"


class TestScorecard:
    def test_spec_loads(self):
        s = load_spec()
        assert len(s.metrics) == 37 and abs(sum(d.weight for d in s.dimensions.values()) - 1.0) < 1e-9

    def test_good(self):
        sc = score_deterministic(GOOD_AD, ZA)
        assert sc.gates_passed and sc.composite > 80 and sc.standard.level == "publishable" and all(r.severity != "must_fix" for r in sc.standard.reasons)
        assert all(m.status == "skipped" for m in sc.metrics if m.grader == "judge")
        assert sc.metric("seo.title_matches_taxonomy").status == "not_implemented"

    def test_bad_blocked(self):
        sc = score_deterministic(BAD_AD, ZA)
        assert not sc.gates_passed and sc.verdict == "not_ready" and sc.standard.level == "not_ready"
        assert sc.composite > 0  # never zeroed
        assert {r.metric for r in sc.standard.reasons if r.severity == "must_fix"} >= {"inclusive.exclusionary_terms", "compliance.ee_statement"}
        assert all(r.message for r in sc.standard.reasons)
        assert {"inclusive.exclusionary_terms", "compliance.ee_statement"} <= set(sc.gate_failures)
        assert "compliance.popia_notice" not in sc.gate_failures
        unknown = score_deterministic(BAD_AD, ScoringContext(jurisdiction="ZA"))
        assert "compliance.ee_statement" not in unknown.gate_failures

    def test_empty_blocked_by_minimum_content(self):
        sc = score_deterministic(EMPTY_AD, ScoringContext(jurisdiction="ZA"))
        assert "structure.minimum_content" in sc.gate_failures and sc.standard.level == "not_ready"
        assert "structure.minimum_content" not in score_deterministic(GOOD_AD, ZA).gate_failures

    def test_non_designated(self):
        sc = score_deterministic(GOOD_AD.model_copy(update={"ee_statement": None}), ScoringContext(jurisdiction="ZA", designated_employer=False))
        assert sc.metric("compliance.ee_statement").status == "not_applicable" and sc.gates_passed

    def test_channel_override(self):
        d = score_deterministic(GOOD_AD, ZA).metric("clarity.word_count")
        li = score_deterministic(GOOD_AD, ZA.model_copy(update={"channel": "linkedin"})).metric("clarity.word_count")
        assert d.normalized == 1 and li.normalized < 1
