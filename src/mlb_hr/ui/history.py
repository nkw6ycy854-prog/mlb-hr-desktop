from __future__ import annotations

from datetime import datetime, timezone

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QComboBox, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QPushButton, QScrollArea, QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from mlb_hr.services.daily_accuracy import DailyAccuracyService
from mlb_hr.services.game_time import GameTimeService
from mlb_hr.services.history import HistoryFilter, HistoryService
from mlb_hr.ui.presentation import combination_result_label, format_local_time, player_result_label

PLAYER_TABLE_HEADERS = ["Fecha", "Hora", "Jugador", "HR%", "Estado", "Cuota", "Resultado"]
COMBINATION_TABLE_HEADERS = ["Fecha", "Inicio", "Tipo", "Selecciones", "Filtro", "Cuota", "Resultado", "P/L"]

_PERIOD_BUTTONS = [("TODAY", "HOY"), ("7D", "7 DÍAS"), ("30D", "30 DÍAS"), ("ALL", "TODO")]
_STATUS_OPTIONS = [("ALL", "Todos"), ("RECOMMENDED", "Recomendado"), ("WATCH", "Vigilar"), ("NO_FILTER", "No cumple filtro")]
_RESULT_OPTIONS = [("ALL", "Todos"), ("HR", "HR"), ("NO_HR", "No HR"), ("PENDING", "Pendiente")]
_RESULT_LABELS_BY_MODE = {
    0: ["Todos", "HR", "No HR", "Pendiente"],
    1: ["Todos", "Ganada", "Perdida", "Pendiente"],
}


class HistoryWidget(QWidget):
    def __init__(self, store, parent=None) -> None:
        super().__init__(parent)
        self.store = store
        self.history_service = HistoryService(store)
        self.daily_accuracy_service = DailyAccuracyService(store)
        self.timezone_name = store.get_state("timezone_name", None) or GameTimeService.DEFAULT_TIMEZONE
        self._period = "ALL"
        self._player_records: list = []
        self._combination_records: list = []
        self._daily_accuracy = None
        self._build()
        self.refresh()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 22)
        root.setSpacing(14)

        top = QHBoxLayout()
        title = QLabel("HISTORIAL")
        title.setObjectName("title")
        top.addWidget(title)
        top.addStretch()
        refresh_btn = QPushButton("ACTUALIZAR")
        refresh_btn.setObjectName("primaryButton")
        refresh_btn.clicked.connect(self.refresh)
        top.addWidget(refresh_btn)
        root.addLayout(top)

        mode_row = QHBoxLayout()
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        self.players_btn = QPushButton("JUGADORES")
        self.players_btn.setObjectName("navButton")
        self.players_btn.setCheckable(True)
        self.players_btn.setChecked(True)
        self.players_btn.clicked.connect(lambda: self.set_mode(0))
        self.combinations_btn = QPushButton("COMBINACIONES")
        self.combinations_btn.setObjectName("navButton")
        self.combinations_btn.setCheckable(True)
        self.combinations_btn.clicked.connect(lambda: self.set_mode(1))
        self.hits_today_btn = QPushButton("ACIERTOS HOY")
        self.hits_today_btn.setObjectName("navButton")
        self.hits_today_btn.setCheckable(True)
        self.hits_today_btn.clicked.connect(lambda: self.set_mode(2))
        for btn in (self.players_btn, self.combinations_btn, self.hits_today_btn):
            self.mode_group.addButton(btn)
            mode_row.addWidget(btn)
        mode_row.addStretch()
        root.addLayout(mode_row)

        filters_row = QHBoxLayout()
        self.period_group = QButtonGroup(self)
        self.period_group.setExclusive(True)
        self.period_buttons: dict[str, QPushButton] = {}
        for code, label in _PERIOD_BUTTONS:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.clicked.connect(lambda _checked=False, c=code: self._set_period(c))
            self.period_group.addButton(btn)
            self.period_buttons[code] = btn
            filters_row.addWidget(btn)
        self.period_buttons["ALL"].setChecked(True)

        self.status_combo = QComboBox()
        for code, label in _STATUS_OPTIONS:
            self.status_combo.addItem(label, code)
        self.status_combo.currentIndexChanged.connect(lambda _i: self.refresh())
        filters_row.addWidget(self.status_combo)

        self.result_combo = QComboBox()
        for code, label in _RESULT_OPTIONS:
            self.result_combo.addItem(label, code)
        self.result_combo.currentIndexChanged.connect(lambda _i: self.refresh())
        filters_row.addWidget(self.result_combo)
        filters_row.addStretch()
        root.addLayout(filters_row)

        self.metrics = QGridLayout()
        root.addLayout(self.metrics)

        body = QHBoxLayout()
        root.addLayout(body, 1)

        self.mode_stack = QStackedWidget()
        self.players_table = QTableWidget(0, len(PLAYER_TABLE_HEADERS))
        self.players_table.setHorizontalHeaderLabels(PLAYER_TABLE_HEADERS)
        self.players_table.verticalHeader().setVisible(False)
        self.players_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.players_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.players_table.cellClicked.connect(self._select_player_row)
        self.players_table.horizontalHeader().setStretchLastSection(True)

        self.combinations_table = QTableWidget(0, len(COMBINATION_TABLE_HEADERS))
        self.combinations_table.setHorizontalHeaderLabels(COMBINATION_TABLE_HEADERS)
        self.combinations_table.verticalHeader().setVisible(False)
        self.combinations_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.combinations_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.combinations_table.cellClicked.connect(self._select_combination_row)
        self.combinations_table.horizontalHeader().setStretchLastSection(True)

        self.hits_today_page = QScrollArea()
        self.hits_today_page.setWidgetResizable(True)
        hits_today_container = QWidget()
        self.hits_today_layout = QVBoxLayout(hits_today_container)
        self.hits_today_layout.setContentsMargins(0, 0, 0, 0)
        self.hits_today_page.setWidget(hits_today_container)
        self._hits_today_frames: list[QFrame] = []

        self.mode_stack.addWidget(self.players_table)
        self.mode_stack.addWidget(self.combinations_table)
        self.mode_stack.addWidget(self.hits_today_page)
        body.addWidget(self.mode_stack, 3)

        self.detail = QFrame()
        self.detail.setObjectName("card")
        self.detail.setMinimumWidth(280)
        self.detail_layout = QVBoxLayout(self.detail)
        self.detail_layout.setContentsMargins(18, 18, 18, 18)
        self._clear_detail()
        body.addWidget(self.detail, 1)

    def set_mode(self, index: int) -> None:
        self.mode_stack.setCurrentIndex(index)
        if index in _RESULT_LABELS_BY_MODE:
            self._apply_result_labels(index)
        self._clear_detail()
        self.refresh()

    def _apply_result_labels(self, mode_index: int) -> None:
        for i, label in enumerate(_RESULT_LABELS_BY_MODE[mode_index]):
            self.result_combo.setItemText(i, label)

    def _set_period(self, code: str) -> None:
        self._period = code
        self.refresh()

    def current_filter(self) -> HistoryFilter:
        return HistoryFilter(
            period=self._period,
            status=self.status_combo.currentData(),
            result=self.result_combo.currentData(),
        )

    def _clear_detail(self) -> None:
        while self.detail_layout.count():
            item = self.detail_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self.detail_layout.addWidget(QLabel("Selecciona una fila para ver el detalle."))
        self.detail_layout.addStretch()

    def refresh(self) -> None:
        now = datetime.now(timezone.utc)
        self.timezone_name = self.store.get_state("timezone_name", None) or GameTimeService.DEFAULT_TIMEZONE
        filter_ = self.current_filter()
        self._player_records = self.history_service.player_records(filter_, now)
        self._combination_records = self.history_service.combination_records(filter_, now)
        local_today = GameTimeService(self.timezone_name).localize(now).date()
        self._daily_accuracy = self.daily_accuracy_service.for_date(local_today, self.timezone_name)
        self._render_metrics()
        self._render_players_table()
        self._render_combinations_table()
        self.render_hits_today()

    def _render_metrics(self) -> None:
        while self.metrics.count():
            item = self.metrics.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        if self.mode_stack.currentIndex() == 2:
            return  # ACIERTOS HOY renders its own summary inside render_hits_today()
        if self.mode_stack.currentIndex() == 0:
            summary = HistoryService.summarize_players(self._player_records)
            vals = [
                ("Analizados", str(summary["analyzed"])),
                ("Recomendados", str(summary["recommended"])),
                ("Aciertos", str(summary["hits"])),
                ("Hit rate", f"{summary['hit_rate']*100:.1f}%" if summary["hit_rate"] is not None else "—"),
                ("P/L", f"${summary['pnl']:+.2f}"),
                ("ROI", f"{summary['roi']*100:.1f}%" if summary["roi"] is not None else "—"),
            ]
        else:
            summary = HistoryService.summarize_combinations(self._combination_records)
            vals = [
                ("Analizadas", str(summary["analyzed"])),
                ("Recomendadas", str(summary["recommended"])),
                ("Aciertos", str(summary["hits"])),
                ("Hit rate", f"{summary['hit_rate']*100:.1f}%" if summary["hit_rate"] is not None else "—"),
                ("P/L", f"${summary['pnl']:+.2f}"),
            ]
        for i, (name, val) in enumerate(vals):
            frame = QFrame()
            frame.setObjectName("card")
            lay = QVBoxLayout(frame)
            a = QLabel(name)
            a.setObjectName("muted")
            v = QLabel(val)
            v.setStyleSheet("font-size:18px;font-weight:700")
            lay.addWidget(a)
            lay.addWidget(v)
            self.metrics.addWidget(frame, i // 3, i % 3)

    def _render_players_table(self) -> None:
        records = self._player_records
        self.players_table.setRowCount(len(records))
        for r, rec in enumerate(records):
            date_text = rec.created_at.date().isoformat() if rec.created_at else "—"
            time_text = format_local_time(rec.game_time, self.timezone_name)
            odds_text = f"{int(rec.odds_at_prediction):+d}" if rec.odds_at_prediction is not None else "—"
            vals = [date_text, time_text, rec.player_name, f"{rec.final_probability*100:.1f}%", rec.status, odds_text, player_result_label(rec.result)]
            for c, v in enumerate(vals):
                item = QTableWidgetItem(str(v))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter if c not in {2} else Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                self.players_table.setItem(r, c, item)
        self.players_table.resizeColumnsToContents()
        self.players_table.horizontalHeader().setStretchLastSection(True)

    def _render_combinations_table(self) -> None:
        records = self._combination_records
        self.combinations_table.setRowCount(len(records))
        for r, rec in enumerate(records):
            date_text = rec.created_at.date().isoformat() if rec.created_at else "—"
            start_text = format_local_time(rec.start_time, self.timezone_name)
            selections = " + ".join(leg.player_name for leg in rec.legs)
            odds_text = f"{rec.estimated_decimal_odds:.2f}" if rec.estimated_decimal_odds else "—"
            pl_text = f"${rec.pnl:+.2f}" if rec.pnl is not None else "—"
            vals = [date_text, start_text, rec.kind, selections, rec.filter_status, odds_text, combination_result_label(rec.result), pl_text]
            for c, v in enumerate(vals):
                item = QTableWidgetItem(str(v))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter if c not in {3} else Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                self.combinations_table.setItem(r, c, item)
        self.combinations_table.resizeColumnsToContents()
        self.combinations_table.horizontalHeader().setStretchLastSection(True)

    def _select_player_row(self, row: int, _col: int) -> None:
        if 0 <= row < len(self._player_records):
            self._show_player_detail(self._player_records[row])

    def _select_combination_row(self, row: int, _col: int) -> None:
        if 0 <= row < len(self._combination_records):
            self._show_combination_detail(self._combination_records[row])

    def _show_player_detail(self, record) -> None:
        self._clear_detail()
        title = QLabel(record.player_name)
        title.setObjectName("section")
        self.detail_layout.insertWidget(0, title)
        prob = QLabel(f"Predicción original: {record.final_probability*100:.1f}%")
        self.detail_layout.insertWidget(1, prob)
        classification = QLabel(f"Clasificación: {record.classification}")
        self.detail_layout.insertWidget(2, classification)
        odds_text = f"{int(record.odds_at_prediction):+d}" if record.odds_at_prediction is not None else "SIN CUOTA"
        odds = QLabel(f"Cuota registrada: {odds_text}")
        self.detail_layout.insertWidget(3, odds)
        result = QLabel(f"Resultado: {player_result_label(record.result)}")
        self.detail_layout.insertWidget(4, result)

    def _show_combination_detail(self, record) -> None:
        self._clear_detail()
        title = QLabel(record.kind)
        title.setObjectName("section")
        self.detail_layout.insertWidget(0, title)
        idx = 1
        for leg in record.legs:
            time_text = format_local_time(leg.game_time, self.timezone_name)
            lab = QLabel(f"{leg.player_name} · {leg.classification} · {player_result_label(leg.result)} · {time_text}")
            self.detail_layout.insertWidget(idx, lab)
            idx += 1
        result = QLabel(f"Resultado: {combination_result_label(record.result)}")
        self.detail_layout.insertWidget(idx, result)
        idx += 1
        pl_text = f"${record.pnl:+.2f}" if record.pnl is not None else "—"
        pl = QLabel(f"P/L: {pl_text}")
        self.detail_layout.insertWidget(idx, pl)

    def render_hits_today(self) -> None:
        for frame in self._hits_today_frames:
            frame.deleteLater()
        while self.hits_today_layout.count():
            item = self.hits_today_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        frames: list[QFrame] = []
        result = self._daily_accuracy
        if result is None:
            self.hits_today_layout.addStretch()
            self._hits_today_frames = frames
            return

        summary = result.summary
        tz = GameTimeService(self.timezone_name)

        header = QLabel(f"Jugadores acertados: {summary.player_hits}")
        header.setStyleSheet("font-size:16px;font-weight:700")
        self.hits_today_layout.addWidget(header)
        combo_header = QLabel(f"Combinaciones ganadas: {summary.combo_wins}")
        combo_header.setStyleSheet("font-size:16px;font-weight:700")
        self.hits_today_layout.addWidget(combo_header)

        hit_players = [p for p in result.players if p.result == "HR"]
        won_combos = [c for c in result.combinations if c.result == "HR"]

        if not hit_players and not won_combos:
            empty = QLabel("Todavía no hay predicciones acertadas para esta fecha.")
            empty.setObjectName("muted")
            self.hits_today_layout.addWidget(empty)
        else:
            if hit_players:
                section = QLabel("JUGADORES")
                section.setStyleSheet("font-weight:700;margin-top:8px;")
                self.hits_today_layout.addWidget(section)
            for player in hit_players:
                frame = QFrame()
                frame.setObjectName("card")
                lay = QVBoxLayout(frame)
                time_text = tz.format_time(player.game_time_utc)
                odds_text = f"{int(player.odds_at_prediction):+d}" if player.odds_at_prediction is not None else "—"
                lay.addWidget(QLabel(f"{player.player_name} — {player.team_name} vs {player.opponent_name} · {time_text}"))
                lay.addWidget(QLabel(f"{player.probability*100:.1f}% · {player.classification} · Cuota {odds_text}"))
                status_label = QLabel("✅ ACERTADO / HR")
                status_label.setObjectName("good")
                lay.addWidget(status_label)
                frames.append(frame)
                self.hits_today_layout.addWidget(frame)

            if won_combos:
                section = QLabel("COMBINACIONES")
                section.setStyleSheet("font-weight:700;margin-top:8px;")
                self.hits_today_layout.addWidget(section)
            for combo in won_combos:
                frame = QFrame()
                frame.setObjectName("card")
                lay = QVBoxLayout(frame)
                lay.addWidget(QLabel(f"{combo.kind} · {combo.filter_status}"))
                for leg in combo.legs:
                    leg_time = tz.format_time(leg.game_time)
                    lay.addWidget(QLabel(f"  {leg.player_name} · {leg_time}"))
                odds_text = f"{combo.odds:.2f}" if combo.odds else "—"
                pl_text = f"${combo.pnl:+.2f}" if combo.pnl is not None else "—"
                status_label = QLabel(f"✅ {combination_result_label(combo.result)} · Cuota {odds_text} · P/L {pl_text}")
                status_label.setObjectName("good")
                lay.addWidget(status_label)
                frames.append(frame)
                self.hits_today_layout.addWidget(frame)

        if summary.player_pending or summary.combo_pending:
            pending = QLabel(f"Pendientes: {summary.player_pending} jugador(es), {summary.combo_pending} combinación(es).")
            pending.setObjectName("muted")
            self.hits_today_layout.addWidget(pending)

        self.hits_today_layout.addStretch()
        self._hits_today_frames = frames
