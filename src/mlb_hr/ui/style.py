APP_STYLESHEET = """
QMainWindow { background: #111318; color: #f5f7fb; }
QWidget { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; font-size: 13px; color: #edf0f5; }
QFrame#sidebar { background: #161920; border: 0; border-right: 1px solid #252b34; }
QPushButton#navButton { background: transparent; border: 0; border-radius: 7px; padding: 10px 14px; text-align: left; color: #9da5b4; font-weight: 600; }
QPushButton#navButton:hover { background: #1f232c; color: #f5f7fb; }
QPushButton#navButton:checked { background: #222731; color: #ffffff; }
QPushButton { background: #2b313d; border: 1px solid #3a4250; border-radius: 7px; padding: 8px 14px; }
QPushButton:hover { background: #343b49; }
QPushButton:disabled { background: #1c1f26; border-color: #2a2f38; color: #5b6270; }
QPushButton#primaryButton { background: #2d6a4f; border-color: #3c8b69; font-weight: 600; }
QPushButton#primaryButton:disabled { background: #1e332b; border-color: #294539; color: #5b6270; }
QLabel#title { font-size: 23px; font-weight: 700; }
QLabel#section { font-size: 16px; font-weight: 650; }
QLabel#muted { color: #9da5b4; }
QLabel#good { color: #61c991; font-weight: 600; }
QLabel#warning { color: #e7bd62; font-weight: 600; }
QLabel#bad { color: #e77b75; font-weight: 600; }
QLabel[tone="good"] { color: #61c991; font-weight: 600; }
QLabel[tone="warning"] { color: #e7bd62; font-weight: 600; }
QLabel[tone="bad"] { color: #e77b75; font-weight: 600; }
QLabel[tone="muted"] { color: #9da5b4; }
QTableWidget { background: #171a20; border: 1px solid #252b34; gridline-color: #252b34; border-radius: 8px; selection-background-color: #29323d; }
QTableWidget::item { padding: 4px 6px; }
QHeaderView::section { background: #20242c; color: #aeb6c4; border: 0; padding: 8px; font-weight: 600; }
QFrame#card { background: #171a20; border: 1px solid #252b34; border-radius: 10px; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox { background: #171a20; border: 1px solid #343b48; border-radius: 6px; padding: 7px; }
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled { color: #5b6270; border-color: #2a2f38; }
QScrollArea { border: 0; }
"""
