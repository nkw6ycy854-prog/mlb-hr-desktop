from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

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
