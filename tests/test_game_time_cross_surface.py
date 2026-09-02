import json
from datetime import date, datetime, timezone
from types import SimpleNamespace

from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from mlb_hr.domain.enums import (
    ConfidenceLabel,
    CriticVerdict,
    GameState,
    IntegrityStatus,
    MarketPriceLabel,
    ModelClassification,
    ModelHealth,
    SlateQuality,
    UserActionLabel,
)
from mlb_hr.domain.models import (
    GameContext,
    LineupEntry,
    MarketDecision,
    PlayerRef,
    Prediction,
    PredictionCard,
    ProbabilityDistribution,
    SlateResult,
    TeamLineup,
    VenueRef,
)
from mlb_hr.ui.history import HistoryWidget
from mlb_hr.ui.today import TodayWidget

# A single fixed UTC instant that every surface must render identically as
# "7:15 PM" for the default timezone (America/Santo_Domingo, UTC-4).
GAME_TIME_UTC = datetime(2026, 8, 30, 23, 15, tzinfo=timezone.utc)
EXPECTED_TIME = "7:15 PM"


def app():
    return QApplication.instance() or QApplication([])


class _Store:
    def get_state(self, key, default=None):
        return default  # unset -> exercises the default timezone, not an explicit one

    def connection(self):
        from contextlib import contextmanager

        @contextmanager
        def _cm():
            yield SimpleNamespace(execute=lambda *a, **k: SimpleNamespace(fetchone=lambda: None, fetchall=lambda: []))

        return _cm()


def _card() -> PredictionCard:
    player = PlayerRef(1, "Aaron Judge")
    pitcher = PlayerRef(900, "Pitcher")
    dist = ProbabilityDistribution(0.2, 0.2, 0.2, 0.2, 0.0, 90.0)
    pred = Prediction(
        prediction_id="pred-1", snapshot_id="snap", game_pk=1, player=player, opposing_pitcher=pitcher,
        team_name="Team A", opponent_name="Team B", game_time=GAME_TIME_UTC,
        final_hr_probability=0.2, raw_hr_probability=0.2, matchup_score=80, grade="B", reliability=90,
        confidence_score=80, confidence_label=ConfidenceLabel.HIGH, distribution=dist,
        classification=ModelClassification.PRIMARY, user_action=UserActionLabel.RECOMMENDED,
        integrity=IntegrityStatus.PASS, critic=CriticVerdict.PASS, reasons=[], main_risk=None, warnings=[],
        model_version="V1", feature_version="F1", calibration_version="C1", quality_gate_version="Q1",
    )
    return PredictionCard(pred, MarketDecision(None, MarketPriceLabel.NO_ODDS))


def test_today_ranking_detail_shows_canonical_time():
    app()
    widget = TodayWidget(SimpleNamespace(stake=10.0), _Store())
    widget._show_detail(_card())
    texts = "\n".join(label.text() for label in widget.detail.findChildren(QLabel))
    assert EXPECTED_TIME in texts


def test_today_por_partidos_shows_canonical_time():
    app()
    widget = TodayWidget(SimpleNamespace(stake=10.0), _Store())
    game = GameContext(
        game_pk=1, game_date=date(2026, 8, 30), game_time=GAME_TIME_UTC,
        away_team_id=1, away_team_name="Team A", home_team_id=2, home_team_name="Team B",
        venue=VenueRef(1, "Park"), state=GameState.PREGAME,
        away_lineup=TeamLineup(team_id=1, team_name="Team A", entries=[LineupEntry(PlayerRef(1, "Aaron Judge"), 1)], confirmed=True),
        home_lineup=TeamLineup(team_id=2, team_name="Team B", entries=[], confirmed=True),
        away_starter=PlayerRef(500, "Away SP"), home_starter=PlayerRef(501, "Home SP"),
    )
    card = _card()
    result = SlateResult(
        cards=[card], combinations=[], slate_quality=SlateQuality.GREEN, model_health=ModelHealth.GREEN,
        confirmed_lineups=1, total_games=1, updated_at=datetime.now(timezone.utc), pregame_games=1,
        game_contexts=(game,),
    )
    widget._loaded(result)
    labels = [label.text() for label in widget.games_page.findChildren(QLabel)]
    buttons = [button.text() for button in widget.games_page.findChildren(QPushButton)]
    assert EXPECTED_TIME in "\n".join(labels + buttons)


def test_history_player_row_shows_canonical_time():
    app()

    class _PlayerHistoryStore(_Store):
        def history_prediction_rows(self, limit=2000):
            return [{
                "prediction_id": "p1", "player_name": "Aaron Judge",
                "game_time": GAME_TIME_UTC.isoformat(), "created_at": GAME_TIME_UTC.isoformat(),
                "classification": "PRIMARY", "final_probability": 0.2,
                "reference_stake": 10.0, "odds_at_prediction": 150,
                "actual_hr_binary": None, "pnl_amount": None,
            }]

        def history_combination_rows(self, limit=1000):
            return []

        def prediction_rows_by_ids(self, ids):
            return {}

        def leg_settlements(self, ids):
            return {}

    widget = HistoryWidget(_PlayerHistoryStore())
    assert widget.players_table.item(0, 1).text() == EXPECTED_TIME


def test_history_combination_inicio_shows_canonical_time():
    app()
    legs = [{
        "prediction_id": "p1", "player_id": 1, "player_name": "Aaron Judge",
        "probability": 0.2, "classification": "PRIMARY", "game_pk": 1,
    }]

    class _ComboHistoryStore(_Store):
        def history_prediction_rows(self, limit=2000):
            return []

        def history_combination_rows(self, limit=1000):
            return [{
                "combination_id": "c1", "kind": "BEST_2_MAN", "created_at": GAME_TIME_UTC.isoformat(),
                "legs_json": json.dumps(legs), "filter_status": "QUALIFIED",
                "won": None, "profit_loss": None, "estimated_decimal_odds": 2.5,
            }]

        def prediction_rows_by_ids(self, ids):
            return {"p1": {"game_time": GAME_TIME_UTC.isoformat()}}

        def leg_settlements(self, ids):
            return {"p1": {"actual_hr_binary": None}}

    widget = HistoryWidget(_ComboHistoryStore())
    assert widget.combinations_table.item(0, 1).text() == EXPECTED_TIME
