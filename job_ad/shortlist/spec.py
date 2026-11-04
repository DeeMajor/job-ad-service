"""Load the ranking spec (docs/shortlist-ranker/ranking-spec.yaml)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "docs" / "shortlist-ranker" / "ranking-spec.yaml"


class Weights(BaseModel):
    requirements: float = 0.45
    skills_test: float = 0.40
    nice_to_have: float = 0.15


class StatusValues(BaseModel):
    met: float = 1.0
    unclear: float = 0.5
    unmet: float = 0.0


class ReqWeight(BaseModel):
    justified: float = 2
    unjustified: float = 1


class Tiers(BaseModel):
    strong: float = 75
    possible: float = 55


class TestRules(BaseModel):
    strength_at: float = 0.8
    gap_below: float = 0.5
    time_scored: bool = False


class RankingSpec(BaseModel):
    version: str
    weights: Weights
    requirement_status_values: StatusValues
    requirement_weight: ReqWeight
    tiers: Tiers
    test: TestRules
    tiebreakers: list[str]


@lru_cache(maxsize=1)
def load_ranking_spec(path: Path | None = None) -> RankingSpec:
    with open(path or DEFAULT_PATH, encoding="utf-8") as f:
        return RankingSpec.model_validate(yaml.safe_load(f))


RANKING_SPEC_VERSION = load_ranking_spec().version
