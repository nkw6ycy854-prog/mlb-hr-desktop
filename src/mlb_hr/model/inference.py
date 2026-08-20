from __future__ import annotations

from dataclasses import dataclass
import math

from mlb_hr.calibration.engine import CalibrationEngine
from mlb_hr.domain.math import clamp, logistic, logit
from mlb_hr.features.engine import CandidateFeatureBundle
from mlb_hr.model.package import ModelPackage


@dataclass(slots=True)
class InferenceResult:
    p_sp_per_pa: float
    p_bp_per_pa: float
    raw_game_probability: float
    final_probability: float
    matchup_score: float
    grade: str
    standardized_features: dict[str, float]


class ProbabilityEngine:
    def __init__(self, package: ModelPackage) -> None:
        self.package = package
        self.manifest = package.manifest
        self.calibrator = CalibrationEngine(self.manifest.calibration)

    def standardized(self, values: dict[str, float]) -> dict[str, float]:
        out: dict[str, float] = {}
        for name in self.manifest.feature_names:
            value = float(values.get(name, self.manifest.feature_means.get(name, 0.0)))
            mean = float(self.manifest.feature_means.get(name, 0.0))
            scale = abs(float(self.manifest.feature_scales.get(name, 1.0))) or 1.0
            out[name] = (value - mean) / scale
        return out

    def per_pa_probability(self, values: dict[str, float]) -> tuple[float, dict[str, float]]:
        z = self.standardized(values)
        linear = float(self.manifest.intercept)
        for name in self.manifest.feature_names:
            linear += float(self.manifest.coefficients.get(name, 0.0)) * z[name]
        return clamp(logistic(linear), 0.0005, 0.45), z

    def predict(self, bundle: CandidateFeatureBundle) -> InferenceResult:
        p_sp, z = self.per_pa_probability(bundle.vector.values)
        league = max(bundle.league_hr_pa, 0.005)
        bp_hr = max(bundle.bullpen.weighted_hr_bf, 0.001)
        # Candidate 2 neutral bullpen fallback: once the starter exits, return to the
        # batter's shrunk HR/PA talent rather than carrying the starter matchup through
        # every PA.  A bullpen-specific adjustment remains disabled until independently
        # validated out of sample (bullpen_adjustment_scale=0 in the frozen candidate).
        batter_baseline = clamp(float(bundle.vector.values.get("batter_hr_pa", league)), 0.0005, 0.45)
        scale = float(self.manifest.uncertainty.get("bullpen_adjustment_scale", 0.0))
        relative = (bp_hr - league) / league
        p_bp = logistic(logit(batter_baseline) + scale * relative * 0.12)
        p_bp = clamp(p_bp, 0.0005, 0.45)

        max_pa = max(bundle.pa.distribution) if bundle.pa.distribution else 6
        p_by_pa: dict[int, float] = {}
        for k in range(1, max_pa + 1):
            q = bundle.starter_exposure.q_by_pa.get(k, 0.0)
            p_by_pa[k] = q * p_sp + (1.0 - q) * p_bp

        raw_game = 0.0
        norm = sum(bundle.pa.distribution.values()) or 1.0
        for n, weight in bundle.pa.distribution.items():
            no_hr = 1.0
            for k in range(1, n + 1):
                no_hr *= 1.0 - p_by_pa.get(k, p_bp)
            raw_game += (weight / norm) * (1.0 - no_hr)
        raw_game = clamp(raw_game, 0.0, 0.95)
        final = self.calibrator.calibrate(raw_game)
        # Score is explicitly comparative, not a probability. Training packages can later replace this mapping.
        matchup = clamp(50.0 + 180.0 * (final - 0.12), 0.0, 100.0)
        grade = _grade(matchup)
        return InferenceResult(p_sp, p_bp, raw_game, final, matchup, grade, z)


def _grade(score: float) -> str:
    if score >= 90:
        return "A+"
    if score >= 85:
        return "A"
    if score >= 80:
        return "A-"
    if score >= 75:
        return "B+"
    if score >= 70:
        return "B"
    return "C"
