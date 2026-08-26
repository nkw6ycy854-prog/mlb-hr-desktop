from __future__ import annotations

from datetime import timezone

from PySide6.QtCore import Qt, QThreadPool, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,QFrame,QHBoxLayout,QLabel,QMessageBox,QPushButton,
    QSizePolicy,QSpinBox,QTableWidget,QTableWidgetItem,QVBoxLayout,QWidget
)

from mlb_hr.domain.enums import CombinationFilterStatus, ModelClassification, ModelHealth
from mlb_hr.domain.models import PredictionCard, SlateResult
from mlb_hr.ui.components import ResponsiveGrid
from mlb_hr.ui.presentation import display_quote, practical_status, quote_display, visible_cards
from mlb_hr.ui.workers import FunctionWorker


class TodayWidget(QWidget):
    def __init__(self,analysis_service,store=None,parent=None)->None:
        super().__init__(parent);self.service=analysis_service;self.store=store;self.thread_pool=QThreadPool.globalInstance();self.current:SlateResult|None=None;self._cards:list[PredictionCard]=[]
        self._on_open_settings=None;self._on_retry=None
        self._build()

    def _build(self)->None:
        root=QVBoxLayout(self);root.setContentsMargins(22,18,22,22);root.setSpacing(14)
        top=QHBoxLayout();
        title=QLabel("HOY");title.setObjectName("title");top.addWidget(title);top.addStretch()
        self.status=QLabel("Listo");self.status.setObjectName("muted");top.addWidget(self.status)
        self.refresh_btn=QPushButton("ACTUALIZAR");self.refresh_btn.setObjectName("primaryButton");self.refresh_btn.clicked.connect(self.refresh);top.addWidget(self.refresh_btn)
        root.addLayout(top)
        meta=QHBoxLayout();self.model_status=QLabel("● Modelo —");self.data_status=QLabel("● Datos —");self.lineups=QLabel("0/0 juegos listos");self.updated=QLabel("Sin actualizar")
        for x in (self.model_status,self.data_status,self.lineups,self.updated):meta.addWidget(x)
        meta.addStretch()
        root.addLayout(meta)
        self.banner=QLabel("");self.banner.setWordWrap(True);self.banner.hide();root.addWidget(self.banner)

        self.health_failure_frame=QFrame();self.health_failure_frame.setObjectName("card");self.health_failure_frame.hide()
        hf_layout=QVBoxLayout(self.health_failure_frame)
        self.health_title=QLabel("");self.health_title.setObjectName("section");hf_layout.addWidget(self.health_title)
        self.health_detail=QLabel("");self.health_detail.setWordWrap(True);hf_layout.addWidget(self.health_detail)
        hf_buttons=QHBoxLayout()
        self.health_open_settings_btn=QPushButton("ABRIR AJUSTES");self.health_open_settings_btn.clicked.connect(self._handle_open_settings);hf_buttons.addWidget(self.health_open_settings_btn)
        self.health_retry_btn=QPushButton("REINTENTAR");self.health_retry_btn.setObjectName("primaryButton");self.health_retry_btn.clicked.connect(self._handle_retry);hf_buttons.addWidget(self.health_retry_btn)
        hf_layout.addLayout(hf_buttons)
        root.addWidget(self.health_failure_frame)

        sec_row=QHBoxLayout()
        self.ranking_section_label=QLabel("MEJORES HR DEL DÍA");self.ranking_section_label.setObjectName("section");sec_row.addWidget(self.ranking_section_label);sec_row.addStretch()
        self.expanded=False
        self.view_all_btn=QPushButton("VER TODOS");self.view_all_btn.clicked.connect(self.toggle_all);sec_row.addWidget(self.view_all_btn)
        root.addLayout(sec_row)
        columns=["#","Jugador","HR%","Clasificación","Confianza","Mejor cuota","FanDuel","Estado"]
        self.table=QTableWidget(0,len(columns));self.table.setHorizontalHeaderLabels(columns);self.table.verticalHeader().setVisible(False);self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);self.table.setAlternatingRowColors(False);self.table.cellClicked.connect(self._select_row);self.table.horizontalHeader().setStretchLastSection(True);self.table.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Expanding)
        self.detail=QFrame();self.detail.setObjectName("card");self.detail.setMinimumWidth(310);self.detail.setSizePolicy(QSizePolicy.Policy.Preferred,QSizePolicy.Policy.Expanding);self.detail_layout=QVBoxLayout(self.detail);self.detail_layout.setContentsMargins(18,18,18,18);self._clear_detail()
        self.main_pair=ResponsiveGrid(two_column_min_width=980);self.main_pair.set_widgets([self.table,self.detail]);root.addWidget(self.main_pair,1)
        self.combo_section_label=QLabel("COMBINACIONES");self.combo_section_label.setObjectName("section");root.addWidget(self.combo_section_label)
        self.combo_grid=ResponsiveGrid(two_column_min_width=760);self._combo_frames:list[QFrame]=[];root.addWidget(self.combo_grid)

    def refresh(self)->None:
        self.refresh_btn.setEnabled(False);self.status.setText("Verificando lineups · SP · clima · modelo…")
        worker=FunctionWorker(self.service.analyze_slate);worker.signals.finished.connect(self._loaded);worker.signals.error.connect(self._error);self.thread_pool.start(worker)

    def _loaded(self,result:SlateResult)->None:
        self.hide_health_failure()
        self.current=result;self.refresh_btn.setEnabled(True);self.status.setText("Actualización completa")
        self.model_status.setText(f"● Modelo {result.model_health.value}");self.model_status.setObjectName("good" if result.model_health==ModelHealth.GREEN else "warning")
        self.lineups.setText(f"{result.confirmed_lineups}/{result.total_games} juegos listos")
        self.updated.setText("Actualizado "+result.updated_at.astimezone().strftime("%I:%M %p").lstrip("0"))
        self.banner.setText(" · ".join(result.messages));self.banner.setVisible(bool(result.messages));self.banner.setObjectName("warning" if result.messages else "muted")
        self._render_table();self._render_combos()

    def _error(self,msg:str)->None:
        self.refresh_btn.setEnabled(True);self.status.setText("Error al actualizar");QMessageBox.warning(self,"Actualización",msg)

    def apply_health_report(self,report)->None:
        statcast_item=next((i for i in report.items if i.key=="statcast"),None)
        db_item=next((i for i in report.items if i.key=="database"),None)
        data_ok=(statcast_item is None or statcast_item.state=="OK") and (db_item is None or db_item.state=="OK")
        self.data_status.setText(f"● Datos {'OK' if data_ok else 'ERROR'}")
        self.data_status.setObjectName("good" if data_ok else "warning")

    def show_health_failure(self,report,*,on_open_settings,on_retry)->None:
        self._on_open_settings=on_open_settings;self._on_retry=on_retry
        self.apply_health_report(report)
        failing=[item for item in report.items if item.state=="ERROR"]
        first=failing[0] if failing else None
        title_text=f"⚠ {first.label.upper()} NO DISPONIBLE" if first else "⚠ PROBLEMA CRÍTICO DETECTADO"
        detail_text=first.detail if first else "Se detectó un problema crítico de runtime."
        self.health_title.setText(title_text);self.health_detail.setText(detail_text)
        self.health_failure_frame.setVisible(True)
        self.ranking_section_label.setVisible(False);self.main_pair.setVisible(False)
        self.combo_section_label.setVisible(False);self.combo_grid.setVisible(False)

    def hide_health_failure(self)->None:
        self.health_failure_frame.setVisible(False)
        self.ranking_section_label.setVisible(True);self.main_pair.setVisible(True)
        self.combo_section_label.setVisible(True);self.combo_grid.setVisible(True)

    def _handle_open_settings(self)->None:
        if self._on_open_settings:self._on_open_settings()

    def _handle_retry(self)->None:
        if self._on_retry:self._on_retry()

    def toggle_all(self)->None:
        self.expanded=not self.expanded
        self.view_all_btn.setText("VER TOP 15" if self.expanded else "VER TODOS")
        self._render_table()

    def _render_table(self)->None:
        if not self.current:
            self.table.setRowCount(0);self._cards=[];self._clear_detail();return
        eligible=[c for c in self.current.cards if c.prediction.classification!=ModelClassification.NOT_ELIGIBLE]
        cards=visible_cards(eligible,expanded=self.expanded)
        self.table.setRowCount(len(cards));self._cards=cards
        for r,card in enumerate(cards):
            p=card.prediction
            vals=[str(r+1),p.player.full_name,f"{p.final_hr_probability*100:.1f}%",p.classification.value,p.confidence_label.value,display_quote(card,best=True),display_quote(card,best=False),practical_status(p.classification)]
            for c,v in enumerate(vals):
                item=QTableWidgetItem(v);item.setTextAlignment(Qt.AlignmentFlag.AlignCenter if c!=1 else Qt.AlignmentFlag.AlignVCenter|Qt.AlignmentFlag.AlignLeft);self.table.setItem(r,c,item)
        self.table.resizeColumnsToContents();self.table.horizontalHeader().setStretchLastSection(True)
        if cards:self.table.selectRow(0);self._show_detail(cards[0])
        else:self._clear_detail()

    def _select_row(self,row:int,_col:int)->None:
        cards=self._cards
        if 0<=row<len(cards):self._show_detail(cards[row])

    def _clear_detail(self)->None:
        while self.detail_layout.count():
            item=self.detail_layout.takeAt(0);w=item.widget();
            if w:w.deleteLater()
        self.detail_layout.addWidget(QLabel("Selecciona un jugador para ver el motivo y el riesgo principal."));self.detail_layout.addStretch()

    def _show_detail(self,card:PredictionCard)->None:
        self._clear_detail();p=card.prediction;m=card.market
        title=QLabel(p.player.full_name);title.setObjectName("section");self.detail_layout.addWidget(title)
        time_text=p.game_time.astimezone().strftime('%I:%M %p').lstrip('0') if p.game_time else "—"
        game=QLabel(f"{p.team_name} vs {p.opponent_name} · {time_text}");game.setObjectName("muted");self.detail_layout.addWidget(game)
        prob=QLabel(f"HR%\n{p.final_hr_probability*100:.1f}%");prob.setAlignment(Qt.AlignmentFlag.AlignCenter);prob.setStyleSheet("font-size:20px;font-weight:700;padding:10px;");self.detail_layout.addWidget(prob)
        status=practical_status(p.classification)
        conf=QLabel(f"{status} · {p.classification.value} · {p.confidence_label.value} CONFIANZA");conf.setAlignment(Qt.AlignmentFlag.AlignCenter);conf.setObjectName("good" if status=="RECOMENDADO" else "warning");self.detail_layout.addWidget(conf)
        qd=quote_display(card)
        best=QLabel(qd.best_text);best.setAlignment(Qt.AlignmentFlag.AlignCenter);self.detail_layout.addWidget(best)
        if qd.fanduel_text:
            fanduel=QLabel(qd.fanduel_text);fanduel.setAlignment(Qt.AlignmentFlag.AlignCenter);self.detail_layout.addWidget(fanduel)
        if p.reasons:
            why=QLabel("¿POR QUÉ?");why.setStyleSheet("font-weight:700;margin-top:8px;");self.detail_layout.addWidget(why)
            for reason in p.reasons[:4]:
                lab=QLabel("✓ "+reason);lab.setWordWrap(True);self.detail_layout.addWidget(lab)
        risk=QLabel("RIESGO PRINCIPAL\n"+("⚠ "+p.main_risk if p.main_risk else "✓ Sin advertencias importantes"));risk.setWordWrap(True);risk.setObjectName("warning" if p.main_risk else "good");self.detail_layout.addWidget(risk)

        qualified=p.classification in {ModelClassification.PRIMARY,ModelClassification.SECONDARY}
        missing_fanduel=m.quote is None
        if qualified and missing_fanduel:
            manual=QWidget();manual_layout=QHBoxLayout(manual);manual_layout.setContentsMargins(0,0,0,0)
            spin=QSpinBox();spin.setRange(-10000,10000);spin.setValue(300);manual_layout.addWidget(spin)
            apply_btn=QPushButton("Cuota manual");manual_layout.addWidget(apply_btn)
            def apply():
                val=spin.value()
                if -100<val<100:QMessageBox.information(self,"Cuota","Usa cuota americana >= +100 o <= -100.");return
                try:self.service.apply_manual_odds(card,val);self._render_table();self._show_detail(card)
                except Exception as exc:QMessageBox.warning(self,"Cuota",str(exc))
            apply_btn.clicked.connect(apply)
            self.detail_layout.addWidget(manual)

        self.copy_btn=QPushButton("COPIAR PICK");self.copy_btn.clicked.connect(lambda:self.copy_pick(card));self.detail_layout.addWidget(self.copy_btn)
        self.detail_layout.addStretch()

    def copy_pick(self,card:PredictionCard)->None:
        p=card.prediction;m=card.market
        text=f"{p.player.full_name} — HR"
        if m.quote and m.quote.american_odds is not None:
            text+=f" | FanDuel {m.quote.american_odds:+d}"
        QGuiApplication.clipboard().setText(text)
        self.copy_btn.setText("COPIADO ✓")
        QTimer.singleShot(1500,lambda:self.copy_btn.setText("COPIAR PICK"))

    def _render_combos(self)->None:
        for frame in self._combo_frames:frame.deleteLater()
        combos={c.kind:c for c in (self.current.combinations if self.current else [])}
        frames=[]
        for kind,label in [("BEST_2_MAN","BEST 2-MAN"),("BEST_3_MAN","BEST 3-MAN"),("LONG_SHOT_2_MAN","LONG-SHOT 2-MAN"),("LONG_SHOT_3_MAN","LONG-SHOT 3-MAN")]:
            frame=QFrame();frame.setObjectName("card");lay=QVBoxLayout(frame);title=QLabel(label);title.setStyleSheet("font-weight:700");lay.addWidget(title)
            combo=combos.get(kind)
            if not combo:
                lay.addWidget(QLabel("NO HAY SUFICIENTES JUGADORES ANALIZADOS"))
            else:
                qualified=combo.filter_status==CombinationFilterStatus.QUALIFIED
                status_text="✅ CUMPLE FILTRO · RECOMENDADA" if qualified else "⚠ NO CUMPLE FILTRO · ALTO RIESGO"
                status_label=QLabel(status_text);status_label.setObjectName("good" if qualified else "warning");lay.addWidget(status_label)
                for leg in combo.legs:
                    lay.addWidget(QLabel(f"{leg.player_name} · {leg.classification.value}"))
                if combo.estimated_decimal_odds:
                    total=self.service.stake*combo.estimated_decimal_odds;lay.addWidget(QLabel(f"Pago estimado · ${self.service.stake:.0f} → ${total:.2f}"))
                else:lay.addWidget(QLabel("SIN CUOTA CONJUNTA"))
            frames.append(frame)
        self._combo_frames=frames
        self.combo_grid.set_widgets(frames)
