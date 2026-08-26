from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QLabel, QScrollArea, QWidget


class StatusPill(QLabel):
    def set_status(self, text: str, tone: str = "muted") -> None:
        self.setText(text)
        self.setProperty("tone", tone)
        self.style().unpolish(self)
        self.style().polish(self)


class ResponsiveGrid(QWidget):
    def __init__(self, *, two_column_min_width: int = 760, parent=None):
        super().__init__(parent)
        self.two_column_min_width = two_column_min_width
        self.column_count = 1
        self._widgets: list[QWidget] = []
        self._layout = QGridLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(12)

    def set_widgets(self, widgets) -> None:
        self._widgets = list(widgets)
        self.reflow()

    def reflow(self) -> None:
        while self._layout.count():
            self._layout.takeAt(0)
        self.column_count = 2 if self.width() >= self.two_column_min_width else 1
        for i, widget in enumerate(self._widgets):
            self._layout.addWidget(widget, i // self.column_count, i % self.column_count)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.reflow()


def make_scroll_page(content: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QScrollArea.Shape.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    area.setWidget(content)
    return area
