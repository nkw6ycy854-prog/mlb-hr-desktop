import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from datetime import datetime, timezone

from PySide6.QtWidgets import QApplication, QMessageBox

from mlb_hr.domain.enums import (
    ConfidenceLabel, CriticVerdict, IntegrityStatus, MarketPriceLabel, ModelClassification, ModelHealth,
    SlateQuality, UserActionLabel,
)
from mlb_hr.domain.models import MarketDecision, PlayerRef, Prediction, PredictionCard, ProbabilityDistribution, SlateResult
from mlb_hr.resources_runtime import packaged_migrations_dir
from mlb_hr.services.favorites import FavoritesService
from mlb_hr.storage.sqlite import SQLiteStore
from mlb_hr.ui.today import TodayWidget


def app():
    return QApplication.instance() or QApplication([])


def _card(index, prob, classification=ModelClassification.PRIMARY, game_pk=100):
    player = PlayerRef(index, f"Player {index}")
    pitcher = PlayerRef(9000 + index, "Pitcher")
    dist = ProbabilityDistribution(prob, prob, prob, prob, 0.0, 90.0)
    pred = Prediction(
        prediction_id=f"pred-{index}", snapshot_id="snap", game_pk=game_pk,
        player=player, opposing_pitcher=pitcher, team_name="Yankees", opponent_name="Red Sox",
        game_time=datetime(2026, 8, 30, 23, 0, tzinfo=timezone.utc), final_hr_probability=prob,
        raw_hr_probability=prob, matchup_score=80, grade="B", reliability=90, confidence_score=80,
        confidence_label=ConfidenceLabel.HIGH, distribution=dist, classification=classification,
        user_action=UserActionLabel.RECOMMENDED, integrity=IntegrityStatus.PASS, critic=CriticVerdict.PASS,
        reasons=["Buen matchup"], main_risk=None, warnings=[],
        model_version="V1", feature_version="F1", calibration_version="C1", quality_gate_version="Q1",
    )
    return PredictionCard(pred, MarketDecision(None, MarketPriceLabel.NO_ODDS))


def _store(tmp_path):
    with packaged_migrations_dir() as migrations_dir:
        s = SQLiteStore(tmp_path / "app.db", migrations_dir=migrations_dir)
        s.migrate()
    return s


def _slate(cards):
    return SlateResult(
        cards=cards, combinations=[], slate_quality=SlateQuality.GREEN, model_health=ModelHealth.GREEN,
        confirmed_lineups=8, total_games=12, updated_at=datetime.now(timezone.utc),
    )


def test_dashboard_shows_games_lineups_recommended_and_best_hr():
    app()
    widget = TodayWidget(object(), None)
    cards = [
        _card(0, 0.28, ModelClassification.PRIMARY),
        _card(1, 0.10, ModelClassification.WATCH),
        _card(2, 0.05, ModelClassification.NOT_ELIGIBLE),
    ]
    widget._loaded(_slate(cards))

    assert "12" in widget.dash_games.text()
    assert "8" in widget.dash_lineups.text() and "12" in widget.dash_lineups.text()
    assert "1" in widget.dash_recommended.text()  # only the PRIMARY card
    assert "28.0%" in widget.dash_best_hr.text()


def test_recomendados_filter_only_shows_recomendado_never_vigilar():
    app()
    widget = TodayWidget(object(), None)
    cards = [_card(0, 0.20, ModelClassification.PRIMARY), _card(1, 0.30, ModelClassification.WATCH)]
    widget._loaded(_slate(cards))

    widget.filter_recomendados_btn.click()

    assert widget.table.rowCount() == 1
    assert widget.table.item(0, 0).text() == "Player 0"


def test_recomendados_filter_shows_explicit_empty_state_when_none_exist():
    app()
    widget = TodayWidget(object(), None)
    cards = [_card(0, 0.20, ModelClassification.WATCH)]
    widget._loaded(_slate(cards))

    widget.filter_recomendados_btn.click()

    assert widget.table.rowCount() == 0
    assert widget.empty_state_label.isHidden() is False
    assert "RECOMENDADOS" in widget.empty_state_label.text()


def test_search_finds_a_player_outside_top_15_and_marks_out_of_filter():
    app()
    widget = TodayWidget(object(), None)
    cards = [_card(i, 0.30 - i * 0.01, ModelClassification.PRIMARY) for i in range(16)]
    cards[15].prediction.player.full_name = "Deep Bench Guy"
    widget._loaded(_slate(cards))

    widget.search_box.setText("Deep Bench")

    assert widget.table.rowCount() == 1
    assert "FUERA DEL FILTRO ACTIVO" in widget.table.item(0, 3).text()


def test_search_by_team_name_matches_all_players_on_that_team():
    app()
    widget = TodayWidget(object(), None)
    cards = [_card(0, 0.2), _card(1, 0.1)]
    widget._loaded(_slate(cards))

    widget.search_box.setText("yankees")

    assert widget.table.rowCount() == 2


def test_clearing_search_restores_the_previous_filter():
    app()
    widget = TodayWidget(object(), None)
    cards = [_card(0, 0.20, ModelClassification.PRIMARY), _card(1, 0.30, ModelClassification.WATCH)]
    widget._loaded(_slate(cards))
    widget.filter_recomendados_btn.click()
    assert widget.table.rowCount() == 1

    widget.search_box.setText("Player 1")
    assert widget.table.rowCount() == 1
    widget.search_box.setText("")

    assert widget.table.rowCount() == 1
    assert widget.table.item(0, 0).text() == "Player 0"


def test_favorito_filter_shows_only_saved_players(tmp_path):
    app()
    store = _store(tmp_path)
    widget = TodayWidget(object(), store)
    cards = [_card(0, 0.20), _card(1, 0.15)]
    widget._loaded(_slate(cards))
    widget.favorites_service.save_favorite(
        player_id=0, game_pk=100, player_name="Player 0", team_name="Yankees", opponent_name="Red Sox",
        game_time=cards[0].prediction.game_time, hr_probability=0.20, practical_status="RECOMENDADO",
        classification="PRIMARY", confidence_label="HIGH", eligible=True, best_bookmaker=None,
        best_american_odds=None, fanduel_american_odds=None, source_prediction_id="pred-0",
    )

    widget.filter_favoritos_btn.click()

    assert widget.table.rowCount() == 1
    assert widget.table.item(0, 0).text() == "Player 0"


def test_guardar_pick_saves_a_favorite_and_button_becomes_guardado(tmp_path):
    app()
    store = _store(tmp_path)
    widget = TodayWidget(object(), store)
    widget._loaded(_slate([_card(0, 0.22)]))

    assert widget.favorite_btn.text() == "GUARDAR PICK"
    widget.favorite_btn.click()

    assert widget.favorite_btn.text() == "★ GUARDADO"
    fav = widget.favorites_service.get_favorite(player_id=0, game_pk=100)
    assert fav is not None
    assert fav["snapshot_hr_probability"] == 0.22


def test_eliminar_de_favoritos_asks_confirmation_then_deletes(tmp_path, monkeypatch):
    app()
    store = _store(tmp_path)
    widget = TodayWidget(object(), store)
    widget._loaded(_slate([_card(0, 0.22)]))
    widget.favorite_btn.click()
    assert widget.favorites_service.get_favorite(player_id=0, game_pk=100) is not None

    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    widget.favorite_btn.click()

    assert widget.favorites_service.get_favorite(player_id=0, game_pk=100) is None
    assert widget.favorite_btn.text() == "GUARDAR PICK"


def test_save_remove_save_again_from_the_ui_works(tmp_path, monkeypatch):
    app()
    store = _store(tmp_path)
    widget = TodayWidget(object(), store)
    widget._loaded(_slate([_card(0, 0.22)]))
    widget.favorite_btn.click()
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    widget.favorite_btn.click()

    widget.favorite_btn.click()

    assert widget.favorites_service.get_favorite(player_id=0, game_pk=100) is not None


def test_ver_analisis_completo_toggles_extra_content():
    from PySide6.QtWidgets import QLabel
    app()
    widget = TodayWidget(object(), None)
    card = _card(0, 0.22)
    widget._show_detail(card)

    def detail_texts():
        return "\n".join(l.text() for l in widget.detail.findChildren(QLabel))

    assert widget.analysis_btn.text() == "VER ANÁLISIS COMPLETO"
    assert "ANÁLISIS COMPLETO" not in detail_texts()

    widget.analysis_btn.click()

    assert widget.analysis_btn.text() == "OCULTAR ANÁLISIS COMPLETO"
    assert "ANÁLISIS COMPLETO" in detail_texts()
    assert "V1" in detail_texts()  # model_version, real data, not reinterpreted


def test_new_session_starts_on_todos_filter_with_empty_search():
    app()
    widget = TodayWidget(object(), None)
    assert widget._active_filter == "TODOS"
    assert widget.search_box.text() == ""


def test_loading_a_slate_persists_mlb_feed_status_for_status_center(tmp_path):
    app()
    store = _store(tmp_path)
    widget = TodayWidget(object(), store)
    widget._loaded(_slate([_card(0, 0.2)]))

    status = store.get_state("last_mlb_feed_status")
    assert status is not None
    assert status["quality"] == "GREEN"
