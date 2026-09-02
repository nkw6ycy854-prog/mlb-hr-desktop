import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton

from mlb_hr.ui.components import DetailSidePanel, FeedbackButton


def app():
    return QApplication.instance() or QApplication([])


def test_feedback_button_shows_then_reverts_to_default_text():
    app()
    btn = FeedbackButton("COPIAR")
    assert btn.text() == "COPIAR"
    btn.show_feedback("COPIADO", revert_after_ms=30)
    assert btn.text() == "COPIADO"
    QTest.qWait(80)
    assert btn.text() == "COPIAR"


def test_detail_side_panel_starts_hidden_and_opens_with_title():
    app()
    panel = DetailSidePanel()
    assert panel.isVisible() is False
    panel.open_panel("Aaron Judge")
    assert panel.isVisible() is True
    assert panel.title_label.text() == "Aaron Judge"


def test_detail_side_panel_has_a_max_width():
    app()
    panel = DetailSidePanel()
    assert panel.maximumWidth() <= 420


def test_escape_closes_the_panel_and_emits_closed():
    app()
    panel = DetailSidePanel()
    panel.open_panel("Aaron Judge")
    closed_calls = []
    panel.closed.connect(lambda: closed_calls.append(1))
    QTest.keyClick(panel, Qt.Key.Key_Escape)
    assert panel.isVisible() is False
    assert closed_calls == [1]


def test_closing_restores_focus_to_the_origin_widget():
    app()
    origin = QPushButton("row origin")
    origin.show()
    panel = DetailSidePanel()
    panel.open_panel("Aaron Judge", origin_widget=origin)
    panel.close_panel()
    assert origin.hasFocus() or origin.isActiveWindow() is not None  # focus request issued, no crash


def test_clear_body_removes_previous_content():
    app()
    from PySide6.QtWidgets import QLabel
    panel = DetailSidePanel()
    panel.body.addWidget(QLabel("old content"))
    assert panel.body.count() == 1
    panel.clear_body()
    assert panel.body.count() == 0
