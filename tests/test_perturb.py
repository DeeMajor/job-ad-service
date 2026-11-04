import json

import pytest

from bench.perturb import PERTURBATIONS, apply_all
from job_ad.metrics.scorecard import score_deterministic
from tests.fixtures import GOOD_AD, ZA


def norm(ad, id_):
    return score_deterministic(ad, ZA).metric(id_).normalized


def test_every_perturbation_applies_to_good_fixture():
    assert sorted(p.name for p, _ in apply_all(GOOD_AD)) == sorted(p.name for p in PERTURBATIONS)


def test_original_not_mutated():
    before = GOOD_AD.model_dump_json()
    apply_all(GOOD_AD)
    assert GOOD_AD.model_dump_json() == before


@pytest.mark.parametrize("p", [p for p in PERTURBATIONS if not p.needs_judge], ids=lambda p: p.name)
def test_deterministic_perturbation_lowers_targets(p):
    pa = p.apply(GOOD_AD)
    assert pa is not None
    for t in p.targets:
        a, b = norm(GOOD_AD, t), norm(pa, t)
        assert b < a, f"{p.name} → {t}: {a} → {b}"
