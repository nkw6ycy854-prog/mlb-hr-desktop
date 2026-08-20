from __future__ import annotations

import math


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def logistic(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def logit(p: float) -> float:
    p = clamp(p, 1e-9, 1 - 1e-9)
    return math.log(p / (1 - p))


def american_to_decimal(odds: int) -> float:
    if odds >= 100:
        return 1.0 + odds / 100.0
    if odds <= -100:
        return 1.0 + 100.0 / abs(odds)
    raise ValueError("American odds must be >= +100 or <= -100")


def decimal_to_implied(decimal_odds: float) -> float:
    if decimal_odds <= 1:
        raise ValueError("Decimal odds must be > 1")
    return 1.0 / decimal_odds


def payout_for_stake(stake: float, american_odds: int) -> tuple[float, float]:
    decimal_odds = american_to_decimal(american_odds)
    total = stake * decimal_odds
    return total, total - stake


def game_hr_probability(per_pa_probability: float, pa_distribution: dict[int, float]) -> float:
    p = clamp(per_pa_probability, 0.0, 0.999999)
    total = 0.0
    norm = sum(max(v, 0.0) for v in pa_distribution.values())
    if norm <= 0:
        return 0.0
    for n, weight in pa_distribution.items():
        if n < 0:
            continue
        w = max(weight, 0.0) / norm
        total += w * (1.0 - (1.0 - p) ** n)
    return clamp(total, 0.0, 1.0)


def weighted_geometric_mean(values: list[tuple[float, float]], floor: float = 1e-6) -> float:
    weighted_log = 0.0
    weight_sum = 0.0
    for value, weight in values:
        if weight <= 0:
            continue
        weighted_log += weight * math.log(max(value, floor))
        weight_sum += weight
    if weight_sum == 0:
        return 0.0
    return math.exp(weighted_log / weight_sum)
