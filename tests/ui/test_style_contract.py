import re

from mlb_hr.ui.style import APP_STYLESHEET


def test_stylesheet_contains_required_selectors():
    for token in [
        "QFrame#sidebar",
        "QPushButton#navButton",
        'QPushButton#navButton:checked',
        'QLabel[tone="good"]',
        'QLabel[tone="warning"]',
        'QLabel[tone="bad"]',
        "QPushButton:disabled",
    ]:
        assert token in APP_STYLESHEET


def _rule_body(selector: str) -> str:
    match = re.search(rf"^{re.escape(selector)}\s*\{{([^}}]*)\}}", APP_STYLESHEET, re.MULTILINE)
    assert match is not None, f"selector {selector!r} not found in stylesheet"
    return match.group(1)


def test_base_widget_rule_sets_an_explicit_dark_background():
    # Plain QWidget pages (TodayWidget/HistoryWidget/SettingsWidget) and the
    # QScrollArea viewport that wraps them are not QFrame/QMainWindow, so without
    # an explicit background on the bare QWidget selector they fall back to the
    # native macOS light background -- leaving light-colored labels illegible.
    body = _rule_body("QWidget")
    assert "background" in body


def test_scroll_area_rule_sets_an_explicit_dark_background():
    body = _rule_body("QScrollArea")
    assert "background" in body


def test_combobox_popup_view_has_dark_background_and_readable_text():
    # QComboBox QAbstractItemView is the dropdown popup's list view -- a
    # separate top-level widget that does not inherit QComboBox's own closed-
    # state background, so it needs its own explicit rule or it falls back to
    # a light native popup with light text (illegible).
    body = _rule_body("QComboBox QAbstractItemView")
    assert "background" in body
    assert "color" in body


def test_combobox_popup_item_selected_and_hover_states_are_styled():
    for token in [
        "QComboBox QAbstractItemView::item:selected",
        "QComboBox QAbstractItemView::item:hover",
    ]:
        assert token in APP_STYLESHEET


def test_popup_scrollbar_is_styled_dark():
    for token in ["QScrollBar:vertical", "QScrollBar::handle:vertical"]:
        assert token in APP_STYLESHEET
