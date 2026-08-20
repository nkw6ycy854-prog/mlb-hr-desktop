from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import random

from mlb_hr.domain.enums import ConfidenceLabel
from mlb_hr.domain.math import clamp, weighted_geometric_mean
from mlb_hr.domain.models import ProbabilityDistribution
from mlb_hr.features.engine import CandidateFeatureBundle
from mlb_hr.model.inference import ProbabilityEngine


@dataclass(slots=True)
class UncertaintyResult:
    distribution: ProbabilityDistribution
    confidence_score: float
    confidence_label: ConfidenceLabel
    training_support: float
    ood_score: float
    calibration_support: float
    primary_driver: str
    component_reliability: dict[str, float]


class UncertaintyEngine:
    def __init__(self, probability_engine: ProbabilityEngine) -> None:
        self.probability_engine = probability_engine
        self.manifest = probability_engine.manifest

    def evaluate(self, bundle: CandidateFeatureBundle, point_probability: float) -> UncertaintyResult:
        z = self.probability_engine.standardized(bundle.vector.values)
        ood = self._ood(z)
        training_support = clamp(100.0 - ood, 0.0, 100.0)
        calibration_support = float(self.manifest.metadata.get("calibration_support_default", 60.0 if self.manifest.release_ready else 30.0))
        rels = dict(bundle.vector.reliabilities)
        rels["MODEL_OOD"] = training_support / 100.0
        rels["CALIBRATION"] = calibration_support / 100.0

        draws = int(self.manifest.uncertainty.get("scenario_draws", 500))
        noise_scale = float(self.manifest.uncertainty.get("feature_noise_scale", 0.15))
        seed = _stable_seed(bundle.vector.snapshot_id, self.manifest.deterministic_seed)
        rng = random.Random(seed)
        scenario_probs: list[float] = []
        central_inference = self.probability_engine.predict(bundle)
        central_pa = max(central_inference.p_sp_per_pa, 1e-6)
        # Each draw represents plausible parameter/input state, not HR/no-HR outcome.
        for _ in range(max(100, min(draws, 2000))):
            values = dict(bundle.vector.values)
            for name in self.manifest.feature_names:
                group_rel = _feature_reliability(name, rels)
                scale = float(self.manifest.feature_scales.get(name, 1.0))
                sigma = noise_scale * scale * (1.0 - group_rel)
                if sigma > 0:
                    values[name] = values.get(name, self.manifest.feature_means.get(name, 0.0)) + rng.gauss(0.0, sigma)
            # Fast approximation: recompute per-PA then preserve PA/exposure structure through a scaled
            # game-level transformation around the central model. This keeps scenario uncertainty distinct
            # from aleatoric game outcome variance.
            p_pa, _ = self.probability_engine.per_pa_probability(values)
            ratio = p_pa / central_pa
            scen = 1.0 - (1.0 - point_probability) ** max(0.2, min(2.5, ratio))
            scenario_probs.append(clamp(scen, 0.0, 0.95))
        scenario_probs.sort()
        p10 = _quantile(scenario_probs, 0.10)
        p50 = _quantile(scenario_probs, 0.50)
        p90 = _quantile(scenario_probs, 0.90)
        width = p90 - p10
        stability = clamp(100.0 * (1.0 - width / max(point_probability + 0.08, 0.12)), 0.0, 100.0)

        exposure_total = bundle.starter_exposure.expected_pa_vs_starter + bundle.starter_exposure.expected_pa_vs_bullpen
        sp_w = bundle.starter_exposure.expected_pa_vs_starter / exposure_total if exposure_total else 0.5
        bp_w = 1.0 - sp_w
        grouped = [
            (max(rels.get("HISTORY", 0.0), 0.01), 1.5),
            (max(rels.get("SPLITS", 0.0), 0.01), 0.8),
            (max(rels.get("PA_OPPORTUNITY", 0.0), 0.01), 0.8),
            (max(training_support / 100.0, 0.01), 0.9),
            (max(calibration_support / 100.0, 0.01), 0.9),
            (max(stability / 100.0, 0.01), 1.2),
        ]
        # Only uncertainty from active predictive components can constrain the bet.
        # This prevents an ablated module (e.g. bullpen/park) from silently re-entering via Confidence.
        if abs(float(self.manifest.uncertainty.get("bullpen_adjustment_scale", 0.0))) > 1e-12:
            grouped.extend([
                (max(rels.get("STARTER_EXPOSURE", 0.0), 0.01), 1.0 * sp_w),
                (max(rels.get("BULLPEN", 0.0), 0.01), 1.0 * bp_w),
            ])
        active = set(self.manifest.feature_names)
        if {"park_delta", "weather_index"} & active:
            grouped.append((max(rels.get("PARK_ENVIRONMENT", 0.0), 0.01), 0.5))
        if "profile_change_score" in active:
            grouped.append((max(rels.get("CURRENT_PROFILE", 0.0), 0.01), 0.6))
        confidence = 100.0 * weighted_geometric_mean(grouped)
        # Bottleneck penalties, but no critical validity failure is handled here; integrity is a separate gate.
        bottleneck = min((v for v, w in grouped if w >= 0.5), default=1.0)
        if bottleneck < 0.25:
            confidence *= 0.70
        confidence = clamp(confidence, float(self.manifest.uncertainty.get("confidence_floor", 5)), 100.0)
        label = self._label(confidence)
        driver = min(
            ((name, rel) for name, rel in rels.items()),
            key=lambda x: x[1],
            default=("NONE", 1.0),
        )[0]
        return UncertaintyResult(
            distribution=ProbabilityDistribution(point_probability, p10, p50, p90, width, stability),
            confidence_score=confidence,
            confidence_label=label,
            training_support=training_support,
            ood_score=ood,
            calibration_support=calibration_support,
            primary_driver=driver,
            component_reliability=rels,
        )

    def _ood(self, z: dict[str, float]) -> float:
        if not z:
            return 100.0
        excess = [max(0.0, abs(v) - 1.5) for v in z.values()]
        rms = math.sqrt(sum(e * e for e in excess) / len(excess))
        return clamp(100.0 * (1.0 - math.exp(-rms / 2.0)), 0.0, 100.0)

    def _label(self, score: float) -> ConfidenceLabel:
        cfg = self.manifest.thresholds
        high = float(cfg.get("confidence_high", 75))
        med = float(cfg.get("confidence_medium", 50))
        low = float(cfg.get("confidence_low", 30))
        if score >= high:
            return ConfidenceLabel.HIGH
        if score >= med:
            return ConfidenceLabel.MEDIUM
        if score >= low:
            return ConfidenceLabel.LOW
        return ConfidenceLabel.VERY_LOW


def _feature_reliability(name: str, rels: dict[str, float]) -> float:
    if name.startswith("batter_") or name.startswith("pitcher_"):
        if "platoon" in name:
            return rels.get("SPLITS", 0.4)
        if "recent" in name or "profile" in name:
            return rels.get("CURRENT_PROFILE", 0.4)
        return rels.get("HISTORY", 0.4)
    if "pitch_type" in name:
        return rels.get("PITCH_TYPE", 0.3)
    if "velocity" in name:
        return rels.get("VELOCITY", 0.3)
    if "zone" in name:
        return rels.get("ZONE", 0.3)
    if "similar" in name:
        return rels.get("SIMILAR_PITCHERS", 0.2)
    if "bvp" in name:
        return rels.get("BVP", 0.1)
    if "park" in name or "weather" in name:
        return rels.get("PARK_ENVIRONMENT", 0.4)
    return rels.get("HISTORY", 0.5)


def _stable_seed(snapshot_id: str, base: int) -> int:
    digest = hashlib.sha256(f"{base}:{snapshot_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def _quantile(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        return 0.0
    pos = q * (len(sorted_values) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = pos - lo
    return sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac
