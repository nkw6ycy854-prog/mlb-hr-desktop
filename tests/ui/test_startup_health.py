from datetime import datetime, timezone
from types import SimpleNamespace

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

import mlb_hr.ui.main_window as mw
from mlb_hr.domain.enums import ModelHealth, SlateQuality
from mlb_hr.services.health import HealthItem, HealthReport
from mlb_hr.ui.today import TodayWidget


def app():
    return QApplication.instance() or QApplication([])


def _make_service():
    return SimpleNamespace(stake=10.0)


def _today_widget() -> TodayWidget:
    widget = TodayWidget(_make_service(), None)
    widget.show()
    return widget


def _report(critical_ok: bool, items=None):
    return HealthReport(
        items=items or (
            HealthItem(key="model", label="Modelo", state="OK", detail="V1.0.0 validado."),
            HealthItem(key="statcast", label="Statcast", state="OK" if critical_ok else "ERROR",
                       detail="Datos disponibles." if critical_ok else "Statcast no fue encontrado."),
            HealthItem(key="database", label="Base de datos", state="OK", detail="Conexión OK."),
            HealthItem(key="odds", label="Cuotas", state="NOT_CONFIGURED", detail="SIN API / NO CONFIGURADO."),
        ),
        critical_ok=critical_ok,
    )


# --- TodayWidget banner behavior ---

def test_show_health_failure_displays_explicit_banner_and_hides_ranking():
    app()
    widget = _today_widget()
    widget.show_health_failure(_report(False), on_open_settings=lambda: None, on_retry=lambda: None)

    assert widget.health_failure_frame.isVisible()
    assert "STATCAST" in widget.health_title.text().upper()
    assert "Statcast no fue encontrado." in widget.health_detail.text()
    assert widget.main_pair.isVisible() is False


def test_abrir_ajustes_button_calls_open_settings_callback():
    app()
    widget = _today_widget()
    called = []
    widget.show_health_failure(_report(False), on_open_settings=lambda: called.append("settings"), on_retry=lambda: None)

    QTest.mouseClick(widget.health_open_settings_btn, Qt.MouseButton.LeftButton)

    assert called == ["settings"]


def test_reintentar_button_calls_retry_callback():
    app()
    widget = _today_widget()
    called = []
    widget.show_health_failure(_report(False), on_open_settings=lambda: None, on_retry=lambda: called.append("retry"))

    QTest.mouseClick(widget.health_retry_btn, Qt.MouseButton.LeftButton)

    assert called == ["retry"]


def test_hide_health_failure_restores_ranking_view():
    app()
    widget = _today_widget()
    widget.show_health_failure(_report(False), on_open_settings=lambda: None, on_retry=lambda: None)

    widget.hide_health_failure()

    assert widget.health_failure_frame.isVisible() is False
    assert widget.main_pair.isVisible() is True


def test_loaded_clears_a_previously_shown_health_failure():
    from mlb_hr.domain.models import SlateResult
    app()
    widget = _today_widget()
    widget.show_health_failure(_report(False), on_open_settings=lambda: None, on_retry=lambda: None)

    result = SlateResult(
        cards=[], combinations=[], slate_quality=SlateQuality.GREEN, model_health=ModelHealth.GREEN,
        confirmed_lineups=0, total_games=0, updated_at=datetime.now(timezone.utc),
    )
    widget._loaded(result)

    assert widget.health_failure_frame.isVisible() is False
    assert widget.main_pair.isVisible() is True


# --- "Datos" indicator now sourced from HealthService, not SlateQuality ---

def test_data_status_reflects_health_report_not_slate_quality():
    from mlb_hr.domain.models import SlateResult
    app()
    widget = _today_widget()

    widget.apply_health_report(_report(True))
    assert "OK" in widget.data_status.text()

    # A subsequent refresh with a RED slate_quality must not downgrade the "Datos" indicator:
    # that indicator is now owned by HealthService, not by the per-slate SlateQuality value.
    result = SlateResult(
        cards=[], combinations=[], slate_quality=SlateQuality.RED, model_health=ModelHealth.GREEN,
        confirmed_lineups=0, total_games=0, updated_at=datetime.now(timezone.utc),
    )
    widget._loaded(result)
    assert "OK" in widget.data_status.text()


def test_data_status_shows_error_when_health_report_statcast_fails():
    app()
    widget = _today_widget()
    widget.apply_health_report(_report(False))
    assert "ERROR" in widget.data_status.text()


# --- MainWindow wiring ---

class _FakeStore:
    # Centro de Estado's own cold-start ("SIN COMPROBAR AUN") behavior is
    # covered exhaustively in test_status_center.py; this fake is only for
    # MainWindow-level plumbing tests, so it reports as fully checked/OK.
    def get_state(self, key, default=None):
        if key == "last_mlb_feed_status":
            return {"quality": "GREEN", "messages": []}
        if key == "last_settlement_run":
            return {"checked": 0, "updated": 0, "errors": 0}
        if key == "last_selftest_passed":
            return True
        return default


class DummyPage(QWidget):
    def __init__(self, *_):
        super().__init__()
        self.health_report = None

    def refresh(self):
        self.refreshed = True

    def apply_health_report(self, report):
        self.health_report = report


class DummyToday(QWidget):
    def __init__(self, *_):
        super().__init__()
        self.refreshed = False
        self.failure_report = None
        self.health_report = None

    def refresh(self):
        self.refreshed = True

    def show_health_failure(self, report, on_open_settings, on_retry):
        self.failure_report = report
        self._on_open_settings = on_open_settings
        self._on_retry = on_retry

    def apply_health_report(self, report):
        self.health_report = report


class DummyGamesPage(QWidget):
    def render(self, result):
        self.rendered = result


def _main_window(monkeypatch):
    app()
    monkeypatch.setattr(mw, "TodayWidget", lambda *_: DummyToday())
    monkeypatch.setattr(mw, "GamesPageWidget", lambda *_: DummyGamesPage())
    monkeypatch.setattr(mw, "CombinationsPageWidget", lambda *_: DummyGamesPage())
    monkeypatch.setattr(mw, "HistoryWidget", lambda *_: DummyPage())
    monkeypatch.setattr(mw, "SettingsWidget", lambda *_, **__: DummyPage())
    return mw.MainWindow(object(), _FakeStore())


def test_apply_health_report_refreshes_today_when_critical_ok(monkeypatch):
    w = _main_window(monkeypatch)

    w.apply_health_report(_report(True))

    assert w.today.refreshed is True
    assert w.today.failure_report is None


def test_apply_health_report_shows_failure_and_open_settings_switches_page(monkeypatch):
    w = _main_window(monkeypatch)

    report = _report(False)
    w.apply_health_report(report)

    assert w.today.refreshed is False
    assert w.today.failure_report is report
    w.today._on_open_settings()
    assert w.pages.currentIndex() == 4


def test_apply_health_report_retry_uses_supplied_callback(monkeypatch):
    w = _main_window(monkeypatch)
    called = []
    w.health_retry_callback = lambda: called.append("retry")

    w.apply_health_report(_report(False))
    w.today._on_retry()

    assert called == ["retry"]


def test_apply_health_error_shows_failure_banner(monkeypatch):
    w = _main_window(monkeypatch)

    w.apply_health_error("boom")

    assert w.today.refreshed is False
    assert w.today.failure_report is not None
    assert w.today.failure_report.critical_ok is False


def test_apply_health_report_refreshes_settings_sistema_section_too(monkeypatch):
    w = _main_window(monkeypatch)

    report = _report(False)
    w.apply_health_report(report)
    assert w.settings.health_report is report

    # A retry that later comes back healthy must refresh SISTEMA again with the new report.
    ok_report = _report(True)
    w.apply_health_report(ok_report)
    assert w.settings.health_report is ok_report


def test_apply_health_report_updates_sidebar_model_and_data_labels_when_ok(monkeypatch):
    w = _main_window(monkeypatch)

    w.apply_health_report(_report(True))

    assert "OK" in w.status_model.text()
    assert "OK" in w.status_data.text()


def test_apply_health_report_updates_sidebar_model_and_data_labels_when_error(monkeypatch):
    w = _main_window(monkeypatch)

    w.apply_health_report(_report(False))

    assert "ERROR" in w.status_data.text()


def test_status_center_indicator_reflects_sistema_ok(monkeypatch):
    w = _main_window(monkeypatch)
    all_ok = _report(True, items=(
        HealthItem(key="model", label="Modelo", state="OK", detail="V1.0.0 validado."),
        HealthItem(key="statcast", label="Statcast", state="OK", detail="Datos disponibles."),
        HealthItem(key="database", label="Base de datos", state="OK", detail="Conexión OK."),
        HealthItem(key="odds", label="Cuotas", state="OK", detail="Configurado."),
    ))
    w.apply_health_report(all_ok)
    assert "SISTEMA OK" in w.status_center_btn.text()


def test_status_center_indicator_reflects_requiere_atencion(monkeypatch):
    w = _main_window(monkeypatch)
    w.apply_health_report(_report(False))
    assert "REQUIERE ATENCION" in w.status_center_btn.text()


def test_opening_status_center_is_not_a_main_nav_section(monkeypatch):
    w = _main_window(monkeypatch)
    w.apply_health_report(_report(True))
    w.set_page(1)

    w.open_status_center()

    assert w.pages.currentIndex() == 5
    assert all(not btn.isChecked() for btn in w._nav_buttons)


def test_closing_status_center_restores_the_previous_page(monkeypatch):
    w = _main_window(monkeypatch)
    w.apply_health_report(_report(True))
    w.set_page(2)

    w.open_status_center()
    w.close_status_center()

    assert w.pages.currentIndex() == 2
    assert w._nav_buttons[2].isChecked() is True
