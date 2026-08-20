from pathlib import Path
from mlb_hr.combinations.engine import CombinationEngine
from mlb_hr.domain.enums import *
from mlb_hr.domain.models import *
from mlb_hr.model.package import ModelPackage
from mlb_hr.quality_gates.critic import CriticResult
from mlb_hr.quality_gates.engine import QualityGateEngine
from mlb_hr.uncertainty.engine import UncertaintyResult


def unc():
    return UncertaintyResult(ProbabilityDistribution(.25,.22,.25,.28,.06,85),85,ConfidenceLabel.HIGH,90,10,90,'NONE',{})


def test_unvalidated_package_cannot_recommend():
    root=Path(__file__).resolve().parents[1];pkg=ModelPackage(root/'model_packages'/'development_baseline')
    r=QualityGateEngine(pkg).classify(integrity=IntegrityStatus.PASS,probability=.3,matchup_score=95,uncertainty=unc(),critic=CriticResult(CriticVerdict.PASS,[],None),warnings=[],model_health=ModelHealth.YELLOW)
    assert r.classification==ModelClassification.NO_BET
    assert 'MODEL_NOT_VALIDATED' in r.reasons


def test_combinations_never_force_unqualified_legs():
    assert CombinationEngine().build([])==[]
