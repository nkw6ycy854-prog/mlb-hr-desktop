from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from mlb_hr.domain.models import SlateResult
from mlb_hr.services.game_time import GameTimeService
from mlb_hr.services.game_views import GamePredictionView, GamePredictionViewBuilder, PlayerGameView
from mlb_hr.ui.components import DetailSidePanel, ResponsiveGrid
from mlb_hr.ui.presentation import display_quote, visual_state


class GameCard(QFrame):
    """One collapsible POR PARTIDOS card. Collapsed by default; the entire
    header is the only expand/collapse control, per the approved plan --
    never a hidden action buried in a player name.
    """

    def __init__(self, view: GamePredictionView, time_service: GameTimeService, on_player_click, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.game_pk = view.game_pk
        self.view = view
        self._on_player_click = on_player_click
        self.is_expanded = False
        self.lineup_status = self._compute_lineup_status(view)

        root = QVBoxLayout(self)
        self.header_btn = QPushButton(self._header_text(view, time_service))
        self.header_btn.setFlat(True)
        self.header_btn.clicked.connect(self.toggle)
        root.addWidget(self.header_btn)

        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self._render_body(view, time_service)
        self.body.hide()
        root.addWidget(self.body)

    @staticmethod
    def _compute_lineup_status(view: GamePredictionView) -> str:
        if view.away.lineup_confirmed and view.home.lineup_confirmed:
            return "CONFIRMADO"
        if view.away.lineup_confirmed or view.home.lineup_confirmed:
            return "PARCIAL"
        return "NO CONFIRMADO"

    def _header_text(self, view: GamePredictionView, time_service: GameTimeService) -> str:
        time_text = time_service.format_time(view.game_time_utc)
        all_players = list(view.away.players) + list(view.home.players)
        ge5 = sum(1 for p in all_players if p.hr_probability is not None and p.hr_probability >= 0.05)
        recommended = sum(1 for p in all_players if p.eligible and visual_state(p.classification, eligible=True) == "RECOMENDADO")
        return (
            f"{view.away.team_name} @ {view.home.team_name} · {time_text} · "
            f"{self.lineup_status} · ≥5%: {ge5} · RECOMENDADOS: {recommended}"
        )

    def _render_body(self, view: GamePredictionView, time_service: GameTimeService) -> None:
        if not view.ready and view.empty_message:
            msg = QLabel(view.empty_message)
            msg.setWordWrap(True)
            msg.setObjectName("muted")
            self.body_layout.addWidget(msg)

        teams = ResponsiveGrid(two_column_min_width=760)
        team_widgets = [self._team_widget(team) for team in (view.away, view.home)]
        teams.set_widgets(team_widgets)
        self.body_layout.addWidget(teams)

    def _team_widget(self, team) -> QWidget:
        frame = QFrame()
        layout = QVBoxLayout(frame)
        status_mark = "✅ CONFIRMADO" if team.lineup_confirmed else "⏳ NO CONFIRMADO"
        header = QLabel(f"{team.team_name} · {status_mark}")
        header.setStyleSheet("font-weight:700;")
        layout.addWidget(header)
        for player in team.players:
            layout.addWidget(self._player_row(player))
        return frame

    def _player_row(self, player: PlayerGameView) -> QWidget:
        hr_text = f"{player.hr_probability*100:.1f}%" if player.hr_probability is not None else "—"
        state = visual_state(player.classification, eligible=player.eligible)
        best_odds = display_quote(player.card, best=True) if player.card is not None else "—"
        label_text = f"{player.batting_order}. {player.player_name}   {hr_text}   {state}   {best_odds}"
        if player.eligible and player.card is not None:
            btn = QPushButton(label_text)
            btn.setFlat(True)
            btn.clicked.connect(lambda:self._on_player_click(player,btn))
            return btn
        label = QLabel(label_text)
        label.setObjectName("muted")
        return label

    def toggle(self) -> None:
        self.is_expanded = not self.is_expanded
        self.body.setVisible(self.is_expanded)

    def set_expanded(self, expanded: bool) -> None:
        self.is_expanded = expanded
        self.body.setVisible(expanded)

    def has_recommended(self) -> bool:
        all_players = list(self.view.away.players) + list(self.view.home.players)
        return any(p.eligible and visual_state(p.classification, eligible=True) == "RECOMENDADO" for p in all_players)


class GamesPageWidget(QScrollArea):
    """POR PARTIDOS -- its own top-level page. Preserves the exact game
    order already produced by analyze_slate() (SlateResult.game_contexts);
    never re-sorts games.
    """

    def __init__(self, store, parent=None) -> None:
        super().__init__(parent)
        self.store = store
        self.setWidgetResizable(True)
        self._current: SlateResult | None = None
        self._cards: list[GameCard] = []

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

        controls = QHBoxLayout()
        self.expand_recommended_btn = QPushButton("EXPANDIR RECOMENDADOS")
        self.expand_recommended_btn.clicked.connect(self.expand_recommended)
        self.collapse_all_btn = QPushButton("COLAPSAR TODOS")
        self.collapse_all_btn.clicked.connect(self.collapse_all)
        controls.addWidget(self.expand_recommended_btn)
        controls.addWidget(self.collapse_all_btn)
        controls.addStretch()
        self._layout.addLayout(controls)

        self.cards_container = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_container)
        self._layout.addWidget(self.cards_container)

        self.detail_panel = DetailSidePanel()
        self._layout.addWidget(self.detail_panel)

        self.empty_label = QLabel("NO HAY JUEGOS PARA MOSTRAR.")
        self.empty_label.setObjectName("muted")
        self.empty_label.hide()
        self._layout.addWidget(self.empty_label)

        self._layout.addStretch()
        self.setWidget(container)

    def _time_service(self) -> GameTimeService:
        name = self.store.get_state("timezone_name", None) if self.store else None
        return GameTimeService(name or GameTimeService.DEFAULT_TIMEZONE)

    def _trigger_refresh(self) -> None:
        if self.refresh_callback:
            self.refresh_btn.setEnabled(False)
            self.refresh_callback()

    def render(self, result: SlateResult) -> None:
        # The refresh (if this page triggered it) is complete once a fresh
        # SlateResult arrives here -- re-enable, no separate "done" signal needed.
        self.refresh_btn.setEnabled(True)
        self._current = result
        for card in self._cards:
            card.deleteLater()
        self._cards = []
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        views = GamePredictionViewBuilder().build(result, self._time_service().timezone_name)
        self.empty_label.setVisible(not views)
        for view in views:
            card = GameCard(view, self._time_service(), self._open_player_detail)
            self._cards.append(card)
            self.cards_layout.addWidget(card)

    def _open_player_detail(self, player: PlayerGameView, origin_widget) -> None:
        self.detail_panel.clear_body()
        state = visual_state(player.classification, eligible=player.eligible)
        hr_text = f"{player.hr_probability*100:.1f}%" if player.hr_probability is not None else "—"
        self.detail_panel.body.addWidget(QLabel(f"HR% {hr_text}"))
        self.detail_panel.body.addWidget(QLabel(f"Estado: {state}"))
        self.detail_panel.body.addWidget(QLabel(f"Classification: {player.classification}"))
        self.detail_panel.body.addWidget(QLabel(f"Confidence: {player.confidence}"))
        if player.card is not None:
            best = display_quote(player.card, best=True)
            self.detail_panel.body.addWidget(QLabel(f"Mejor cuota: {best}"))
            for reason in player.card.prediction.reasons[:3]:
                self.detail_panel.body.addWidget(QLabel("✓ " + reason))
            risk = player.card.prediction.main_risk
            self.detail_panel.body.addWidget(QLabel("Riesgo principal: " + (risk or "Sin advertencias importantes")))
        self.detail_panel.open_panel(player.player_name, origin_widget=origin_widget)

    def expand_recommended(self) -> None:
        for card in self._cards:
            card.set_expanded(card.has_recommended())

    def collapse_all(self) -> None:
        for card in self._cards:
            card.set_expanded(False)
