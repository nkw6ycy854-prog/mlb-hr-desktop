from datetime import date, datetime, timezone

from mlb_hr.domain.enums import (
    ConfidenceLabel,
    CriticVerdict,
    GameState,
    IntegrityStatus,
    MarketPriceLabel,
    ModelClassification,
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
from mlb_hr.services.game_views import GamePredictionViewBuilder


def _player(player_id: int, name: str) -> PlayerRef:
    return PlayerRef(player_id, name)


def _entry(player_id: int, name: str, order: int) -> LineupEntry:
    return LineupEntry(player=_player(player_id, name), batting_order=order)


def _prediction(player_id: int, name: str, game_pk: int, prob: float, classification) -> Prediction:
    dist = ProbabilityDistribution(prob, prob, prob, prob, 0.0, 90.0)
    return Prediction(
        prediction_id=f"pred-{player_id}", snapshot_id="snap", game_pk=game_pk,
        player=_player(player_id, name), opposing_pitcher=_player(9000 + player_id, "Pitcher"),
        team_name="TEAM", opponent_name="OPP", game_time=None,
        final_hr_probability=prob, raw_hr_probability=prob, matchup_score=80, grade="B",
        reliability=90, confidence_score=80, confidence_label=ConfidenceLabel.HIGH,
        distribution=dist, classification=classification, user_action=UserActionLabel.RECOMMENDED,
        integrity=IntegrityStatus.PASS, critic=CriticVerdict.PASS, reasons=[], main_risk=None, warnings=[],
        model_version="V1", feature_version="F1", calibration_version="C1", quality_gate_version="Q1",
    )


def _card(player_id: int, name: str, game_pk: int, prob: float, classification) -> PredictionCard:
    pred = _prediction(player_id, name, game_pk, prob, classification)
    return PredictionCard(pred, MarketDecision(None, MarketPriceLabel.NO_ODDS))


def _game(
    game_pk: int, *, away_confirmed: bool, home_confirmed: bool,
    away_entries=(), home_entries=(), state=GameState.PREGAME,
    game_time=datetime(2026, 8, 30, 23, 15, tzinfo=timezone.utc),
) -> GameContext:
    return GameContext(
        game_pk=game_pk, game_date=date(2026, 8, 30), game_time=game_time,
        away_team_id=1, away_team_name="AWAY", home_team_id=2, home_team_name="HOME",
        venue=VenueRef(1, "Park"), state=state,
        away_lineup=TeamLineup(team_id=1, team_name="AWAY", entries=list(away_entries), confirmed=away_confirmed),
        home_lineup=TeamLineup(team_id=2, team_name="HOME", entries=list(home_entries), confirmed=home_confirmed),
        away_starter=_player(500, "Away SP"), home_starter=_player(501, "Home SP"),
    )


def test_players_within_a_team_sort_by_real_batting_order_not_hr_probability():
    # V1.2.0 POR PARTIDOS requirement: real batting order 1-9, not HR% rank.
    # Entry order here is deliberately NOT HR%-descending, to prove the sort
    # key changed -- if this still sorted by HR%, "High" would come first.
    game = _game(
        1, away_confirmed=True, home_confirmed=True,
        away_entries=[_entry(1, "Low", 1), _entry(2, "High", 2), _entry(3, "Mid", 3)],
    )
    cards = [
        _card(1, "Low", 1, 0.05, ModelClassification.WATCH),
        _card(2, "High", 1, 0.20, ModelClassification.PRIMARY),
        _card(3, "Mid", 1, 0.10, ModelClassification.SECONDARY),
    ]
    slate = SlateResult([], [], None, None, 1, 1, datetime.now(timezone.utc), game_contexts=(game,))
    slate.cards = cards

    views = GamePredictionViewBuilder().build(slate, "America/Santo_Domingo")

    names = [p.player_name for p in views[0].away.players]
    assert names == ["Low", "High", "Mid"]
    orders = [p.batting_order for p in views[0].away.players]
    assert orders == [1, 2, 3]
    # Reordering must never touch the underlying predictive values.
    by_name = {p.player_name: p for p in views[0].away.players}
    assert by_name["High"].hr_probability == 0.20
    assert by_name["High"].classification == "PRIMARY"
    assert by_name["Low"].hr_probability == 0.05
    assert by_name["Mid"].classification == "SECONDARY"


def test_ineligible_player_with_an_early_batting_order_is_not_pushed_to_the_bottom():
    game = _game(
        1, away_confirmed=True, home_confirmed=True,
        away_entries=[_entry(1, "IneligibleLeadoff", 1), _entry(2, "Eligible", 2)],
    )
    cards = [
        _card(1, "IneligibleLeadoff", 1, 0.03, ModelClassification.NOT_ELIGIBLE),
        _card(2, "Eligible", 1, 0.20, ModelClassification.PRIMARY),
    ]
    slate = SlateResult([], [], None, None, 1, 1, datetime.now(timezone.utc), game_contexts=(game,))
    slate.cards = cards

    views = GamePredictionViewBuilder().build(slate, "America/Santo_Domingo")

    names = [p.player_name for p in views[0].away.players]
    assert names == ["IneligibleLeadoff", "Eligible"]


def test_game_with_only_one_lineup_confirmed_is_not_ready():
    game = _game(1, away_confirmed=True, home_confirmed=False)
    slate = SlateResult([], [], None, None, 0, 1, datetime.now(timezone.utc), game_contexts=(game,))

    views = GamePredictionViewBuilder().build(slate, "America/Santo_Domingo")

    assert views[0].ready is False
    assert "ESPERANDO LINEUP" in views[0].empty_message


def test_not_eligible_player_stays_visible_at_bottom_without_a_fabricated_probability():
    game = _game(
        1, away_confirmed=True, home_confirmed=True,
        away_entries=[_entry(1, "Eligible", 1), _entry(2, "Ineligible", 2)],
    )
    cards = [
        _card(1, "Eligible", 1, 0.20, ModelClassification.PRIMARY),
        _card(2, "Ineligible", 1, 0.03, ModelClassification.NOT_ELIGIBLE),
    ]
    slate = SlateResult([], [], None, None, 1, 1, datetime.now(timezone.utc), game_contexts=(game,))
    slate.cards = cards

    views = GamePredictionViewBuilder().build(slate, "America/Santo_Domingo")

    players = views[0].away.players
    assert [p.player_name for p in players] == ["Eligible", "Ineligible"]
    assert players[1].eligible is False
    assert players[1].hr_probability is None


def test_lineup_entry_with_no_card_at_all_never_fabricates_a_probability():
    # Entry present in a confirmed lineup but never produced any card (e.g. it
    # failed the pre-model integrity check). Must still be visible, marked
    # ineligible, with no invented probability.
    game = _game(
        1, away_confirmed=True, home_confirmed=True,
        away_entries=[_entry(1, "NoCard", 1)],
    )
    slate = SlateResult([], [], None, None, 1, 1, datetime.now(timezone.utc), game_contexts=(game,))
    slate.cards = []

    views = GamePredictionViewBuilder().build(slate, "America/Santo_Domingo")

    player = views[0].away.players[0]
    assert player.eligible is False
    assert player.hr_probability is None
    assert player.card is None


def test_live_game_is_not_ready_and_reports_pregame_predictions_closed():
    game = _game(1, away_confirmed=True, home_confirmed=True, state=GameState.LIVE)
    slate = SlateResult([], [], None, None, 1, 1, datetime.now(timezone.utc), game_contexts=(game,))

    views = GamePredictionViewBuilder().build(slate, "America/Santo_Domingo")

    assert views[0].ready is False
    assert views[0].game_state == "LIVE"
    assert views[0].empty_message is not None


def test_final_game_is_not_ready_and_reports_pregame_predictions_closed():
    game = _game(1, away_confirmed=True, home_confirmed=True, state=GameState.FINAL)
    slate = SlateResult([], [], None, None, 1, 1, datetime.now(timezone.utc), game_contexts=(game,))

    views = GamePredictionViewBuilder().build(slate, "America/Santo_Domingo")

    assert views[0].ready is False
    assert views[0].game_state == "FINAL"
    assert views[0].empty_message is not None


def test_pregame_game_with_both_lineups_confirmed_is_ready_with_no_empty_message():
    game = _game(
        1, away_confirmed=True, home_confirmed=True,
        away_entries=[_entry(1, "A", 1)], home_entries=[_entry(2, "B", 1)],
    )
    cards = [_card(1, "A", 1, 0.2, ModelClassification.PRIMARY), _card(2, "B", 1, 0.1, ModelClassification.WATCH)]
    slate = SlateResult([], [], None, None, 1, 1, datetime.now(timezone.utc), game_contexts=(game,))
    slate.cards = cards

    views = GamePredictionViewBuilder().build(slate, "America/Santo_Domingo")

    assert views[0].ready is True
    assert views[0].empty_message is None


def test_build_never_mutates_slate_cards():
    game = _game(
        1, away_confirmed=True, home_confirmed=True,
        away_entries=[_entry(1, "A", 1)],
    )
    cards = [_card(1, "A", 1, 0.2, ModelClassification.PRIMARY)]
    slate = SlateResult([], [], None, None, 1, 1, datetime.now(timezone.utc), game_contexts=(game,))
    slate.cards = cards
    original = list(cards)

    GamePredictionViewBuilder().build(slate, "America/Santo_Domingo")

    assert cards == original
