from __future__ import annotations

from dataclasses import dataclass


_DEFAULT = {
    1: {3: 0.05, 4: 0.43, 5: 0.42, 6: 0.09, 7: 0.01},
    2: {3: 0.07, 4: 0.46, 5: 0.39, 6: 0.075, 7: 0.005},
    3: {3: 0.09, 4: 0.49, 5: 0.35, 6: 0.065, 7: 0.005},
    4: {3: 0.11, 4: 0.51, 5: 0.32, 6: 0.055, 7: 0.005},
    5: {3: 0.13, 4: 0.52, 5: 0.30, 6: 0.045, 7: 0.005},
    6: {3: 0.15, 4: 0.53, 5: 0.275, 6: 0.04, 7: 0.005},
    7: {3: 0.18, 4: 0.53, 5: 0.25, 6: 0.035, 7: 0.005},
    8: {3: 0.21, 4: 0.52, 5: 0.235, 6: 0.03, 7: 0.005},
    9: {3: 0.24, 4: 0.51, 5: 0.22, 6: 0.025, 7: 0.005},
}


@dataclass(slots=True)
class PAProjection:
    distribution: dict[int, float]
    expected_pa: float
    p4_plus: float
    p5_plus: float
    reliability: float


class PAOpportunityEngine:
    def __init__(self, config: dict | None = None) -> None:
        self.config = config or {}

    def project(self, lineup_slot: int, *, home_team: bool, survival_probability: float = 0.98) -> PAProjection:
        raw_table = self.config.get("pa_distribution_by_slot") or _DEFAULT
        slot_data = raw_table.get(str(lineup_slot)) if isinstance(raw_table, dict) else None
        if slot_data is None and isinstance(raw_table, dict):
            slot_data = raw_table.get(lineup_slot)
        if not slot_data:
            slot_data = _DEFAULT.get(lineup_slot, _DEFAULT[5])
        dist = {int(k): float(v) for k, v in slot_data.items()}
        if home_team:
            # Home-team opportunity adjustment is package-controlled. A validated package may set
            # it to zero when the empirical PA distribution already absorbs home/away effects.
            shift = min(max(float(self.config.get("home_ninth_shift", 0.04)), 0.0), dist.get(5, 0.0))
            dist[5] = max(0.0, dist.get(5, 0.0) - shift)
            dist[4] = dist.get(4, 0.0) + shift
        survival_probability = max(0.0, min(1.0, survival_probability))
        # Approximate substitution risk by moving a small tail mass one PA lower.
        if survival_probability < 0.999:
            loss = (1.0 - survival_probability) * 0.25
            adjusted: dict[int, float] = {}
            for n, w in dist.items():
                move = w * loss
                adjusted[n] = adjusted.get(n, 0.0) + w - move
                adjusted[max(1, n - 1)] = adjusted.get(max(1, n - 1), 0.0) + move
            dist = adjusted
        norm = sum(dist.values()) or 1.0
        dist = {n: w / norm for n, w in dist.items()}
        expected = sum(n * w for n, w in dist.items())
        return PAProjection(
            distribution=dist,
            expected_pa=expected,
            p4_plus=sum(w for n, w in dist.items() if n >= 4),
            p5_plus=sum(w for n, w in dist.items() if n >= 5),
            reliability=0.85 if lineup_slot in range(1, 10) else 0.4,
        )
