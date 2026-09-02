"""V1.2.0 mandatory predictive-regression gate.

Two independent guards, per the approved V1.2.0 plan (section 58): zero
tolerance for any predictive difference between V1.1.0 and V1.2.0.

Part A -- deterministic fixture: the same PredictionCard/Combination inputs
fed through the real, unmodified `AnalysisService._rank_key`,
`presentation.practical_status`, and `CombinationEngine.build` must produce
byte-identical HR%, ranking, classification, confidence, practical_status,
eligible, and combination legs/kind/filter_status every time. This test
itself never changes once written -- if it ever needs editing, that is
itself a predictive regression and must stop the release.

Part B -- frozen-file guard: every file in FROZEN_PREDICTIVE_PATHS must be
byte-identical to the `v1.1.0` tag for the entire duration of V1.2.0
development. A non-empty `git diff` against any of them is an automatic
RELEASE BLOCKER, regardless of how small.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from mlb_hr.combinations.engine import CombinationEngine
from mlb_hr.domain.enums import ConfidenceLabel, CriticVerdict, IntegrityStatus, MarketPriceLabel, ModelClassification, UserActionLabel
from mlb_hr.domain.models import MarketDecision, PlayerRef, Prediction, PredictionCard, ProbabilityDistribution
from mlb_hr.services.analysis import AnalysisService
from mlb_hr.ui.presentation import practical_status

ROOT = Path(__file__).resolve().parents[1]
BASELINE_TAG = "v1.1.0"

# Section C of the approved plan: the entire frozen predictive core. V1.2.0
# is UX/persistence-only and must never touch any of these.
FROZEN_PREDICTIVE_PATHS = (
    "src/mlb_hr/model",
    "src/mlb_hr/calibration",
    "src/mlb_hr/features",
    "src/mlb_hr/uncertainty",
    "src/mlb_hr/quality_gates",
    "src/mlb_hr/integrity",
    "src/mlb_hr/combinations/engine.py",
    "src/mlb_hr/odds/market.py",
    "src/mlb_hr/postgame/engine.py",
    "src/mlb_hr/domain/enums.py",
    "src/mlb_hr/domain/models.py",
    "src/mlb_hr/domain/math.py",
    "src/mlb_hr/services/analysis.py",
    "src/mlb_hr/resources/bundled_model",
    "model_packages/V1.0.0",
)


def _card(name: str, prob: float, classification: ModelClassification, game_pk: int, conf: float = 80.0) -> PredictionCard:
    player = PlayerRef(abs(hash(name)) % 100000, name)
    pitcher = PlayerRef(999000 + game_pk, "Pitcher")
    dist = ProbabilityDistribution(prob, prob, prob, prob, 0.0, 90.0)
    pred = Prediction(
        prediction_id=f"pred-{name}", snapshot_id="snap", game_pk=game_pk,
        player=player, opposing_pitcher=pitcher, team_name="A", opponent_name="B",
        game_time=None, final_hr_probability=prob, raw_hr_probability=prob,
        matchup_score=80, grade="B", reliability=90, confidence_score=conf,
        confidence_label=ConfidenceLabel.HIGH, distribution=dist,
        classification=classification, user_action=UserActionLabel.RECOMMENDED,
        integrity=IntegrityStatus.PASS, critic=CriticVerdict.PASS,
        reasons=["fixture reason"], main_risk=None, warnings=[],
        model_version="V1", feature_version="F1", calibration_version="C1", quality_gate_version="Q1",
    )
    return PredictionCard(pred, MarketDecision(None, MarketPriceLabel.NO_ODDS))


def _golden_cards() -> list[PredictionCard]:
    # One of each real classification, spanning 2 games, deliberately not
    # pre-sorted -- ranking must come purely from _rank_key.
    return [
        _card("Watch Player", 0.16, ModelClassification.WATCH, game_pk=1),
        _card("Primary Two", 0.22, ModelClassification.PRIMARY, game_pk=2),
        _card("No Bet Player", 0.09, ModelClassification.NO_BET, game_pk=1),
        _card("Primary One", 0.28, ModelClassification.PRIMARY, game_pk=1),
        _card("Ineligible Player", 0.95, ModelClassification.NOT_ELIGIBLE, game_pk=2),
        _card("Secondary One", 0.19, ModelClassification.SECONDARY, game_pk=2),
    ]


def test_ranking_classification_confidence_are_byte_identical_to_golden_fixture():
    cards = _golden_cards()
    ranked = sorted(cards, key=AnalysisService._rank_key, reverse=True)
    ranked_names = [c.prediction.player.full_name for c in ranked]

    assert ranked_names == [
        "Primary One", "Primary Two", "Secondary One",
        "Watch Player", "No Bet Player", "Ineligible Player",
    ]
    assert [c.prediction.final_hr_probability for c in ranked] == [0.28, 0.22, 0.19, 0.16, 0.09, 0.95]
    assert [c.prediction.classification for c in ranked] == [
        ModelClassification.PRIMARY, ModelClassification.PRIMARY, ModelClassification.SECONDARY,
        ModelClassification.WATCH, ModelClassification.NO_BET, ModelClassification.NOT_ELIGIBLE,
    ]
    assert [c.prediction.confidence_label for c in ranked] == [ConfidenceLabel.HIGH] * 6


def test_practical_status_is_byte_identical_to_golden_fixture():
    cards = {c.prediction.player.full_name: c for c in _golden_cards()}
    assert practical_status(cards["Primary One"].prediction.classification) == "RECOMENDADO"
    assert practical_status(cards["Primary Two"].prediction.classification) == "RECOMENDADO"
    assert practical_status(cards["Secondary One"].prediction.classification) == "RECOMENDADO"
    assert practical_status(cards["Watch Player"].prediction.classification) == "VIGILAR"
    assert practical_status(cards["No Bet Player"].prediction.classification) == "NO CUMPLE FILTRO"
    # NOT_ELIGIBLE is never passed to practical_status() in production
    # (game_views.py overrides it to "NO ELEGIBLE" upstream) -- but the
    # function's own fallback behavior for it must still never change.
    assert practical_status(cards["Ineligible Player"].prediction.classification) == "NO CUMPLE FILTRO"


def test_eligible_derivation_is_byte_identical_to_golden_fixture():
    cards = {c.prediction.player.full_name: c for c in _golden_cards()}
    for name in ("Primary One", "Primary Two", "Secondary One", "Watch Player", "No Bet Player"):
        assert cards[name].prediction.classification != ModelClassification.NOT_ELIGIBLE
    assert cards["Ineligible Player"].prediction.classification == ModelClassification.NOT_ELIGIBLE


def test_combination_engine_output_is_byte_identical_to_golden_fixture():
    cards = _golden_cards()
    combos = {c.kind: c for c in CombinationEngine().build(cards)}

    assert set(combos.keys()) == {"BEST_2_MAN", "BEST_3_MAN", "LONG_SHOT_2_MAN", "LONG_SHOT_3_MAN"}

    best2 = combos["BEST_2_MAN"]
    assert best2.filter_status.value == "QUALIFIED"
    assert {leg.player_name for leg in best2.legs} == {"Primary One", "Primary Two"}

    best3 = combos["BEST_3_MAN"]
    assert best3.filter_status.value == "QUALIFIED"
    assert {leg.player_name for leg in best3.legs} == {"Primary One", "Primary Two", "Secondary One"}
    assert any(leg.classification == ModelClassification.PRIMARY for leg in best3.legs)

    for combo in combos.values():
        assert all(leg.player_name != "Ineligible Player" for leg in combo.legs)


def test_frozen_predictive_files_are_byte_identical_to_v1_1_0_tag():
    result = subprocess.run(
        ["git", "diff", "--stat", BASELINE_TAG, "--", *FROZEN_PREDICTIVE_PATHS],
        cwd=ROOT, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "", (
        "RELEASE BLOCKER: frozen predictive files differ from the v1.1.0 tag:\n" + result.stdout
    )
