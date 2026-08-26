from datetime import datetime, timezone
import json

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel

from mlb_hr.services.history import HistoryFilter
from mlb_hr.ui.history import HistoryWidget


def app():
    return QApplication.instance() or QApplication([])


class _FakeStore:
    def history_prediction_rows(self, limit=2000):
        return []

    def history_combination_rows(self, limit=1000):
        return []

    def prediction_rows_by_ids(self, ids):
        return {}

    def get_state(self, key, default=None):
        return default


def _widget() -> HistoryWidget:
    app()
    return HistoryWidget(_FakeStore())


def test_history_defaults_to_jugadores_view():
    widget = _widget()
    assert widget.mode_stack.currentIndex() == 0


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


def _tz_store():
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
        "won": None, "profit_loss": None, "estimated_decimal_odds": 2.5,
    }
    prediction_rows = {"p1": {"game_time": game_time_p1}, "p2": {"game_time": game_time_p2}}

    class _TzStore:
        def history_prediction_rows(self, limit=2000):
            return [player_row]

        def history_combination_rows(self, limit=1000):
            return [combo_row]

        def prediction_rows_by_ids(self, ids):
            return {k: v for k, v in prediction_rows.items() if k in ids}

        def get_state(self, key, default=None):
            return "America/Santo_Domingo" if key == "timezone_name" else default

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
    assert "PENDING" in texts


def test_selecting_combination_row_shows_each_leg_with_individual_time():
    app()
    widget = HistoryWidget(_tz_store())
    widget.set_mode(1)
    widget._select_combination_row(0, 0)
    texts = "\n".join(label.text() for label in widget.detail.findChildren(QLabel))
    assert "Aaron Judge" in texts and "7:05 PM" in texts
    assert "Juan Soto" in texts and "6:40 PM" in texts
