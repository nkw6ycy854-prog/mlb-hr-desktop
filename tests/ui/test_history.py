from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import json

from PySide6.QtCore import QThreadPool, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from mlb_hr.services.game_time import GameTimeService
from mlb_hr.services.history import HistoryFilter
from mlb_hr.services.settlement_coordinator import SettlementRunResult
from mlb_hr.ui.history import HistoryWidget


def _pump(timeout_ms=2000):
    QThreadPool.globalInstance().waitForDone(timeout_ms)
    QTest.qWait(50)


def app():
    return QApplication.instance() or QApplication([])


class _FakeStore:
    def history_prediction_rows(self, limit=2000):
        return []

    def history_combination_rows(self, limit=1000):
        return []

    def prediction_rows_by_ids(self, ids):
        return {}

    def leg_settlements(self, ids):
        return {}

    def get_state(self, key, default=None):
        return default


def _widget() -> HistoryWidget:
    app()
    return HistoryWidget(_FakeStore())


def test_history_defaults_to_jugadores_view():
    widget = _widget()
    assert widget.mode_stack.currentIndex() == 0


def test_empty_jugadores_history_shows_explanation_not_just_a_blank_table():
    widget = _widget()  # _FakeStore returns [] for both prediction/combination rows

    assert widget.players_table.rowCount() == 0
    assert widget.empty_state_label.isHidden() is False
    assert widget.empty_state_label.text().strip() != ""


def test_empty_combinaciones_history_shows_explanation_not_just_a_blank_table():
    widget = _widget()

    widget.combinations_btn.click()

    assert widget.combinations_table.rowCount() == 0
    assert widget.empty_state_label.isHidden() is False
    assert widget.empty_state_label.text().strip() != ""


def test_empty_state_label_hides_once_jugadores_has_rows():
    widget = HistoryWidget(_tz_store())

    assert widget.players_table.rowCount() == 1
    assert widget.empty_state_label.isHidden() is True


def test_clicking_combinaciones_switches_stack():
    widget = _widget()
    QTest.mouseClick(widget.combinations_btn, Qt.MouseButton.LeftButton)
    assert widget.mode_stack.currentIndex() == 1


def test_selecting_filters_builds_expected_history_filter():
    widget = _widget()
    QTest.mouseClick(widget.period_buttons["30D"], Qt.MouseButton.LeftButton)
    widget.status_combo.setCurrentIndex(widget.status_combo.findData("RECOMMENDED"))
    widget.result_combo.setCurrentIndex(widget.result_combo.findData("HR"))

    assert widget.current_filter() == HistoryFilter(period="30D", status="RECOMMENDED", result="HR")


def test_player_table_headers_match_spec():
    widget = _widget()
    headers = [widget.players_table.horizontalHeaderItem(i).text() for i in range(widget.players_table.columnCount())]
    assert headers == ["Fecha", "Hora", "Jugador", "HR%", "Estado", "Cuota", "Resultado"]


def test_combination_table_headers_match_spec():
    widget = _widget()
    headers = [widget.combinations_table.horizontalHeaderItem(i).text() for i in range(widget.combinations_table.columnCount())]
    assert headers == ["Fecha", "Inicio", "Tipo", "Selecciones", "Filtro", "Cuota", "Resultado", "P/L"]


def _tz_store(timezone_name="America/Santo_Domingo"):
    game_time_p1 = datetime(2026, 8, 26, 23, 5, tzinfo=timezone.utc).isoformat()
    game_time_p2 = datetime(2026, 8, 26, 22, 40, tzinfo=timezone.utc).isoformat()
    created_at = datetime(2026, 8, 26, 20, 0, tzinfo=timezone.utc).isoformat()

    player_row = {
        "prediction_id": "p1", "player_name": "Aaron Judge",
        "game_time": game_time_p1, "created_at": created_at,
        "classification": "PRIMARY", "final_probability": 0.3,
        "reference_stake": 10.0, "odds_at_prediction": 150,
        "actual_hr_binary": None, "pnl_amount": None,
    }
    legs = [
        {"prediction_id": "p1", "player_id": 1, "player_name": "Aaron Judge", "probability": .3, "classification": "PRIMARY", "game_pk": 1},
        {"prediction_id": "p2", "player_id": 2, "player_name": "Juan Soto", "probability": .28, "classification": "SECONDARY", "game_pk": 2},
    ]
    combo_row = {
        "combination_id": "c1", "kind": "BEST_2_MAN", "created_at": created_at,
        "legs_json": json.dumps(legs), "filter_status": "QUALIFIED",
        "won": 1, "profit_loss": 25.0, "estimated_decimal_odds": 2.5,
    }
    prediction_rows = {"p1": {"game_time": game_time_p1}, "p2": {"game_time": game_time_p2}}
    leg_settlement_rows = {"p1": {"actual_hr_binary": 1}, "p2": {"actual_hr_binary": None}}

    class _TzStore:
        def __init__(self):
            self.timezone_name = timezone_name

        def history_prediction_rows(self, limit=2000):
            return [player_row]

        def history_combination_rows(self, limit=1000):
            return [combo_row]

        def prediction_rows_by_ids(self, ids):
            return {k: v for k, v in prediction_rows.items() if k in ids}

        def leg_settlements(self, ids):
            return {k: v for k, v in leg_settlement_rows.items() if k in ids}

        def get_state(self, key, default=None):
            return self.timezone_name if key == "timezone_name" else default

    return _TzStore()


def test_player_row_shows_game_time_in_configured_timezone():
    app()
    widget = HistoryWidget(_tz_store())
    time_item = widget.players_table.item(0, 1)
    assert time_item.text() == "7:05 PM"


def test_combination_inicio_uses_earliest_leg_game_time_in_configured_timezone():
    app()
    widget = HistoryWidget(_tz_store())
    start_item = widget.combinations_table.item(0, 1)
    assert start_item.text() == "6:40 PM"


def test_selecting_player_row_shows_original_prediction_classification_odds_result():
    app()
    widget = HistoryWidget(_tz_store())
    widget._select_player_row(0, 0)
    texts = "\n".join(label.text() for label in widget.detail.findChildren(QLabel))
    assert "30.0%" in texts
    assert "PRIMARY" in texts
    assert "+150" in texts
    assert "PENDIENTE" in texts


def test_player_table_and_detail_use_hr_no_hr_pendiente_vocabulary():
    app()
    widget = HistoryWidget(_tz_store())
    result_item = widget.players_table.item(0, 6)
    assert result_item.text() == "PENDIENTE"


def test_combination_table_result_column_uses_ganada_not_hr():
    app()
    widget = HistoryWidget(_tz_store())
    result_item = widget.combinations_table.item(0, 6)
    assert result_item.text() == "GANADA"
    assert result_item.text() not in {"HR", "NO_HR", "NO HR"}


def test_selecting_combination_row_shows_each_leg_with_individual_time_and_result():
    app()
    widget = HistoryWidget(_tz_store())
    widget.set_mode(1)
    widget._select_combination_row(0, 0)
    texts = "\n".join(label.text() for label in widget.detail.findChildren(QLabel))
    assert "Aaron Judge" in texts and "7:05 PM" in texts
    assert "Juan Soto" in texts and "6:40 PM" in texts
    # Combo-level result is GANADA, but each leg keeps its own HR/NO HR/PENDIENTE outcome.
    assert "Aaron Judge · PRIMARY · HR · 7:05 PM" in texts
    assert "Juan Soto · SECONDARY · PENDIENTE · 6:40 PM" in texts
    assert "GANADA" in texts
    assert "Resultado: GANADA" in texts


def test_result_filter_labels_switch_to_ganada_perdida_pendiente_in_combinations_mode():
    app()
    widget = HistoryWidget(_tz_store())
    widget.set_mode(1)
    labels = [widget.result_combo.itemText(i) for i in range(widget.result_combo.count())]
    assert labels == ["Todos", "Ganada", "Perdida", "Pendiente"]
    # Underlying filter codes stay the same regardless of the visible label.
    widget.result_combo.setCurrentIndex(widget.result_combo.findData("HR"))
    assert widget.current_filter().result == "HR"


def test_result_filter_labels_stay_hr_no_hr_pendiente_in_players_mode():
    app()
    widget = HistoryWidget(_tz_store())
    labels = [widget.result_combo.itemText(i) for i in range(widget.result_combo.count())]
    assert labels == ["Todos", "HR", "No HR", "Pendiente"]


def test_history_defaults_to_santo_domingo_when_timezone_not_persisted():
    # Matches GameTimeService.DEFAULT_TIMEZONE and TodayWidget's default, so an
    # app that never touched Ajustes shows the same hour on every screen.
    app()
    widget = HistoryWidget(_tz_store(timezone_name=None))
    time_item = widget.players_table.item(0, 1)
    assert time_item.text() == "7:05 PM"


def test_history_refresh_picks_up_a_persisted_timezone_change():
    app()
    store = _tz_store()
    widget = HistoryWidget(store)
    assert widget.players_table.item(0, 1).text() == "7:05 PM"

    store.timezone_name = "UTC"
    widget.refresh()

    assert widget.players_table.item(0, 1).text() == "11:05 PM"


def _hits_today_texts(widget) -> str:
    labels = [label.text() for label in widget.hits_today_page.findChildren(QLabel)]
    buttons = [button.text() for button in widget.hits_today_page.findChildren(QPushButton)]
    return "\n".join(labels + buttons)


def _hits_today_store():
    # Anchored to local noon (not a `datetime.now()`-relative offset) so the
    # fixture's calendar day always matches HistoryWidget.refresh()'s own
    # `now()`-derived local_date, regardless of what wall-clock hour the
    # test happens to run at (near the UTC/local day boundary, an offset
    # anchor could round game_time into a different local calendar day).
    zone = ZoneInfo("America/Santo_Domingo")
    local_today = GameTimeService("America/Santo_Domingo").localize(datetime.now(timezone.utc)).date()
    game_time = datetime.combine(local_today, datetime.min.time().replace(hour=12), tzinfo=zone).astimezone(timezone.utc)
    created_at = game_time - timedelta(hours=2)

    player_rows = [
        {
            "prediction_id": "hit1", "player_name": "Aaron Judge",
            "game_time": game_time.isoformat(), "created_at": created_at.isoformat(),
            "classification": "PRIMARY", "final_probability": 0.20,
            "reference_stake": 10.0, "odds_at_prediction": 150,
            "actual_hr_binary": 1, "pnl_amount": 25.0,
            "game_pk": 1, "team_name": "Yankees", "opponent_name": "Red Sox",
        },
        {
            "prediction_id": "hit2", "player_name": "Juan Soto",
            "game_time": game_time.isoformat(), "created_at": created_at.isoformat(),
            "classification": "SECONDARY", "final_probability": 0.15,
            "reference_stake": 10.0, "odds_at_prediction": 130,
            "actual_hr_binary": 1, "pnl_amount": 18.0,
            "game_pk": 2, "team_name": "Mets", "opponent_name": "Braves",
        },
        {
            "prediction_id": "miss1", "player_name": "Player Miss",
            "game_time": game_time.isoformat(), "created_at": created_at.isoformat(),
            "classification": "WATCH", "final_probability": 0.08,
            "reference_stake": 10.0, "odds_at_prediction": 200,
            "actual_hr_binary": 0, "pnl_amount": -10.0,
            "game_pk": 3, "team_name": "Cubs", "opponent_name": "Reds",
        },
    ]
    legs = [{"prediction_id": "combo_leg1", "player_id": 9, "player_name": "Combo Player", "probability": 0.12, "classification": "PRIMARY", "game_pk": 4}]
    combo_rows = [{
        "combination_id": "combo1", "kind": "BEST_2_MAN", "created_at": created_at.isoformat(),
        "legs_json": json.dumps(legs), "filter_status": "QUALIFIED",
        "won": 1, "profit_loss": 30.0, "estimated_decimal_odds": 3.2,
    }]
    prediction_rows = {"combo_leg1": {"game_time": game_time.isoformat()}}

    class _Store:
        def history_prediction_rows(self, limit=2000):
            return list(player_rows)

        def history_combination_rows(self, limit=1000):
            return list(combo_rows)

        def prediction_rows_by_ids(self, ids):
            return {k: v for k, v in prediction_rows.items() if k in ids}

        def leg_settlements(self, ids):
            return {}

        def get_state(self, key, default=None):
            return "America/Santo_Domingo" if key == "timezone_name" else default

    return _Store()


def test_clicking_aciertos_hoy_switches_to_third_stack_page():
    app()
    widget = HistoryWidget(_FakeStore())

    widget.hits_today_btn.click()

    assert widget.mode_stack.currentIndex() == 2


def test_aciertos_hoy_shows_exact_hit_counts_and_names():
    app()
    widget = HistoryWidget(_hits_today_store())

    widget.hits_today_btn.click()
    texts = _hits_today_texts(widget)

    assert "Jugadores acertados: 2" in texts
    assert "Combinaciones ganadas: 1" in texts
    assert "Aaron Judge" in texts
    assert "Juan Soto" in texts
    assert "Player Miss" not in texts  # did not hit -- must not appear as a hit
    assert "Combo Player" in texts


def test_aciertos_hoy_empty_state_message():
    app()
    widget = HistoryWidget(_FakeStore())

    widget.hits_today_btn.click()
    texts = _hits_today_texts(widget)

    assert "Todavía no hay predicciones acertadas para esta fecha." in texts


def test_actualizar_resultados_disables_button_and_shows_progress_feedback():
    app()
    calls = []

    def runner():
        calls.append(1)
        return SettlementRunResult(checked=1, updated=1, still_pending=0, errors=())

    widget = HistoryWidget(_FakeStore(), settlement_runner=runner)

    widget.refresh_results_btn.click()

    assert widget.refresh_results_btn.isEnabled() is False
    assert "Actualizando resultados" in widget.results_feedback.text()
    _pump()
    assert widget.refresh_results_btn.isEnabled() is True
    assert calls == [1]


def test_actualizar_resultados_shows_success_feedback_and_refreshes_views():
    app()
    store = _hits_today_store()

    def runner():
        return SettlementRunResult(checked=3, updated=2, still_pending=1, errors=())

    widget = HistoryWidget(store, settlement_runner=runner)
    widget.hits_today_btn.click()  # move onto ACIERTOS HOY so refresh() effects are visible there

    widget.refresh_results_btn.click()
    _pump()

    assert widget.refresh_results_btn.isEnabled() is True
    assert "actualizado" in widget.results_feedback.text().lower()
    assert widget.results_feedback.objectName() == "good"
    # refresh() ran again -- ACIERTOS HOY content is still correctly populated from the store.
    assert "Jugadores acertados: 2" in _hits_today_texts(widget)


def test_actualizar_resultados_shows_error_and_reenables_button():
    app()

    def failing_runner():
        raise RuntimeError("MLB feed unavailable")

    widget = HistoryWidget(_FakeStore(), settlement_runner=failing_runner)

    widget.refresh_results_btn.click()
    _pump()

    assert widget.refresh_results_btn.isEnabled() is True
    assert "mlb feed unavailable" in widget.results_feedback.text().lower()
    assert widget.results_feedback.objectName() == "warning"


def test_actualizar_resultados_never_reaches_analyze_slate():
    # HistoryWidget's settlement_runner is injected directly (a bound
    # SettlementCoordinator.refresh_pending in production); the widget never
    # holds a reference to AnalysisService, so there is no attribute path to
    # analyze_slate() from here at all.
    app()
    widget = HistoryWidget(_FakeStore(), settlement_runner=lambda: SettlementRunResult(0, 0, 0, ()))

    assert not hasattr(widget, "analysis_service")
    assert not hasattr(widget, "service")
    widget.refresh_results_btn.click()
    _pump()
    assert widget.refresh_results_btn.isEnabled() is True
