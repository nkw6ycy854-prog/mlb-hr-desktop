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
from mlb_hr.services.status_center import build_status_center_report
from mlb_hr.ui.combinations_page import CombinationsPageWidget
from mlb_hr.ui.components import make_scroll_page
from mlb_hr.ui.games_page import GamesPageWidget
from mlb_hr.ui.history import HistoryWidget
from mlb_hr.ui.presentation import data_health_ok
from mlb_hr.ui.settings import SettingsWidget
from mlb_hr.ui.status_center import StatusCenterPanel
from mlb_hr.ui.today import TodayWidget


class MainWindow(QMainWindow):
    def __init__(self, analysis_service, store, paths=None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("MLB HR")
        self.resize(1180, 760)
        self.paths = paths
        self.store = store
        self.health_retry_callback = None
        self.settlement_trigger_callback = None
        self._last_health_report = None
        self._page_before_status_center = 0

        self.today = TodayWidget(analysis_service, store)
        self.games_page = GamesPageWidget(store)
        self.combinations_page = CombinationsPageWidget(analysis_service)
        self.today.on_loaded = self._on_today_loaded
        self.history = HistoryWidget(store)
        self.settings = SettingsWidget(store, paths=paths)
        self.status_center_panel = StatusCenterPanel()
        self.status_center_panel.on_close = self.close_status_center

        self.pages = QStackedWidget()
        self.pages.addWidget(make_scroll_page(self.today))
        self.pages.addWidget(self.games_page)
        self.pages.addWidget(self.combinations_page)
        self.pages.addWidget(make_scroll_page(self.history))
        self.pages.addWidget(make_scroll_page(self.settings))
        self.pages.addWidget(self.status_center_panel)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(200)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(12, 18, 12, 12)
        sidebar_layout.setSpacing(6)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)

        self.nav_today = self._make_nav_button("Hoy", 0)
        self.nav_games = self._make_nav_button("Por Partidos", 1)
        self.nav_combinations = self._make_nav_button("Combinaciones", 2)
        self.nav_history = self._make_nav_button("Historial", 3)
        self.nav_settings = self._make_nav_button("Ajustes", 4)
        self._nav_buttons = (self.nav_today, self.nav_games, self.nav_combinations, self.nav_history, self.nav_settings)
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

        # Centro de Estado is NOT a main nav section -- accessed only via
        # this sidebar indicator, per the approved plan.
        self.status_center_btn = QPushButton("● SISTEMA OK")
        self.status_center_btn.setFlat(True)
        self.status_center_btn.clicked.connect(self.open_status_center)
        sidebar_layout.addWidget(self.status_center_btn)

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
        if index == 3:
            self.history.refresh()

    def _on_today_loaded(self, result) -> None:
        self.games_page.render(result)
        self.combinations_page.render(result)

    def open_status_center(self) -> None:
        if self._last_health_report is None:
            return
        self._page_before_status_center = self.pages.currentIndex()
        report = build_status_center_report(self._last_health_report, self.store)
        self.status_center_panel.render(report)
        self.pages.setCurrentIndex(5)
        # An exclusive QButtonGroup refuses to let its last-checked button
        # become unchecked (by design, it always keeps exactly one checked
        # once any has been) -- Centro de Estado isn't a nav section, so no
        # nav button should look active while it's open; toggling
        # exclusivity off is the standard way to uncheck all of them.
        self.nav_group.setExclusive(False)
        for btn in self._nav_buttons:
            btn.setChecked(False)
        self.nav_group.setExclusive(True)

    def close_status_center(self) -> None:
        self.pages.setCurrentIndex(self._page_before_status_center)
        for i, btn in enumerate(self._nav_buttons):
            btn.setChecked(i == self._page_before_status_center)

    def apply_health_report(self, report) -> None:
        self._last_health_report = report
        status_report = build_status_center_report(report, self.store)
        self.status_center_btn.setText(f"● {status_report.global_state}")
        self.status_center_btn.setProperty("tone", "recomendado" if status_report.global_state == "SISTEMA OK" else "alto_riesgo")
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
                on_open_settings=lambda: self.set_page(4),
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
