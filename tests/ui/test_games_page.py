import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import date, datetime, timezone

from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from mlb_hr.domain.enums import (
    ConfidenceLabel, CriticVerdict, GameState, IntegrityStatus, MarketPriceLabel, ModelClassification,
    ModelHealth, SlateQuality, UserActionLabel,
)
from mlb_hr.domain.models import (
    GameContext, LineupEntry, MarketDecision, PlayerRef, Prediction, PredictionCard,
    ProbabilityDistribution, SlateResult, TeamLineup, VenueRef,
)
from mlb_hr.ui.games_page import GamesPageWidget


def app():
    return QApplication.instance() or QApplication([])


def _entry(player_id, name, order):
    return LineupEntry(player=PlayerRef(player_id, name), batting_order=order)


def _card(player_id, name, game_pk, prob, classification=ModelClassification.PRIMARY):
    player = PlayerRef(player_id, name)
    pitcher = PlayerRef(9000 + player_id, "Pitcher")
    dist = ProbabilityDistribution(prob, prob, prob, prob, 0.0, 90.0)
    pred = Prediction(
        prediction_id=f"pred-{player_id}", snapshot_id="snap", game_pk=game_pk,
        player=player, opposing_pitcher=pitcher, team_name="Team A", opponent_name="Team B",
        game_time=datetime(2026, 8, 30, 23, 15, tzinfo=timezone.utc), final_hr_probability=prob,
        raw_hr_probability=prob, matchup_score=80, grade="B", reliability=90, confidence_score=80,
        confidence_label=ConfidenceLabel.HIGH, distribution=dist, classification=classification,
        user_action=UserActionLabel.RECOMMENDED, integrity=IntegrityStatus.PASS, critic=CriticVerdict.PASS,
        reasons=["Buen matchup"], main_risk=None, warnings=[],
        model_version="V1", feature_version="F1", calibration_version="C1", quality_gate_version="Q1",
    )
    return PredictionCard(pred, MarketDecision(None, MarketPriceLabel.NO_ODDS))


def _game(game_pk, *, away_confirmed=True, home_confirmed=True, away_entries=(), home_entries=(), state=GameState.PREGAME):
    return GameContext(
        game_pk=game_pk, game_date=date(2026, 8, 30), game_time=datetime(2026, 8, 30, 23, 15, tzinfo=timezone.utc),
        away_team_id=1, away_team_name="Team A", home_team_id=2, home_team_name="Team B",
        venue=VenueRef(1, "Park"), state=state,
        away_lineup=TeamLineup(team_id=1, team_name="Team A", entries=list(away_entries), confirmed=away_confirmed),
        home_lineup=TeamLineup(team_id=2, team_name="Team B", entries=list(home_entries), confirmed=home_confirmed),
        away_starter=PlayerRef(500, "Away SP"), home_starter=PlayerRef(501, "Home SP"),
    )


def _slate(game_contexts, cards):
    return SlateResult(
        cards=cards, combinations=[], slate_quality=SlateQuality.GREEN, model_health=ModelHealth.GREEN,
        confirmed_lineups=0, total_games=len(game_contexts), updated_at=datetime.now(timezone.utc),
        game_contexts=tuple(game_contexts),
    )


def test_cards_are_all_collapsed_by_default():
    app()
    widget = GamesPageWidget(None)
    game = _game(1, away_entries=[_entry(1, "A", 1)], home_entries=[_entry(2, "B", 1)])
    widget.render(_slate([game], [_card(1, "A", 1, 0.2), _card(2, "B", 1, 0.1)]))

    assert len(widget._cards) == 1
    assert widget._cards[0].is_expanded is False


def test_clicking_the_header_expands_the_card():
    app()
    widget = GamesPageWidget(None)
    game = _game(1, away_entries=[_entry(1, "A", 1)], home_entries=[_entry(2, "B", 1)])
    widget.render(_slate([game], [_card(1, "A", 1, 0.2), _card(2, "B", 1, 0.1)]))

    widget._cards[0].header_btn.click()

    assert widget._cards[0].is_expanded is True
    assert widget._cards[0].body.isHidden() is False


def test_confirmado_status_when_both_lineups_confirmed():
    app()
    widget = GamesPageWidget(None)
    game = _game(1, away_confirmed=True, home_confirmed=True)
    widget.render(_slate([game], []))

    assert widget._cards[0].lineup_status == "CONFIRMADO"


def test_parcial_status_when_only_one_lineup_confirmed():
    app()
    widget = GamesPageWidget(None)
    game = _game(1, away_confirmed=True, home_confirmed=False)
    widget.render(_slate([game], []))

    assert widget._cards[0].lineup_status == "PARCIAL"


def test_no_confirmado_status_when_neither_lineup_confirmed():
    app()
    widget = GamesPageWidget(None)
    game = _game(1, away_confirmed=False, home_confirmed=False)
    widget.render(_slate([game], []))

    assert widget._cards[0].lineup_status == "NO CONFIRMADO"


def test_header_shows_ge5_and_recomendados_counts():
    app()
    widget = GamesPageWidget(None)
    game = _game(1, away_entries=[_entry(1, "A", 1), _entry(2, "B", 2)], home_entries=[_entry(3, "C", 1)])
    cards = [
        _card(1, "A", 1, 0.20, ModelClassification.PRIMARY),  # >=5%, RECOMENDADO
        _card(2, "B", 1, 0.02, ModelClassification.NO_BET),   # <5%, ALTO RIESGO
        _card(3, "C", 1, 0.10, ModelClassification.WATCH),    # >=5%, VIGILAR
    ]
    widget.render(_slate([game], cards))

    header_text = widget._cards[0].header_btn.text()
    assert "≥5%: 2" in header_text
    assert "RECOMENDADOS: 1" in header_text


def test_expanded_view_shows_both_teams_in_real_batting_order():
    app()
    widget = GamesPageWidget(None)
    game = _game(
        1,
        away_entries=[_entry(1, "Leadoff", 1), _entry(2, "Cleanup", 4)],
        home_entries=[_entry(3, "HomeGuy", 1)],
    )
    cards = [_card(1, "Leadoff", 1, 0.10), _card(2, "Cleanup", 1, 0.25), _card(3, "HomeGuy", 1, 0.15)]
    widget.render(_slate([game], cards))
    widget._cards[0].header_btn.click()

    labels = [l.text() for l in widget._cards[0].body.findChildren(QLabel)]
    buttons = [b.text() for b in widget._cards[0].body.findChildren(QPushButton)]
    texts = "\n".join(labels + buttons)
    assert texts.index("Leadoff") < texts.index("Cleanup")
    assert "HomeGuy" in texts


def test_expandir_recomendados_opens_only_games_with_at_least_one_recomendado():
    app()
    widget = GamesPageWidget(None)
    game_with = _game(1, away_entries=[_entry(1, "Good", 1)])
    game_without = _game(2, away_entries=[_entry(2, "Bad", 1)])
    cards = [_card(1, "Good", 1, 0.2, ModelClassification.PRIMARY), _card(2, "Bad", 2, 0.1, ModelClassification.WATCH)]
    widget.render(_slate([game_with, game_without], cards))

    widget.expand_recommended()

    assert widget._cards[0].is_expanded is True
    assert widget._cards[1].is_expanded is False


def test_colapsar_todos_closes_every_card():
    app()
    widget = GamesPageWidget(None)
    game = _game(1)
    widget.render(_slate([game], []))
    widget._cards[0].toggle()
    assert widget._cards[0].is_expanded is True

    widget.collapse_all()

    assert widget._cards[0].is_expanded is False


def test_game_order_is_preserved_exactly_as_in_slate():
    app()
    widget = GamesPageWidget(None)
    g1, g2, g3 = _game(3), _game(1), _game(2)
    widget.render(_slate([g1, g2, g3], []))

    assert [c.game_pk for c in widget._cards] == [3, 1, 2]


def test_clicking_a_player_opens_the_shared_detail_panel():
    app()
    widget = GamesPageWidget(None)
    game = _game(1, away_entries=[_entry(1, "A", 1)])
    widget.render(_slate([game], [_card(1, "A", 1, 0.2)]))
    widget._cards[0].header_btn.click()

    player_btn = next(b for b in widget._cards[0].body.findChildren(QPushButton) if "A" in b.text())
    player_btn.click()

    assert widget.detail_panel.isHidden() is False
    assert "A" in widget.detail_panel.title_label.text()
