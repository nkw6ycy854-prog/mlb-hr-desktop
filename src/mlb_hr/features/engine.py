from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import uuid4

from mlb_hr.domain.enums import WarningSeverity
from mlb_hr.domain.models import DataWarning, FeatureVector, GameContext, LineupEntry, PlayerRef, WeatherSnapshot
from mlb_hr.features.bullpen import BullpenComponent, BullpenEngine
from mlb_hr.features.exposure import StarterExposure, StarterExposureEngine
from mlb_hr.features.pa import PAOpportunityEngine, PAProjection
from mlb_hr.features.park import ParkEnvironmentEngine, ParkEnvironmentResult
from mlb_hr.features.reliability import ReliabilityConfig, reliability, shrink_rate
from mlb_hr.storage.analytics import AnalyticsStore


@dataclass(slots=True)
class CandidateFeatureBundle:
    vector: FeatureVector
    pa: PAProjection
    starter_exposure: StarterExposure
    bullpen: BullpenComponent
    park: ParkEnvironmentResult
    batter_pa: int
    pitcher_bf: int
    batter_history_reliability: float
    pitcher_history_reliability: float
    profile_change_reliability: float
    opponent_starter_hr_bf: float
    league_hr_pa: float


class FeatureEngine:
    def __init__(self, analytics: AnalyticsStore, config: dict[str, Any] | None = None) -> None:
        self.analytics = analytics
        self.config = config or {}
        self.enabled_model_features = set(self.config.get("_enabled_model_features", []))
        self.relcfg = ReliabilityConfig(**self.config.get("reliability", {})) if self.config.get("reliability") else ReliabilityConfig()
        pa_cfg = dict(self.config.get("pa", {}))
        if "pa_distribution_by_slot" in self.config:
            pa_cfg["pa_distribution_by_slot"] = self.config["pa_distribution_by_slot"]
        if "home_ninth_shift" in self.config:
            pa_cfg["home_ninth_shift"] = self.config["home_ninth_shift"]
        self.pa_engine = PAOpportunityEngine(pa_cfg)
        self.exposure_engine = StarterExposureEngine(self.config.get("starter_exposure", {}))
        self.bullpen_engine = BullpenEngine(self.config.get("bullpen", {}))
        self.park_engine = ParkEnvironmentEngine(self.config.get("park", {}))

    def build(
        self,
        *,
        game: GameContext,
        batter_entry: LineupEntry,
        opposing_pitcher: PlayerRef,
        weather: WeatherSnapshot | None,
        opponent_team_abbr: str | None,
        active_bullpen_ids: set[int] | None = None,
        snapshot_id: str | None = None,
    ) -> CandidateFeatureBundle:
        cutoff = game.game_date
        batter = batter_entry.player
        hand = batter.bat_side
        p_hand = opposing_pitcher.throw_side
        league = self.analytics.league_hr_per_pa(cutoff)
        bh = self.analytics.batter_history(batter.player_id, cutoff, p_hand)
        ph = self.analytics.pitcher_history(opposing_pitcher.player_id, cutoff, hand)
        warnings: list[DataWarning] = []

        batter_hr = shrink_rate(bh.hr_pa, bh.pa, league, self.relcfg.batter_pa_k)
        pitcher_hr = shrink_rate(ph.hr_bf, ph.bf, league, self.relcfg.pitcher_bf_k)
        batter_barrel = shrink_rate(bh.barrel_rate, bh.bbe, 0.07, self.relcfg.batter_bbe_k)
        batter_hardhit = shrink_rate(bh.hardhit_rate, bh.bbe, 0.38, self.relcfg.batter_bbe_k)
        pitcher_barrel = shrink_rate(ph.barrel_allowed, ph.bbe, 0.07, self.relcfg.pitcher_bbe_k)
        pitcher_hardhit = shrink_rate(ph.hardhit_allowed, ph.bbe, 0.38, self.relcfg.pitcher_bbe_k)

        split_batter = shrink_rate(bh.split_hr_pa, max(bh.pa * 0.45, 0), batter_hr, self.relcfg.split_pa_k)
        split_pitcher = shrink_rate(ph.split_hr_bf, max(ph.bf * 0.45, 0), pitcher_hr, self.relcfg.split_pa_k)
        batter_platoon_delta = split_batter - batter_hr
        pitcher_platoon_delta = split_pitcher - pitcher_hr
        recent_batter = shrink_rate(bh.recent_60_hr_pa, min(bh.pa, 120), batter_hr, 90)
        recent_pitcher = shrink_rate(ph.recent_60_hr_bf, min(ph.bf, 150), pitcher_hr, 110)

        if "pitch_type_match" in self.enabled_model_features:
            pitch_delta, pitch_rel = self.analytics.pitch_type_match(batter.player_id, opposing_pitcher.player_id, cutoff)
        else:
            pitch_delta, pitch_rel = 0.0, 1.0
        if "velocity_match" in self.enabled_model_features:
            velo_delta, velo_rel = self.analytics.velocity_match(batter.player_id, opposing_pitcher.player_id, cutoff)
        else:
            velo_delta, velo_rel = 0.0, 1.0
        if "zone_match" in self.enabled_model_features:
            zone_delta, zone_rel = self.analytics.zone_match(batter.player_id, opposing_pitcher.player_id, cutoff)
        else:
            zone_delta, zone_rel = 0.0, 1.0

        if "similar_pitcher_delta" in self.enabled_model_features:
            sim = self.analytics.similar_pitcher_signal(batter.player_id, opposing_pitcher.player_id, p_hand or "R", cutoff)
            sim_delta = shrink_rate(sim.batter_hr_pa, sim.batter_pa, batter_hr, 80) - batter_hr if sim.batter_pa else 0.0
        else:
            from mlb_hr.storage.analytics import SimilarPitcherResult
            sim = SimilarPitcherResult(reliability=1.0)
            sim_delta = 0.0

        if "bvp_delta" in self.enabled_model_features:
            bvp_pa, _, bvp_raw = self.analytics.bvp(batter.player_id, opposing_pitcher.player_id, cutoff)
            bvp_shrunk = shrink_rate(bvp_raw, bvp_pa, batter_hr, self.relcfg.bvp_pa_k)
            bvp_delta = bvp_shrunk - batter_hr
        else:
            bvp_pa, bvp_delta = 0, 0.0

        if "profile_change_score" in self.enabled_model_features:
            b_change, b_change_rel = self.analytics.batter_profile_change(batter.player_id, cutoff)
            p_change, p_change_rel = self.analytics.pitcher_profile_change(opposing_pitcher.player_id, cutoff)
            profile_change = 0.5 * b_change + 0.5 * p_change
            profile_change_rel = (b_change_rel + p_change_rel) / 2.0
        else:
            profile_change, profile_change_rel = 0.0, 1.0

        park_active = "park_delta" in self.enabled_model_features or "weather_index" in self.enabled_model_features
        park = self.park_engine.evaluate(game.venue, hand, weather)
        if not park_active:
            park.park_fit_delta = 0.0
            park.weather_index = 0.0
            park.park_reliability = 1.0
            park.environment_reliability = 1.0
            park.reasons.clear(); park.warnings.clear()

        survival = float(self.config.get("player_survival_default", 0.985))
        pa = self.pa_engine.project(
            batter_entry.batting_order,
            home_team=batter.team_id == game.home_team_id,
            survival_probability=survival,
        )
        avg_bf, starts = self.analytics.starter_avg_bf(opposing_pitcher.player_id, cutoff)
        exposure = self.exposure_engine.project(batter_entry.batting_order, pa.distribution, avg_bf, starts)

        bullpen_candidates = self.analytics.team_bullpen_candidates(opponent_team_abbr or "", cutoff, active_bullpen_ids)
        bullpen = self.bullpen_engine.evaluate(bullpen_candidates, league)

        if bh.pa < 100:
            warnings.append(DataWarning("COLD_START_BATTER", WarningSeverity.MAJOR if bh.pa < 30 else WarningSeverity.MINOR, "Muestra MLB limitada del bateador", "COLD_START"))
        if ph.bf < 100:
            warnings.append(DataWarning("COLD_START_PITCHER", WarningSeverity.MAJOR if ph.bf < 30 else WarningSeverity.MINOR, "Muestra MLB limitada del pitcher", "COLD_START"))
        if "zone_match" in self.enabled_model_features and zone_rel < 0.25:
            warnings.append(DataWarning("ZONE_UNRELIABLE", WarningSeverity.MINOR, "Evidencia por zona limitada", "ZONE"))
        if bullpen.reliability < 0.35 and exposure.expected_pa_vs_bullpen >= 1.5:
            warnings.append(DataWarning("BULLPEN_UNCERTAIN", WarningSeverity.MAJOR, "Alta incertidumbre sobre el bullpen esperado", "BULLPEN"))
        if park.environment_reliability < 0.4:
            warnings.append(DataWarning("ENVIRONMENT_UNCERTAIN", WarningSeverity.MINOR, "Entorno meteorológico incierto", "PARK_ENVIRONMENT"))

        values = {
            "league_hr_pa": league,
            "batter_hr_pa": batter_hr,
            "batter_barrel_rate": batter_barrel,
            "batter_hardhit_rate": batter_hardhit,
            "batter_avg_ev": bh.avg_ev,
            "batter_flyball_rate": bh.flyball_rate,
            "batter_xslg": bh.xslg,
            "batter_platoon_delta": batter_platoon_delta,
            "batter_recent_delta": recent_batter - batter_hr,
            "pitcher_hr_bf": pitcher_hr,
            "pitcher_barrel_allowed": pitcher_barrel,
            "pitcher_hardhit_allowed": pitcher_hardhit,
            "pitcher_avg_ev_allowed": ph.avg_ev_allowed,
            "pitcher_xslg_allowed": ph.xslg_allowed,
            "pitcher_platoon_delta": pitcher_platoon_delta,
            "pitcher_recent_delta": recent_pitcher - pitcher_hr,
            "pitch_type_match": pitch_delta,
            "velocity_match": velo_delta,
            "zone_match": zone_delta,
            "similar_pitcher_delta": sim_delta,
            "bvp_delta": bvp_delta,
            "park_delta": park.park_fit_delta,
            "weather_index": park.weather_index,
            "profile_change_score": profile_change,
        }
        reliabilities = {
            "HISTORY": (bh.reliability + ph.reliability) / 2.0,
            "CURRENT_PROFILE": profile_change_rel if abs(profile_change) > 0.01 else min(1.0, (bh.reliability + ph.reliability) / 2),
            "SPLITS": min(1.0, (reliability(bh.pa * .45, self.relcfg.split_pa_k) + reliability(ph.bf * .45, self.relcfg.split_pa_k)) / 2),
            "PITCH_TYPE": pitch_rel,
            "VELOCITY": velo_rel,
            "ZONE": zone_rel,
            "SIMILAR_PITCHERS": sim.reliability,
            "BVP": reliability(bvp_pa, self.relcfg.bvp_pa_k),
            "PA_OPPORTUNITY": pa.reliability,
            "STARTER_EXPOSURE": exposure.reliability,
            "BULLPEN": bullpen.reliability,
            "PARK_ENVIRONMENT": min(park.park_reliability, park.environment_reliability),
        }
        vector = FeatureVector(
            batter_id=batter.player_id,
            pitcher_id=opposing_pitcher.player_id,
            game_pk=game.game_pk,
            values=values,
            reliabilities=reliabilities,
            warnings=warnings,
            snapshot_id=snapshot_id or str(uuid4()),
        )
        return CandidateFeatureBundle(
            vector=vector,
            pa=pa,
            starter_exposure=exposure,
            bullpen=bullpen,
            park=park,
            batter_pa=bh.pa,
            pitcher_bf=ph.bf,
            batter_history_reliability=bh.reliability,
            pitcher_history_reliability=ph.reliability,
            profile_change_reliability=profile_change_rel,
            opponent_starter_hr_bf=pitcher_hr,
            league_hr_pa=league,
        )
