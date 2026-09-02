import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import date, datetime, timezone

from PySide6.QtWidgets import QApplication

from mlb_hr.domain.enums import (
    CombinationFilterStatus, ConfidenceLabel, CriticVerdict, GameState, IntegrityStatus,
    MarketPriceLabel, ModelClassification, ModelHealth, SlateQuality, UserActionLabel,
)
from mlb_hr.domain.models import (
    Combination, CombinationLeg, GameContext, LineupEntry, MarketDecision, PlayerRef,
    Prediction, PredictionCard, ProbabilityDistribution, SlateResult, TeamLineup, VenueRef,
)
from mlb_hr.ui.combinations_page import CombinationsPageWidget
from mlb_hr.ui.games_page import GamesPageWidget
from mlb_hr.ui.status_center import StatusCenterPanel
from mlb_hr.services.status_center import StatusCenterReport, StatusItem
from mlb_hr.ui.style import APP_STYLESHEET

_SIZES = [(1400, 900), (1180, 760), (820, 700), (760, 640)]


def app():
    a = QApplication.instance() or QApplication([])
    a.setStyleSheet(APP_STYLESHEET)
    return a


def _card(pid, name, prob, game_pk=1):
    player = PlayerRef(pid, name)
    pitcher = PlayerRef(9000 + pid, "Pitcher")
    dist = ProbabilityDistribution(prob, prob, prob, prob, 0.0, 90.0)
    pred = Prediction(
        prediction_id=f"pred-{pid}", snapshot_id="snap", game_pk=game_pk, player=player,
        opposing_pitcher=pitcher, team_name="Yankees", opponent_name="Red Sox",
        game_time=datetime(2026, 8, 30, 23, 0, tzinfo=timezone.utc), final_hr_probability=prob,
        raw_hr_probability=prob, matchup_score=80, grade="B", reliability=90, confidence_score=80,
        confidence_label=ConfidenceLabel.HIGH, distribution=dist, classification=ModelClassification.PRIMARY,
        user_action=UserActionLabel.RECOMMENDED, integrity=IntegrityStatus.PASS, critic=CriticVerdict.PASS,
        reasons=["Buen matchup"], main_risk=None, warnings=[],
        model_version="V1", feature_version="F1", calibration_version="C1", quality_gate_version="Q1",
    )
    return PredictionCard(pred, MarketDecision(None, MarketPriceLabel.NO_ODDS))


def test_games_page_survives_all_four_breakpoints():
    app()
    widget = GamesPageWidget(None)
    game = GameContext(
        game_pk=1, game_date=date(2026, 8, 30), game_time=datetime(2026, 8, 30, 23, 0, tzinfo=timezone.utc),
        away_team_id=1, away_team_name="Yankees", home_team_id=2, home_team_name="Red Sox",
        venue=VenueRef(1, "Park"), state=GameState.PREGAME,
        away_lineup=TeamLineup(1, "Yankees", [LineupEntry(PlayerRef(1, "A"), 1)], confirmed=True),
        home_lineup=TeamLineup(2, "Red Sox", [], confirmed=True),
        away_starter=PlayerRef(500, "SP"), home_starter=PlayerRef(501, "SP"),
    )
    result = SlateResult(
        cards=[_card(1, "A", 0.2)], combinations=[], slate_quality=SlateQuality.GREEN,
        model_health=ModelHealth.GREEN, confirmed_lineups=1, total_games=1,
        updated_at=datetime.now(timezone.utc), game_contexts=(game,),
    )
    widget.render(result)
    widget.show()
    for w, h in _SIZES:
        widget.resize(w, h)
        app().processEvents()
        assert widget.width() <= w + 5


def test_combinations_page_survives_all_four_breakpoints():
    app()
    widget = CombinationsPageWidget(object())
    legs = [CombinationLeg("pred-1", 1, "A", 0.2, ModelClassification.PRIMARY, 1),
            CombinationLeg("pred-2", 2, "B", 0.18, ModelClassification.SECONDARY, 1)]
    combo = Combination("combo-1", "BEST_2_MAN", legs, 0.05, 80.0, CombinationFilterStatus.QUALIFIED, None, 3.2, [])
    result = SlateResult(
        cards=[_card(1, "A", 0.2), _card(2, "B", 0.18)], combinations=[combo],
        slate_quality=SlateQuality.GREEN, model_health=ModelHealth.GREEN, confirmed_lineups=1,
        total_games=1, updated_at=datetime.now(timezone.utc),
    )
    widget.render(result)
    widget.show()
    for w, h in _SIZES:
        widget.resize(w, h)
        app().processEvents()
        assert widget.width() <= w + 5


def test_status_center_panel_survives_all_four_breakpoints():
    app()
    panel = StatusCenterPanel()
    report = StatusCenterReport(
        items=tuple(StatusItem(k, k, "OK", "detalle") for k in
                    ("model", "statcast", "mlb_feed", "database", "odds", "last_settlement", "selftest")),
        global_state="SISTEMA OK",
    )
    panel.render(report)
    panel.show()
    for w, h in _SIZES:
        panel.resize(w, h)
        app().processEvents()
        assert panel.width() <= w + 5
