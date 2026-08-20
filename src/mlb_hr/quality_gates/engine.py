from __future__ import annotations

from dataclasses import dataclass

from mlb_hr.domain.enums import (
    CriticVerdict,
    IntegrityStatus,
    ModelClassification,
    ModelHealth,
    UserActionLabel,
    WarningSeverity,
)
from mlb_hr.domain.models import DataWarning
from mlb_hr.model.package import ModelPackage
from mlb_hr.quality_gates.critic import CriticResult
from mlb_hr.uncertainty.engine import UncertaintyResult


@dataclass(slots=True)
class GateResult:
    classification: ModelClassification
    user_action: UserActionLabel
    reasons: list[str]


class QualityGateEngine:
    def __init__(self, package: ModelPackage, *, allow_unvalidated_demo: bool = False) -> None:
        self.package=package
        self.t=package.manifest.thresholds
        self.allow_unvalidated_demo=allow_unvalidated_demo

    def classify(
        self,
        *,
        integrity: IntegrityStatus,
        probability: float,
        matchup_score: float,
        uncertainty: UncertaintyResult,
        critic: CriticResult,
        warnings: list[DataWarning],
        model_health: ModelHealth,
    ) -> GateResult:
        reasons=[]
        if integrity != IntegrityStatus.PASS:
            return GateResult(ModelClassification.NOT_ELIGIBLE,UserActionLabel.PASS,["DATA_INTEGRITY_FAIL"])
        if any(w.severity==WarningSeverity.CRITICAL for w in warnings):
            return GateResult(ModelClassification.NOT_ELIGIBLE,UserActionLabel.PASS,["CRITICAL_WARNING"])
        if model_health==ModelHealth.RED:
            return GateResult(ModelClassification.NO_BET,UserActionLabel.PASS,["MODEL_HEALTH_RED"])
        if not self.package.release_ready and not self.allow_unvalidated_demo:
            return GateResult(ModelClassification.NO_BET,UserActionLabel.PASS,["MODEL_NOT_VALIDATED"])
        if critic.verdict==CriticVerdict.REJECT:
            return GateResult(ModelClassification.NO_BET,UserActionLabel.PASS,["MODEL_CRITIC_REJECT",*critic.reasons])
        max_bet_ood=float(self.t.get("max_bet_ood",80))
        max_primary_ood=float(self.t.get("max_primary_ood",55))
        if uncertainty.ood_score>=max_bet_ood:
            return GateResult(ModelClassification.NO_BET,UserActionLabel.PASS,["OOD_TOO_HIGH"])
        primary_p=float(self.t.get("primary_probability",0.20))
        second_p=float(self.t.get("secondary_probability",0.17))
        watch_p=float(self.t.get("watch_probability",0.14))
        primary_c=float(self.t.get("primary_confidence",70))
        second_c=float(self.t.get("secondary_confidence",55))
        primary_m=float(self.t.get("primary_matchup",80))
        second_m=float(self.t.get("secondary_matchup",70))
        has_major=any(w.severity==WarningSeverity.MAJOR for w in warnings)
        if probability>=primary_p and uncertainty.confidence_score>=primary_c and matchup_score>=primary_m and uncertainty.ood_score<max_primary_ood and critic.verdict==CriticVerdict.PASS and not has_major:
            reasons.extend(["STRONG_HR_PROBABILITY","HIGH_ROBUSTNESS","STRONG_MATCHUP"])
            return GateResult(ModelClassification.PRIMARY,UserActionLabel.RECOMMENDED,reasons)
        if probability>=second_p and uncertainty.confidence_score>=second_c and matchup_score>=second_m and critic.verdict!=CriticVerdict.REJECT:
            reasons.extend(["GOOD_HR_PROBABILITY","ACCEPTABLE_ROBUSTNESS"])
            return GateResult(ModelClassification.SECONDARY,UserActionLabel.RECOMMENDED if not has_major else UserActionLabel.OPTIONAL,reasons)
        if probability>=watch_p:
            return GateResult(ModelClassification.WATCH,UserActionLabel.OPTIONAL,["WATCH_THRESHOLD_MET"])
        return GateResult(ModelClassification.NO_BET,UserActionLabel.PASS,["BELOW_QUALIFICATION_THRESHOLD"])
