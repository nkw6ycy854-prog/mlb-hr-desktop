from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

import mlb_hr.ui.main_window as mw


class DummyPage(mw.QWidget):
    def refresh(self):
        self.refreshed = True


def test_sidebar_navigation_changes_page(monkeypatch):
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(mw, "TodayWidget", lambda *_: DummyPage())
    monkeypatch.setattr(mw, "HistoryWidget", lambda *_: DummyPage())
    monkeypatch.setattr(mw, "SettingsWidget", lambda *_, **__: DummyPage())
    w = mw.MainWindow(object(), object())
    assert w.pages.currentIndex() == 0
    QTest.mouseClick(w.nav_history, Qt.MouseButton.LeftButton)
    assert w.pages.currentIndex() == 1
    QTest.mouseClick(w.nav_settings, Qt.MouseButton.LeftButton)
    assert w.pages.currentIndex() == 2


def test_set_page_called_programmatically_still_syncs_sidebar_active_state(monkeypatch):
    # Reproduces the real ABRIR AJUSTES flow: TodayWidget's health-failure
    # banner calls self.set_page(2) directly (not a click on nav_settings),
    # so the sidebar's checked state has to be kept in sync in set_page()
    # itself, not rely on QButtonGroup's own click-driven toggle.
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(mw, "TodayWidget", lambda *_: DummyPage())
    monkeypatch.setattr(mw, "HistoryWidget", lambda *_: DummyPage())
    monkeypatch.setattr(mw, "SettingsWidget", lambda *_, **__: DummyPage())
    w = mw.MainWindow(object(), object())

    w.set_page(2)

    assert w.nav_settings.isChecked() is True
    assert w.nav_today.isChecked() is False
    assert w.nav_history.isChecked() is False

    w.set_page(0)

    assert w.nav_today.isChecked() is True
    assert w.nav_settings.isChecked() is False
