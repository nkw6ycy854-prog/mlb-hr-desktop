from datetime import datetime, timezone
from types import SimpleNamespace

from PySide6.QtWidgets import QApplication

from mlb_hr.domain.enums import (
    ConfidenceLabel,
    CriticVerdict,
    IntegrityStatus,
    MarketPriceLabel,
    ModelClassification,
    ModelHealth,
    SlateQuality,
    UserActionLabel,
)
from mlb_hr.domain.models import (
    MarketDecision,
    PlayerRef,
    Prediction,
    PredictionCard,
    ProbabilityDistribution,
    SlateResult,
)
from mlb_hr.ui.today import TodayWidget


def app():
    return QApplication.instance() or QApplication([])


def _make_card(index: int, probability: float) -> PredictionCard:
    player = PlayerRef(player_id=index, full_name=f"Player {index}")
    pitcher = PlayerRef(player_id=9000 + index, full_name="Opposing Pitcher")
    distribution = ProbabilityDistribution(
        point=probability, p10=probability, p50=probability, p90=probability,
        interval_width=0.0, stability_score=1.0,
    )
    prediction = Prediction(
        prediction_id=f"pred-{index}",
        snapshot_id="snap-1",
        game_pk=100 + index,
        player=player,
        opposing_pitcher=pitcher,
        team_name="Team A",
        opponent_name="Team B",
        game_time=datetime(2026, 8, 26, 19, 5, tzinfo=timezone.utc),
        final_hr_probability=probability,
        raw_hr_probability=probability,
        matchup_score=0.5,
        grade="B",
        reliability=0.9,
        confidence_score=0.8,
        confidence_label=ConfidenceLabel.HIGH,
        distribution=distribution,
        classification=ModelClassification.PRIMARY,
        user_action=UserActionLabel.RECOMMENDED,
        integrity=IntegrityStatus.PASS,
        critic=CriticVerdict.PASS,
        reasons=["Strong matchup"],
        main_risk=None,
        warnings=[],
        model_version="V1.0.0",
        feature_version="1",
        calibration_version="1",
        quality_gate_version="1",
        model_health=ModelHealth.GREEN,
    )
    market = MarketDecision(quote=None, label=MarketPriceLabel.NO_ODDS)
    return PredictionCard(prediction=prediction, market=market)


def _make_service():
    return SimpleNamespace(stake=10.0)


def test_today_defaults_to_top_15_and_can_expand():
    app()
    widget = TodayWidget(_make_service(), None)
    cards = [_make_card(i, 1 - i / 100) for i in range(20)]
    result = SlateResult(
        cards=cards,
        combinations=[],
        slate_quality=SlateQuality.GREEN,
        model_health=ModelHealth.GREEN,
        confirmed_lineups=15,
        total_games=15,
        updated_at=datetime.now(timezone.utc),
    )
    widget._loaded(result)

    assert widget.table.rowCount() == 15
    assert widget.view_all_btn.text() == "VER TODOS"
    widget.toggle_all()
    assert widget.table.rowCount() == 20
    assert widget.view_all_btn.text() == "VER TOP 15"
    assert widget.table.horizontalHeaderItem(7).text() == "Estado"
