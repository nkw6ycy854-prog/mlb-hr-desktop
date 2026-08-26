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
