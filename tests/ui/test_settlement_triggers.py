from datetime import datetime, timezone
from types import SimpleNamespace

from PySide6.QtWidgets import QApplication, QWidget

import mlb_hr.ui.main_window as mw
from mlb_hr.domain.enums import ModelHealth, SlateQuality
from mlb_hr.domain.models import SlateResult
from mlb_hr.services.health import HealthItem, HealthReport
from mlb_hr.ui.today import TodayWidget


def app():
    return QApplication.instance() or QApplication([])


def _make_service():
    return SimpleNamespace(stake=10.0)


def _report(critical_ok: bool):
    return HealthReport(
        items=(HealthItem(key="model", label="Modelo", state="OK", detail="V1.0.0 validado."),),
        critical_ok=critical_ok,
    )


def _slate_result():
    return SlateResult(
        cards=[], combinations=[], slate_quality=SlateQuality.GREEN, model_health=ModelHealth.GREEN,
        confirmed_lineups=0, total_games=0, updated_at=datetime.now(timezone.utc),
    )


# --- TodayWidget: settlement trigger runs after a slate load (post-ACTUALIZAR) ---

def test_today_widget_calls_settlement_trigger_after_loaded():
    app()
    widget = TodayWidget(_make_service(), None)
    calls = []
    widget.settlement_trigger = lambda: calls.append(1)

    widget._loaded(_slate_result())

    assert calls == [1]


def test_today_widget_tolerates_no_settlement_trigger_configured():
    app()
    widget = TodayWidget(_make_service(), None)
    assert widget.settlement_trigger is None

    widget._loaded(_slate_result())  # must not raise


# --- MainWindow: settlement trigger runs once startup health passes ---

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

    def apply_health_report(self, report):
        self.health_report = report


def _main_window(monkeypatch):
    app()
    monkeypatch.setattr(mw, "TodayWidget", lambda *_: DummyToday())
    monkeypatch.setattr(mw, "HistoryWidget", lambda *_: DummyPage())
    monkeypatch.setattr(mw, "SettingsWidget", lambda *_, **__: DummyPage())
    return mw.MainWindow(object(), object())


def test_settlement_trigger_callback_runs_once_health_is_ok(monkeypatch):
    w = _main_window(monkeypatch)
    calls = []
    w.settlement_trigger_callback = lambda: calls.append(1)

    w.apply_health_report(_report(True))

    assert calls == [1]


def test_settlement_trigger_callback_does_not_run_when_health_fails(monkeypatch):
    w = _main_window(monkeypatch)
    calls = []
    w.settlement_trigger_callback = lambda: calls.append(1)

    w.apply_health_report(_report(False))

    assert calls == []


def test_settlement_trigger_callback_is_optional(monkeypatch):
    w = _main_window(monkeypatch)
    assert w.settlement_trigger_callback is None

    w.apply_health_report(_report(True))  # must not raise
