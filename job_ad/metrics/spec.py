"""Load and query the metric spec (docs/job-ad-drafter/metrics/job-ad-metrics.yaml)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "docs" / "job-ad-drafter" / "metrics" / "job-ad-metrics.yaml"


class Norm(BaseModel):
    kind: str = "band"  # band | linear
    lo: Optional[float] = None
    hi: Optional[float] = None
    slack: Optional[float] = None


class Gate(BaseModel):
    op: str
    value: float


class MetricSpec(BaseModel):
    id: str
    dimension: str
    grader: str
    type: str  # pass_fail | count | ratio | number
    norm: Optional[Norm] = None
    overrides: Optional[dict[str, Norm]] = None
    gate: Optional[Gate] = None
    params: Optional[dict[str, Any]] = None
    jurisdictions: Optional[list[str]] = None
    applies_when: Optional[str] = None
    gate_when: Optional[str] = None  # name of a boolean ScoringContext field; gate only when true


class Dimension(BaseModel):
    weight: float
    gate: bool = False


class Spec(BaseModel):
    version: str
    publish_threshold: float
    review_threshold: float
    gates: list[str]
    dimensions: dict[str, Dimension]
    metrics: list[MetricSpec]
    telemetry: list[str] = Field(default_factory=list)

    def metric(self, id: str) -> MetricSpec:
        for m in self.metrics:
            if m.id == id:
                return m
        raise KeyError(f"unknown metric {id}")

    def is_gate(self, m: MetricSpec, ctx: Optional[dict[str, Any]] = None) -> bool:
        """A metric is a gate if it carries a gate clause, is listed in spec.gates (prefix.* allowed),
        or has gate_when naming a context field that is true."""
        if m.gate_when:
            return bool(ctx and ctx.get(m.gate_when) is True)
        if m.gate:
            return True
        for g in self.gates:
            if g.endswith(".*") and m.id.startswith(g[:-1]):
                return True
            if g == m.id:
                return True
        return False


@lru_cache(maxsize=4)
def load_spec(path: Path = DEFAULT_PATH) -> Spec:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    spec = Spec.model_validate(data)
    seen: set[str] = set()
    for m in spec.metrics:
        if m.id in seen:
            raise ValueError(f"duplicate metric id {m.id}")
        seen.add(m.id)
        if m.dimension not in spec.dimensions:
            raise ValueError(f"metric {m.id} has unknown dimension {m.dimension}")
    return spec
