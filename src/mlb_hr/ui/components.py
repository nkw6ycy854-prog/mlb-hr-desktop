from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget


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


class FeedbackButton(QPushButton):
    """A button that shows transient confirmation text after being clicked,
    then reverts to its own default label. Used everywhere a control needs
    one-shot feedback (COPIAR -> COPIADO, GUARDAR PICK -> GUARDADO) instead
    of each screen reimplementing the same QTimer.singleShot pattern.
    """

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self._default_text = text

    def show_feedback(self, text: str, revert_after_ms: int = 1500) -> None:
        self.setText(text)
        QTimer.singleShot(revert_after_ms, lambda: self.setText(self._default_text))


class DetailSidePanel(QFrame):
    """Reusable slide-in detail panel, shared by HOY/POR PARTIDOS/COMBINACIONES.

    Lives inside the same page (not a modal dialog), toggled visible/hidden
    with a bounded max-width, Esc-to-close, and focus restored to whatever
    row/control opened it.
    """

    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setMaximumWidth(420)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._origin_widget: QWidget | None = None

        root = QVBoxLayout(self)
        header = QHBoxLayout()
        self.title_label = QLabel("")
        self.title_label.setObjectName("section")
        header.addWidget(self.title_label)
        header.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setFlat(True)
        close_btn.setToolTip("Cerrar (Esc)")
        close_btn.clicked.connect(self.close_panel)
        header.addWidget(close_btn)
        root.addLayout(header)

        self.body = QVBoxLayout()
        root.addLayout(self.body)
        root.addStretch()

        self.hide()

    def open_panel(self, title: str, *, origin_widget: QWidget | None = None) -> None:
        self.title_label.setText(title)
        self._origin_widget = origin_widget
        self.show()
        self.setFocus()

    def close_panel(self) -> None:
        self.hide()
        self.closed.emit()
        if self._origin_widget is not None:
            self._origin_widget.setFocus()

    def clear_body(self) -> None:
        while self.body.count():
            item = self.body.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close_panel()
            return
        super().keyPressEvent(event)


def make_scroll_page(content: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QScrollArea.Shape.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    area.setWidget(content)
    return area
