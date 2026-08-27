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


def test_combination_filter_status_values_are_stable():
    assert CombinationFilterStatus.QUALIFIED.value == "QUALIFIED"
    assert CombinationFilterStatus.FALLBACK.value == "FALLBACK"


def card(name, prob, classification, game_pk=1):
    player = PlayerRef(abs(hash(name)) % 100000, name)
    pitcher = PlayerRef(999, "Pitcher")
    dist = ProbabilityDistribution(prob, prob, prob, prob, 0.0, 90.0)
    pred = Prediction(
        prediction_id=f"pred-{name}", snapshot_id="snap", game_pk=game_pk,
        player=player, opposing_pitcher=pitcher, team_name="A", opponent_name="B",
        game_time=None, final_hr_probability=prob, raw_hr_probability=prob,
        matchup_score=80, grade="B", reliability=90, confidence_score=80,
        confidence_label=ConfidenceLabel.HIGH, distribution=dist,
        classification=classification, user_action=UserActionLabel.RECOMMENDED,
        integrity=IntegrityStatus.PASS, critic=CriticVerdict.PASS,
        reasons=[], main_risk=None, warnings=[],
        model_version="V1", feature_version="F1", calibration_version="C1", quality_gate_version="Q1",
    )
    market = MarketDecision(quote=None, label=MarketPriceLabel.NO_ODDS)
    return PredictionCard(prediction=pred, market=market)


def test_best2_falls_back_when_only_watch_and_no_bet_exist():
    cards = [card("A", .16, ModelClassification.WATCH),
             card("B", .14, ModelClassification.NO_BET)]
    combo = {c.kind: c for c in CombinationEngine().build(cards)}["BEST_2_MAN"]
    assert combo.filter_status == CombinationFilterStatus.FALLBACK
    assert {leg.player_name for leg in combo.legs} == {"A", "B"}


def test_qualified_combo_wins_when_enough_qualified_legs_exist():
    cards = [card("A", .18, ModelClassification.PRIMARY),
             card("B", .16, ModelClassification.SECONDARY),
             card("C", .15, ModelClassification.WATCH)]
    combo = {c.kind: c for c in CombinationEngine().build(cards)}["BEST_2_MAN"]
    assert combo.filter_status == CombinationFilterStatus.QUALIFIED
    assert all(leg.classification in {ModelClassification.PRIMARY, ModelClassification.SECONDARY} for leg in combo.legs)


def test_not_eligible_is_never_used_for_fallback():
    cards = [card("A", .15, ModelClassification.WATCH),
             card("X", .30, ModelClassification.NOT_ELIGIBLE)]
    assert "BEST_2_MAN" not in {c.kind for c in CombinationEngine().build(cards)}


def test_combination_engine_builds_fallback_from_the_exact_reported_slate_shape():
    # Same shape as the reported "HOY empty" slate: a confirmed slate with zero
    # PRIMARY/SECONDARY, several WATCH/NO_BET, and one NOT_ELIGIBLE row passed
    # through unfiltered (as analyze_slate() actually does -- the engine itself
    # is responsible for excluding NOT_ELIGIBLE).
    cards = [
        card("Watch One", .20, ModelClassification.WATCH),
        card("Watch Two", .15, ModelClassification.WATCH),
        card("No Bet One", .10, ModelClassification.NO_BET),
        card("Ineligible", .90, ModelClassification.NOT_ELIGIBLE),
    ]
    combos = {c.kind: c for c in CombinationEngine().build(cards)}
    assert "BEST_2_MAN" in combos
    best2 = combos["BEST_2_MAN"]
    assert best2.filter_status == CombinationFilterStatus.FALLBACK
    used_names = {leg.player_name for leg in best2.legs}
    assert "Ineligible" not in used_names
    assert used_names <= {"Watch One", "Watch Two", "No Bet One"}
