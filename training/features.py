from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

# V1 candidate starts with features that can be reconstructed strictly pre-game from the
# Statcast archive. More complex live features remain implemented in the app, but they
# only enter a frozen release after their own historical/ablation dataset proves value.
CORE_FEATURES = [
    "league_hr_pa",
    "batter_hr_pa",
    "batter_barrel_rate",
    "batter_hardhit_rate",
    "batter_avg_ev",
    "batter_flyball_rate",
    "batter_xslg",
    "batter_platoon_delta",
    "batter_recent_delta",
    "pitcher_hr_bf",
    "pitcher_barrel_allowed",
    "pitcher_hardhit_allowed",
    "pitcher_avg_ev_allowed",
    "pitcher_xslg_allowed",
    "pitcher_platoon_delta",
    "pitcher_recent_delta",
]

FEATURE_GROUPS: dict[str, list[str]] = {
    "BATTER_POWER": ["batter_hr_pa", "batter_barrel_rate", "batter_hardhit_rate", "batter_avg_ev", "batter_flyball_rate", "batter_xslg"],
    "PITCHER_VULNERABILITY": ["pitcher_hr_bf", "pitcher_barrel_allowed", "pitcher_hardhit_allowed", "pitcher_avg_ev_allowed", "pitcher_xslg_allowed"],
    "PLATOON": ["batter_platoon_delta", "pitcher_platoon_delta"],
    "RECENT": ["batter_recent_delta", "pitcher_recent_delta"],
}

DEFAULT_K = {
    "batter_pa": 250.0,
    "batter_bbe": 150.0,
    "pitcher_bf": 300.0,
    "pitcher_bbe": 180.0,
    "split": 120.0,
    "recent_batter": 90.0,
    "recent_pitcher": 110.0,
}


def _num(s: pd.Series, default: float = 0.0) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").fillna(default).astype(float)


def _rate(num: pd.Series, den: pd.Series, prior: pd.Series | float, k: float) -> pd.Series:
    n = _num(den)
    x = _num(num)
    raw = np.divide(x, n, out=np.zeros_like(x, dtype=float), where=n.to_numpy() > 0)
    p = _num(prior) if isinstance(prior, pd.Series) else pd.Series(float(prior), index=n.index)
    w = n / (n + float(k))
    return pd.Series(w.to_numpy() * raw + (1.0 - w.to_numpy()) * p.to_numpy(), index=n.index)


def transform_raw_features(df: pd.DataFrame, ks: dict[str, float] | None = None) -> pd.DataFrame:
    """Convert strictly pre-game raw counts into the runtime feature contract.

    Shrinkage is performed against the rolling league prior. Missing observations are
    treated as missing evidence and shrink toward the prior; they are not represented as
    a fake observed league-average sample.
    """
    k = dict(DEFAULT_K)
    if ks:
        k.update({key: float(value) for key, value in ks.items()})
    out = df.copy()
    league = _num(out["league_hr_pa_raw"], 0.03).clip(0.005, 0.10)
    out["league_hr_pa"] = league

    b_pa = _num(out["batter_pa_prior"])
    b_bbe = _num(out["batter_bbe_prior"])
    p_bf = _num(out["pitcher_bf_prior"])
    p_bbe = _num(out["pitcher_bbe_prior"])

    out["batter_hr_pa"] = _rate(out["batter_hr_prior"], b_pa, league, k["batter_pa"])
    out["pitcher_hr_bf"] = _rate(out["pitcher_hr_prior"], p_bf, league, k["pitcher_bf"])

    # Contact priors use conservative league process priors when there is no evidence.
    out["batter_barrel_rate"] = _rate(out["batter_barrel_prior"], b_bbe, 0.07, k["batter_bbe"])
    out["batter_hardhit_rate"] = _rate(out["batter_hardhit_prior"], b_bbe, 0.38, k["batter_bbe"])
    out["pitcher_barrel_allowed"] = _rate(out["pitcher_barrel_prior"], p_bbe, 0.07, k["pitcher_bbe"])
    out["pitcher_hardhit_allowed"] = _rate(out["pitcher_hardhit_prior"], p_bbe, 0.38, k["pitcher_bbe"])

    def shrunk_mean(sum_col: str, n_col: str, prior: float, kk: float) -> pd.Series:
        n = _num(out[n_col]); total = _num(out[sum_col]); raw = np.divide(total, n, out=np.full(len(n), prior, dtype=float), where=n.to_numpy() > 0)
        w = n / (n + kk)
        return pd.Series(w.to_numpy() * raw + (1 - w.to_numpy()) * prior, index=out.index)

    out["batter_avg_ev"] = shrunk_mean("batter_ev_sum_prior", "batter_ev_n_prior", 88.5, k["batter_bbe"])
    out["pitcher_avg_ev_allowed"] = shrunk_mean("pitcher_ev_sum_prior", "pitcher_ev_n_prior", 88.5, k["pitcher_bbe"])
    out["batter_flyball_rate"] = _rate(out["batter_fb_prior"], out["batter_bbtype_n_prior"], 0.23, k["batter_bbe"])
    out["batter_xslg"] = shrunk_mean("batter_xslg_sum_prior", "batter_xslg_n_prior", 0.45, k["batter_bbe"])
    out["pitcher_xslg_allowed"] = shrunk_mean("pitcher_xslg_sum_prior", "pitcher_xslg_n_prior", 0.45, k["pitcher_bbe"])

    b_split = _rate(out["batter_split_hr_prior"], out["batter_split_pa_prior"], out["batter_hr_pa"], k["split"])
    p_split = _rate(out["pitcher_split_hr_prior"], out["pitcher_split_bf_prior"], out["pitcher_hr_bf"], k["split"])
    out["batter_platoon_delta"] = b_split - out["batter_hr_pa"]
    out["pitcher_platoon_delta"] = p_split - out["pitcher_hr_bf"]

    b_recent = _rate(out["batter_hr_recent"], out["batter_pa_recent"], out["batter_hr_pa"], k["recent_batter"])
    p_recent = _rate(out["pitcher_hr_recent"], out["pitcher_bf_recent"], out["pitcher_hr_bf"], k["recent_pitcher"])
    out["batter_recent_delta"] = b_recent - out["batter_hr_pa"]
    out["pitcher_recent_delta"] = p_recent - out["pitcher_hr_bf"]

    # Reliability proxy used only for threshold development/stratification. Production
    # Confidence is generated by the full Uncertainty Engine.
    b_rel = b_pa / (b_pa + k["batter_pa"])
    p_rel = p_bf / (p_bf + k["pitcher_bf"])
    split_b_rel = _num(out["batter_split_pa_prior"]) / (_num(out["batter_split_pa_prior"]) + k["split"])
    split_p_rel = _num(out["pitcher_split_bf_prior"]) / (_num(out["pitcher_split_bf_prior"]) + k["split"])
    out["reliability_proxy"] = 100.0 * np.power(np.maximum(b_rel * p_rel * np.sqrt(np.maximum(split_b_rel * split_p_rel, 1e-8)), 1e-8), 1.0 / 3.0)

    for name in CORE_FEATURES:
        out[name] = pd.to_numeric(out[name], errors="coerce")
    return out


def game_rows(feature_df: pd.DataFrame) -> pd.DataFrame:
    """One pre-game candidate row per batter-game, using the first starter-facing PA.

    The observed game HR and PA totals are labels only and are never inputs to the model.
    """
    df = feature_df.copy()
    df["game_date"] = pd.to_datetime(df["game_date"])
    labels = df.groupby(["game_pk", "batter"], as_index=False).agg(
        actual_hr=("label_hr", "max"),
        actual_pa=("label_hr", "size"),
    )
    starters = df[df["is_starter_pitcher"].astype(bool)].sort_values(["game_pk", "batter", "at_bat_number"])
    first = starters.groupby(["game_pk", "batter"], as_index=False).first()
    first = first.merge(labels, on=["game_pk", "batter"], how="inner")
    first = first[first["lineup_slot"].between(1, 9)]
    return first


def lineup_pa_distributions(train_feature_df: pd.DataFrame) -> dict[str, dict[str, float]]:
    games = game_rows(train_feature_df)
    result: dict[str, dict[str, float]] = {}
    for slot in range(1, 10):
        vals = games.loc[games["lineup_slot"] == slot, "actual_pa"].astype(int)
        if vals.empty:
            continue
        counts = {n: int((vals == n).sum()) for n in range(1, 7)}
        counts[7] = int((vals >= 7).sum())
        total = sum(counts.values())
        if not total:
            continue
        # Small Dirichlet smoothing prevents zero probability in rare tails.
        denom = total + 7.0
        result[str(slot)] = {str(n): (counts[n] + 1.0) / denom for n in range(1, 8)}
    return result
