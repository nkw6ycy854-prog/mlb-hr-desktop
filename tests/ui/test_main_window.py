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
