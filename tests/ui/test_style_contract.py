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
