from __future__ import annotations

from PySide6.QtWidgets import QMainWindow,QTabWidget

from mlb_hr.ui.history import HistoryWidget
from mlb_hr.ui.settings import SettingsWidget
from mlb_hr.ui.today import TodayWidget


class MainWindow(QMainWindow):
    def __init__(self,analysis_service,store,parent=None)->None:
        super().__init__(parent);self.setWindowTitle("MLB HR");self.resize(1180,760)
        tabs=QTabWidget();self.today=TodayWidget(analysis_service,store);self.history=HistoryWidget(store);self.settings=SettingsWidget(store)
        tabs.addTab(self.today,"HOY");tabs.addTab(self.history,"HISTORIAL");tabs.addTab(self.settings,"AJUSTES")
        tabs.currentChanged.connect(lambda i:self.history.refresh() if i==1 else None)
        self.setCentralWidget(tabs)
