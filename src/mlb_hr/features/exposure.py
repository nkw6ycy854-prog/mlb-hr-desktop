from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(slots=True)
class StarterExposure:
    q_by_pa: dict[int, float]
    expected_pa_vs_starter: float
    expected_pa_vs_bullpen: float
    reliability: float
    avg_starter_bf: float


class StarterExposureEngine:
    def __init__(self, config: dict | None = None) -> None:
        self.config = config or {}

    def project(
        self,
        lineup_slot: int,
        pa_distribution: dict[int, float],
        avg_starter_bf: float,
        starter_sample_starts: int,
    ) -> StarterExposure:
        league_bf = float(self.config.get("league_starter_bf_prior", 18.5))
        k = float(self.config.get("starter_bf_shrink_k", 8.0))
        n = max(starter_sample_starts, 0)
        bf = (n * avg_starter_bf + k * league_bf) / (n + k) if n + k else league_bf
        scale = float(self.config.get("starter_survival_scale", 3.4))
        max_pa = max(pa_distribution) if pa_distribution else 6
        q: dict[int, float] = {}
        for pa_idx in range(1, max_pa + 1):
            bf_position = lineup_slot + 9 * (pa_idx - 1)
            q[pa_idx] = 1.0 / (1.0 + math.exp((bf_position - bf) / max(scale, 0.5)))
        expected_total = sum(n_pa * prob for n_pa, prob in pa_distribution.items())
        expected_sp = 0.0
        for pa_idx in range(1, max_pa + 1):
            p_occurs = sum(prob for n_pa, prob in pa_distribution.items() if n_pa >= pa_idx)
            expected_sp += p_occurs * q[pa_idx]
        rel = min(1.0, n / (n + 6.0)) if n else 0.25
        return StarterExposure(
            q_by_pa=q,
            expected_pa_vs_starter=expected_sp,
            expected_pa_vs_bullpen=max(0.0, expected_total - expected_sp),
            reliability=rel,
            avg_starter_bf=bf,
        )
