from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from mlb_hr.services.status_center import StatusCenterReport, StatusItem
from mlb_hr.ui.components import DetailSidePanel

# Real, non-predictive impact/action text per component -- shown only when
# that component is not OK, matching the approved plan's "qué falló, impacto
# práctico, acción disponible" requirement (section 40). Never a raw log dump.
_IMPACT_ACTION = {
    "model": ("Las predicciones podrían no generarse.", "Revisa AJUSTES > SISTEMA."),
    "statcast": ("El análisis HR está bloqueado hasta que haya datos.", "Verifica que Statcast local esté disponible."),
    "mlb_feed": ("El slate de HOY podría estar incompleto o desactualizado.", "Pulsa ACTUALIZAR de nuevo."),
    "database": ("La app no puede leer ni guardar datos de forma fiable.", "Reinicia la app; si persiste, revisa el archivo de base de datos en AJUSTES > SISTEMA."),
    "odds": ("No se mostrarán cuotas de mercado en los picks.", "Configura tu API key en AJUSTES > CUOTAS."),
    "last_settlement": ("Algunos resultados podrían no estar verificados.", "Pulsa ACTUALIZAR RESULTADOS en HISTORIAL."),
    "selftest": ("Uno o más chequeos internos fallaron.", "Ejecuta EJECUTAR SELF-TEST en AJUSTES para ver el detalle."),
}


class StatusCenterPanel(QWidget):
    """Sidebar-accessible Centro de Estado -- not a main nav section.
    Opened via the sidebar's SISTEMA OK / REQUIERE ATENCION indicator.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.on_close = None
        root = QVBoxLayout(self)
        header = QHBoxLayout()
        back_btn = QPushButton("← VOLVER")
        back_btn.setFlat(True)
        back_btn.clicked.connect(lambda: self.on_close() if self.on_close else None)
        header.addWidget(back_btn)
        header.addStretch()
        root.addLayout(header)
        self.global_label = QLabel("")
        self.global_label.setObjectName("section")
        root.addWidget(self.global_label)

        self.rows_container = QWidget()
        self.rows_layout = QVBoxLayout(self.rows_container)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.rows_container)
        root.addWidget(scroll)

        self.detail_panel = DetailSidePanel()
        root.addWidget(self.detail_panel)

        self._report: StatusCenterReport | None = None

    def render(self, report: StatusCenterReport) -> None:
        self._report = report
        tone = "recomendado" if report.global_state == "SISTEMA OK" else "alto_riesgo"
        self.global_label.setText(f"● {report.global_state}")
        self.global_label.setProperty("tone", tone)

        while self.rows_layout.count():
            item = self.rows_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for status_item in report.items:
            icon = {"OK": "●", "ADVERTENCIA": "◐", "ERROR": "✕", "SIN COMPROBAR AUN": "○"}.get(status_item.state, "○")
            btn = QPushButton(f"{icon} {status_item.label} · {status_item.state}")
            btn.setFlat(True)
            btn.clicked.connect(lambda _checked=False, i=status_item: self._show_item_detail(i))
            self.rows_layout.addWidget(btn)

    def _show_item_detail(self, item: StatusItem) -> None:
        self.detail_panel.clear_body()
        self.detail_panel.body.addWidget(QLabel(f"Estado: {item.state}"))
        self.detail_panel.body.addWidget(QLabel(f"Qué falló / detalle: {item.detail}"))
        self.detail_panel.body.addWidget(QLabel("Última comprobación: en esta sesión"))
        if item.state != "OK":
            impact, action = _IMPACT_ACTION.get(item.key, ("Impacto no especificado.", "Sin acción disponible."))
            self.detail_panel.body.addWidget(QLabel(f"Impacto práctico: {impact}"))
            self.detail_panel.body.addWidget(QLabel(f"Acción disponible: {action}"))
        self.detail_panel.open_panel(item.label)
