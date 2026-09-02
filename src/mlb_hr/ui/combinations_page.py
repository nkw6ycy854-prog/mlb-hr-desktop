from __future__ import annotations

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from mlb_hr.domain.enums import CombinationFilterStatus
from mlb_hr.domain.models import Combination, SlateResult
from mlb_hr.ui.components import DetailSidePanel, ResponsiveGrid
from mlb_hr.ui.presentation import display_quote, quote_display, visual_state

_KINDS = [
    ("BEST_2_MAN", "BEST 2-MAN"),
    ("BEST_3_MAN", "BEST 3-MAN"),
    ("LONG_SHOT_2_MAN", "LONG-SHOT 2-MAN"),
    ("LONG_SHOT_3_MAN", "LONG-SHOT 3-MAN"),
]


class CombinationCard(QFrame):
    """One of the 4 always-visible combination-kind cards."""

    def __init__(self, kind: str, label: str, combo: Combination | None, stake: float, on_detail, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.kind = kind
        self.combo = combo
        layout = QVBoxLayout(self)
        title = QLabel(label)
        title.setStyleSheet("font-weight:700;")
        layout.addWidget(title)

        if combo is None:
            layout.addWidget(QLabel("NO HAY SUFICIENTES JUGADORES ANALIZADOS"))
            self.detail_btn = None
            return

        qualified = combo.filter_status == CombinationFilterStatus.QUALIFIED
        status_text = "✅ CUMPLE FILTRO · RECOMENDADA" if qualified else "⚠ NO CUMPLE FILTRO · ALTO RIESGO"
        status_label = QLabel(status_text)
        status_label.setProperty("tone", "recomendado" if qualified else "alto_riesgo")
        layout.addWidget(status_label)

        for leg in combo.legs:
            layout.addWidget(QLabel(f"{leg.player_name} · {leg.classification.value}"))

        if combo.estimated_decimal_odds:
            total = stake * combo.estimated_decimal_odds
            layout.addWidget(QLabel(f"PAYOUT: ${stake:.0f} → ${total:.2f}"))
        else:
            payout_label = QLabel("PAYOUT: N/A")
            payout_label.setToolTip("No hay suficientes cuotas de mercado para calcular el pago combinado de esta combinación.")
            layout.addWidget(payout_label)
            explain = QLabel("SIN CUOTA CONJUNTA — no hay suficientes cuotas de mercado para las piernas de esta combinación.")
            explain.setObjectName("muted")
            explain.setWordWrap(True)
            layout.addWidget(explain)

        self.detail_btn = QPushButton("VER DETALLE")
        self.detail_btn.clicked.connect(lambda: on_detail(kind, label, combo, self.detail_btn))
        layout.addWidget(self.detail_btn)


class CombinationsPageWidget(QScrollArea):
    """COMBINACIONES -- its own top-level page. Always shows all 4 kinds;
    never changes CombinationEngine.build()/save_combination() output, only
    how it's presented.
    """

    def __init__(self, service, parent=None) -> None:
        super().__init__(parent)
        self.service = service
        self.setWidgetResizable(True)
        self._current: SlateResult | None = None
        self._cards_by_kind: dict[str, CombinationCard] = {}
        self._cards_by_prediction_id: dict[str, object] = {}
        self.refresh_callback = None

        container = QWidget()
        self._layout = QVBoxLayout(container)

        top = QHBoxLayout()
        self.refresh_btn = QPushButton("ACTUALIZAR")
        self.refresh_btn.setObjectName("primaryButton")
        self.refresh_btn.clicked.connect(self._trigger_refresh)
        top.addStretch()
        top.addWidget(self.refresh_btn)
        self._layout.addLayout(top)

        self.grid = ResponsiveGrid(two_column_min_width=760)
        self._layout.addWidget(self.grid)

        self.detail_panel = DetailSidePanel()
        self._layout.addWidget(self.detail_panel)

        self._layout.addStretch()
        self.setWidget(container)

    def _trigger_refresh(self) -> None:
        if self.refresh_callback:
            self.refresh_btn.setEnabled(False)
            self.refresh_callback()

    def render(self, result: SlateResult) -> None:
        self.refresh_btn.setEnabled(True)
        self._current = result
        self._cards_by_prediction_id = {c.prediction.prediction_id: c for c in result.cards}
        combos = {c.kind: c for c in result.combinations}
        stake = getattr(self.service, "stake", 10.0)

        cards = []
        self._cards_by_kind = {}
        for kind, label in _KINDS:
            card = CombinationCard(kind, label, combos.get(kind), stake, self._show_combo_detail)
            self._cards_by_kind[kind] = card
            cards.append(card)
        self.grid.set_widgets(cards)

    def _show_combo_detail(self, kind: str, label: str, combo: Combination, origin_widget=None) -> None:
        self.detail_panel.clear_body()
        qualified = combo.filter_status == CombinationFilterStatus.QUALIFIED
        status = QLabel("✅ CUMPLE FILTRO" if qualified else "⚠ NO CUMPLE FILTRO · ALTO RIESGO")
        self.detail_panel.body.addWidget(status)
        for leg in combo.legs:
            card = self._cards_by_prediction_id.get(leg.prediction_id)
            row_text = f"{leg.player_name} · {leg.probability*100:.1f}%"
            if card is not None:
                state = visual_state(card.prediction.classification, eligible=True)
                odds = display_quote(card, best=True)
                row_text += f" · {state} · {odds}"
                btn = QPushButton(row_text)
                btn.setFlat(True)
                btn.clicked.connect(lambda _checked=False, c=card, k=kind, l=label, cb=combo, ow=origin_widget: self._show_player_detail(c, k, l, cb, ow))
                self.detail_panel.body.addWidget(btn)
            else:
                self.detail_panel.body.addWidget(QLabel(row_text))
        if combo.estimated_decimal_odds:
            self.detail_panel.body.addWidget(QLabel(f"Cuota combinada: {combo.estimated_decimal_odds:.2f}"))
        else:
            self.detail_panel.body.addWidget(QLabel("PAYOUT: N/A"))
        # origin_widget is always the CombinationCard's own VER DETALLE
        # button that started this flow -- kept stable across VOLVER A
        # COMBINACIÓN hops so Esc always restores focus to where the user
        # actually began, not to an intermediate leg.
        self.detail_panel.open_panel(label, origin_widget=origin_widget)

    def _show_player_detail(self, card, kind: str, label: str, combo: Combination, origin_widget=None) -> None:
        self.detail_panel.clear_body()
        p = card.prediction
        state = visual_state(p.classification, eligible=True)
        self.detail_panel.body.addWidget(QLabel(f"HR% {p.final_hr_probability*100:.1f}%"))
        self.detail_panel.body.addWidget(QLabel(f"Estado: {state}"))
        qd = quote_display(card)
        self.detail_panel.body.addWidget(QLabel(qd.best_text))
        for reason in p.reasons[:3]:
            self.detail_panel.body.addWidget(QLabel("✓ " + reason))
        self.detail_panel.body.addWidget(QLabel("Riesgo principal: " + (p.main_risk or "Sin advertencias importantes")))
        back_btn = QPushButton("VOLVER A COMBINACIÓN")
        back_btn.clicked.connect(lambda: self._show_combo_detail(kind, label, combo, origin_widget))
        self.detail_panel.body.addWidget(back_btn)
        self.detail_panel.open_panel(p.player.full_name, origin_widget=origin_widget)
