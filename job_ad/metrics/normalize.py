"""Raw value → 0..1, and gate evaluation."""
from __future__ import annotations

import math
from typing import Optional

from .spec import Gate, MetricSpec, Norm


def _clamp01(x: float) -> float:
    if x is None or math.isnan(x):
        return 0.0
    return max(0.0, min(1.0, x))


def normalize(raw: float, norm: Optional[Norm], type_: str) -> float:
    """band: 1 inside [lo, hi]; linear decay to 0 at lo-slack / hi+slack (missing lo/hi = unbounded).
    linear: raw / lo capped at 1."""
    if type_ == "pass_fail":
        return 1.0 if raw >= 1 else 0.0
    if norm is None:
        return _clamp01(raw)
    if norm.kind == "linear":
        return _clamp01(raw / (norm.lo if norm.lo is not None else 1.0))
    lo = norm.lo if norm.lo is not None else -math.inf
    hi = norm.hi if norm.hi is not None else math.inf
    slack = norm.slack or 0.0
    if lo <= raw <= hi:
        return 1.0
    if slack <= 0:
        return 0.0
    if raw < lo:
        return _clamp01(1 - (lo - raw) / slack)
    return _clamp01(1 - (raw - hi) / slack)


def pick_norm(m: MetricSpec, channel: Optional[str]) -> Optional[Norm]:
    if channel and m.overrides and channel in m.overrides:
        return m.overrides[channel]
    return m.norm


def gate_passes(raw: float, gate: Gate) -> bool:
    if gate.op == "==":
        return raw == gate.value
    if gate.op == ">=":
        return raw >= gate.value
    if gate.op == "<=":
        return raw <= gate.value
    raise ValueError(f"unknown gate op {gate.op}")
