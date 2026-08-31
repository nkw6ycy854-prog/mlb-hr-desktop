from __future__ import annotations

from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from mlb_hr import __version__
from mlb_hr.ui.components import make_scroll_page
from mlb_hr.ui.history import HistoryWidget
from mlb_hr.ui.presentation import data_health_ok
from mlb_hr.ui.settings import SettingsWidget
from mlb_hr.ui.today import TodayWidget


class MainWindow(QMainWindow):
    def __init__(self, analysis_service, store, paths=None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("MLB HR")
        self.resize(1180, 760)
        self.paths = paths
        self.health_retry_callback = None
        self.settlement_trigger_callback = None

        self.today = TodayWidget(analysis_service, store)
        self.history = HistoryWidget(store)
        self.settings = SettingsWidget(store, paths=paths)

        self.pages = QStackedWidget()
        self.pages.addWidget(make_scroll_page(self.today))
        self.pages.addWidget(make_scroll_page(self.history))
        self.pages.addWidget(make_scroll_page(self.settings))

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(200)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(12, 18, 12, 12)
        sidebar_layout.setSpacing(6)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)

        self.nav_today = self._make_nav_button("Hoy", 0)
        self.nav_history = self._make_nav_button("Historial", 1)
        self.nav_settings = self._make_nav_button("Ajustes", 2)
        self._nav_buttons = (self.nav_today, self.nav_history, self.nav_settings)
        for btn in self._nav_buttons:
            sidebar_layout.addWidget(btn)
        sidebar_layout.addStretch()

        self.status_model = QLabel("Modelo —")
        self.status_model.setObjectName("muted")
        self.status_data = QLabel("Datos —")
        self.status_data.setObjectName("muted")
        self.status_version = QLabel(f"Versión {__version__}")
        self.status_version.setObjectName("muted")
        for lbl in (self.status_model, self.status_data, self.status_version):
            sidebar_layout.addWidget(lbl)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(sidebar)
        layout.addWidget(self.pages, 1)
        self.setCentralWidget(central)

        self.nav_today.setChecked(True)
        self.set_page(0)

    def _make_nav_button(self, label: str, index: int) -> QPushButton:
        btn = QPushButton(label)
        btn.setObjectName("navButton")
        btn.setCheckable(True)
        btn.clicked.connect(lambda: self.set_page(index))
        self.nav_group.addButton(btn)
        return btn

    def set_page(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        # set_page() can be reached without a nav-button click (e.g. "ABRIR
        # AJUSTES" from TodayWidget's health-failure banner calls this
        # directly) -- QButtonGroup only auto-toggles checked state on an
        # actual click, so the sidebar has to be synced here explicitly.
        for i, btn in enumerate(self._nav_buttons):
            btn.setChecked(i == index)
        if index == 1:
            self.history.refresh()

    def apply_health_report(self, report) -> None:
        self._apply_sidebar_health(report)
        if hasattr(self.today, "apply_health_report"):
            self.today.apply_health_report(report)
        if hasattr(self.settings, "apply_health_report"):
            self.settings.apply_health_report(report)
        if report.critical_ok:
            self.today.refresh()
            if self.settlement_trigger_callback:
                self.settlement_trigger_callback()
        else:
            self.today.show_health_failure(
                report,
                on_open_settings=lambda: self.set_page(2),
                on_retry=lambda: self.health_retry_callback() if self.health_retry_callback else None,
            )

    def _apply_sidebar_health(self, report) -> None:
        model_item = next((i for i in report.items if i.key == "model"), None)
        if model_item:
            self.status_model.setText(f"Modelo ● {model_item.state}")
            self.status_model.setObjectName("good" if model_item.state == "OK" else "warning")
        data_ok = data_health_ok(report)
        self.status_data.setText(f"Datos ● {'OK' if data_ok else 'ERROR'}")
        self.status_data.setObjectName("good" if data_ok else "warning")

    def apply_health_error(self, msg: str) -> None:
        from mlb_hr.services.health import HealthItem, HealthReport
        report = HealthReport(
            items=(HealthItem(key="health_check", label="Health check", state="ERROR", detail=msg),),
            critical_ok=False,
        )
        self.apply_health_report(report)
