from __future__ import annotations

from dataclasses import dataclass


def shrink_rate(raw: float, n: float, prior: float, k: float) -> float:
    n = max(float(n), 0.0)
    k = max(float(k), 0.0)
    if n + k <= 0:
        return prior
    return (n * raw + k * prior) / (n + k)


def reliability(n: float, k: float) -> float:
    n = max(float(n), 0.0)
    k = max(float(k), 0.0)
    return n / (n + k) if n + k else 0.0


@dataclass(slots=True)
class ReliabilityConfig:
    batter_pa_k: float = 250.0
    batter_bbe_k: float = 150.0
    pitcher_bf_k: float = 300.0
    pitcher_bbe_k: float = 180.0
    bvp_pa_k: float = 60.0
    split_pa_k: float = 120.0
