from __future__ import annotations

from dataclasses import dataclass

from mlb_hr.domain.enums import CriticVerdict, WarningSeverity
from mlb_hr.features.engine import CandidateFeatureBundle
from mlb_hr.uncertainty.engine import UncertaintyResult


@dataclass(slots=True)
class CriticResult:
    verdict: CriticVerdict
    reasons: list[str]
    main_risk: str | None


class LocalModelCritic:
    def review(self, bundle: CandidateFeatureBundle, uncertainty: UncertaintyResult) -> CriticResult:
        reasons: list[str]=[]
        risk: str | None=None
        verdict=CriticVerdict.PASS
        if uncertainty.ood_score >= 85:
            return CriticResult(CriticVerdict.REJECT,["EXTREME_OOD"],"Caso muy poco representado en los datos de entrenamiento")
        if uncertainty.ood_score >= 60:
            verdict=CriticVerdict.CAUTION
            reasons.append("HIGH_OOD")
            risk="Soporte histórico limitado para un caso similar"
        bp_share = bundle.starter_exposure.expected_pa_vs_bullpen / max(
            bundle.starter_exposure.expected_pa_vs_starter + bundle.starter_exposure.expected_pa_vs_bullpen, 1e-6
        )
        if bp_share > 0.55 and bundle.bullpen.reliability < 0.35:
            verdict=CriticVerdict.CAUTION
            reasons.append("BULLPEN_ASSUMPTION_DOMINATES")
            risk="Gran parte de la oportunidad depende de un bullpen incierto"
        value_keys = {"PITCH_TYPE": "pitch_type_match", "VELOCITY": "velocity_match", "ZONE": "zone_match"}
        low_correlated = sum(
            1 for key, value_key in value_keys.items()
            if bundle.vector.reliabilities.get(key, 0) < 0.25
            and abs(bundle.vector.values.get(value_key, 0.0)) > 0.05
        )
        if low_correlated >= 2:
            verdict=CriticVerdict.CAUTION
            reasons.append("CORRELATED_SMALL_SAMPLE_MATCHUP_SIGNALS")
            risk=risk or "Varias señales específicas dependen de muestras pequeñas"
        for w in bundle.vector.warnings:
            if w.severity == WarningSeverity.CRITICAL:
                return CriticResult(CriticVerdict.REJECT,[w.code],w.message)
            if w.severity == WarningSeverity.MAJOR and verdict == CriticVerdict.PASS:
                verdict=CriticVerdict.CAUTION
                reasons.append(w.code)
                risk=risk or w.message
        if not reasons:
            reasons.append("NO_MAJOR_MODEL_CRITIC_ISSUE")
        return CriticResult(verdict,reasons,risk)
