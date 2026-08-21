from __future__ import annotations

from datetime import timezone

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,QComboBox,QFrame,QGridLayout,QHBoxLayout,QLabel,QMessageBox,QPushButton,
    QScrollArea,QSpinBox,QTableWidget,QTableWidgetItem,QVBoxLayout,QWidget
)

from mlb_hr.domain.enums import MarketPriceLabel, ModelClassification
from mlb_hr.domain.models import PredictionCard, SlateResult
from mlb_hr.ui.workers import FunctionWorker


class TodayWidget(QWidget):
    def __init__(self,analysis_service,store=None,parent=None)->None:
        super().__init__(parent);self.service=analysis_service;self.store=store;self.thread_pool=QThreadPool.globalInstance();self.current:SlateResult|None=None;self._cards:list[PredictionCard]=[]
        self._build()

    def _build(self)->None:
        root=QVBoxLayout(self);root.setContentsMargins(22,18,22,22);root.setSpacing(14)
        top=QHBoxLayout();
        title=QLabel("MLB HR");title.setObjectName("title");top.addWidget(title);top.addStretch()
        self.status=QLabel("Listo");self.status.setObjectName("muted");top.addWidget(self.status)
        self.refresh_btn=QPushButton("ACTUALIZAR");self.refresh_btn.setObjectName("primaryButton");self.refresh_btn.clicked.connect(self.refresh);top.addWidget(self.refresh_btn)
        root.addLayout(top)
        meta=QHBoxLayout();self.health=QLabel("● MODELO —");self.lineups=QLabel("0/0 LINEUPS");self.updated=QLabel("Sin actualizar");
        for x in (self.health,self.lineups,self.updated):meta.addWidget(x)
        meta.addStretch();meta.addWidget(QLabel("Apuesta base:"));self.stake=QComboBox();self.stake.addItems(["$5","$10","$20","$25","$50"]);self.stake.setCurrentText(f"${int(getattr(self.service,'stake',10))}");self.stake.currentTextChanged.connect(self._stake_changed);meta.addWidget(self.stake)
        root.addLayout(meta)
        self.banner=QLabel("");self.banner.setWordWrap(True);self.banner.hide();root.addWidget(self.banner)
        sec=QLabel("MEJORES HR DEL DÍA");sec.setObjectName("section");root.addWidget(sec)
        body=QHBoxLayout();root.addLayout(body,1)
        self.table=QTableWidget(0,7);self.table.setHorizontalHeaderLabels(["#","Jugador","HR","Conf.","FanDuel","Retorno","Acción"]);self.table.verticalHeader().setVisible(False);self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);self.table.setAlternatingRowColors(False);self.table.cellClicked.connect(self._select_row);self.table.horizontalHeader().setStretchLastSection(True);body.addWidget(self.table,3)
        self.detail=QFrame();self.detail.setObjectName("card");self.detail.setMinimumWidth(310);self.detail.setMaximumWidth(400);self.detail_layout=QVBoxLayout(self.detail);self.detail_layout.setContentsMargins(18,18,18,18);self._clear_detail();body.addWidget(self.detail,1)
        combo_label=QLabel("COMBINACIONES");combo_label.setObjectName("section");root.addWidget(combo_label)
        self.combo_row=QHBoxLayout();root.addLayout(self.combo_row)

    def refresh(self)->None:
        self.refresh_btn.setEnabled(False);self.status.setText("Verificando lineups · SP · clima · modelo…")
        worker=FunctionWorker(self.service.analyze_slate);worker.signals.finished.connect(self._loaded);worker.signals.error.connect(self._error);self.thread_pool.start(worker)

    def _loaded(self,result:SlateResult)->None:
        self.current=result;self.refresh_btn.setEnabled(True);self.status.setText("Actualización completa")
        self.health.setText(f"● MODELO {result.model_health.value}");self.health.setObjectName("good" if result.model_health.value=="GREEN" else "warning")
        self.lineups.setText(f"{result.confirmed_lineups}/{result.total_games} JUEGOS LISTOS")
        self.updated.setText("Actualizado "+result.updated_at.astimezone().strftime("%I:%M %p").lstrip("0"))
        self.banner.setText(" · ".join(result.messages));self.banner.setVisible(bool(result.messages));self.banner.setObjectName("warning" if result.messages else "muted")
        self._render_table();self._render_combos()

    def _error(self,msg:str)->None:
        self.refresh_btn.setEnabled(True);self.status.setText("Error al actualizar");QMessageBox.warning(self,"Actualización",msg)

    def _stake_changed(self,text:str)->None:
        try:value=float(text.replace("$",""))
        except ValueError:return
        self.service.stake=value
        if self.store is not None:
            try:self.store.set_state("default_stake",value)
            except Exception:pass
        if self.current:self._render_table();self._render_combos();self._select_row(self.table.currentRow(),0) if self.table.currentRow()>=0 else None

    def _display_cards(self)->list[PredictionCard]:
        if not self.current:return []
        # Normal UX shows actionable candidates first. If model is unvalidated, show highest analyzed rows
        # with PASS so the user can inspect software status without mistaking them for recommendations.
        actionable=[c for c in self.current.cards if c.prediction.classification in {ModelClassification.PRIMARY,ModelClassification.SECONDARY,ModelClassification.WATCH}]
        return (actionable or self.current.cards)[:20]

    def _render_table(self)->None:
        cards=self._display_cards();self.table.setRowCount(len(cards));self._cards=cards
        for r,card in enumerate(cards):
            p=card.prediction;m=card.market
            odds="—" if not m.quote or m.quote.american_odds is None else f"{m.quote.american_odds:+d}"
            payout="—"
            if m.quote and m.quote.american_odds is not None:
                from mlb_hr.domain.math import payout_for_stake
                payout=f"${payout_for_stake(self.service.stake,m.quote.american_odds)[0]:.2f}"
            vals=[str(r+1),p.player.full_name,f"{p.final_hr_probability*100:.1f}%",p.confidence_label.value,odds,payout,p.user_action.value]
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
        title=QLabel(p.player.full_name);title.setObjectName("section");self.detail_layout.insertWidget(0,title)
        game=QLabel(f"{p.team_name} vs {p.opponent_name}"+(f" · {p.game_time.astimezone().strftime('%I:%M %p').lstrip('0')}" if p.game_time else ""));game.setObjectName("muted");self.detail_layout.insertWidget(1,game)
        prob=QLabel(f"HR PROBABILITY\n{p.final_hr_probability*100:.1f}%");prob.setAlignment(Qt.AlignmentFlag.AlignCenter);prob.setStyleSheet("font-size:20px;font-weight:700;padding:10px;");self.detail_layout.insertWidget(2,prob)
        conf=QLabel(f"{p.confidence_label.value} CONFIDENCE · {p.user_action.value}");conf.setAlignment(Qt.AlignmentFlag.AlignCenter);conf.setObjectName("good" if p.user_action.value=="RECOMENDADO" else "warning");self.detail_layout.insertWidget(3,conf)
        odds_text="SIN CUOTA"
        if m.quote and m.quote.american_odds is not None:
            from mlb_hr.domain.math import payout_for_stake
            total,profit=payout_for_stake(self.service.stake,m.quote.american_odds)
            age=""
            if m.quote.last_update:
                mins=max(0,int((m.quote.fetched_at-m.quote.last_update).total_seconds()/60));age=f" · hace {mins} min"
            odds_text=f"FANDUEL {m.quote.american_odds:+d}{age}\n${self.service.stake:.0f} → ${total:.2f} total · +${profit:.2f}\n{m.label.value}"
        od=QLabel(odds_text);od.setAlignment(Qt.AlignmentFlag.AlignCenter);od.setWordWrap(True);self.detail_layout.insertWidget(4,od)
        why=QLabel("¿POR QUÉ?");why.setStyleSheet("font-weight:700;margin-top:8px;");self.detail_layout.insertWidget(5,why)
        idx=6
        for reason in p.reasons[:4]:
            lab=QLabel("✓ "+reason);lab.setWordWrap(True);self.detail_layout.insertWidget(idx,lab);idx+=1
        risk=QLabel("RIESGO PRINCIPAL\n"+("⚠ "+p.main_risk if p.main_risk else "✓ Sin advertencias importantes"));risk.setWordWrap(True);risk.setObjectName("warning" if p.main_risk else "good");self.detail_layout.insertWidget(idx,risk);idx+=1
        manual=QHBoxLayout();spin=QSpinBox();spin.setRange(-10000,10000);spin.setValue(300);manual.addWidget(spin);btn=QPushButton("Cuota manual");manual.addWidget(btn);self.detail_layout.insertLayout(idx,manual);idx+=1
        qualified_for_market=p.classification in {ModelClassification.PRIMARY,ModelClassification.SECONDARY}
        spin.setEnabled(qualified_for_market);btn.setEnabled(qualified_for_market)
        if not qualified_for_market:
            spin.setToolTip("Las cuotas solo se aplican después de que el modelo cualifica al candidato.")
            btn.setToolTip("Las cuotas solo se aplican después de que el modelo cualifica al candidato.")
        def apply():
            val=spin.value();
            if -100<val<100: QMessageBox.information(self,"Cuota","Usa cuota americana >= +100 o <= -100.");return
            try:self.service.apply_manual_odds(card,val);self._render_table();self._show_detail(card)
            except Exception as exc:QMessageBox.warning(self,"Cuota",str(exc))
        btn.clicked.connect(apply)
        copy=QPushButton("COPIAR PICK");copy.clicked.connect(lambda:QGuiApplication.clipboard().setText(f"{p.player.full_name} — HR"+(f" | FanDuel {m.quote.american_odds:+d}" if m.quote and m.quote.american_odds else "")));self.detail_layout.insertWidget(idx,copy)

    def _render_combos(self)->None:
        while self.combo_row.count():
            item=self.combo_row.takeAt(0);w=item.widget();
            if w:w.deleteLater()
        combos={c.kind:c for c in (self.current.combinations if self.current else [])}
        for kind,label in [("BEST_2_MAN","BEST 2-MAN"),("BEST_3_MAN","BEST 3-MAN"),("LONG_SHOT_2_MAN","LONG-SHOT 2-MAN"),("LONG_SHOT_3_MAN","LONG-SHOT 3-MAN")]:
            frame=QFrame();frame.setObjectName("card");lay=QVBoxLayout(frame);title=QLabel(label);title.setStyleSheet("font-weight:700");lay.addWidget(title)
            combo=combos.get(kind)
            if not combo:lay.addWidget(QLabel("NO HAY COMBINACIÓN\nSUFICIENTEMENTE SÓLIDA"))
            else:
                lay.addWidget(QLabel(" + ".join(l.player_name for l in combo.legs)))
                if combo.estimated_decimal_odds:
                    total=self.service.stake*combo.estimated_decimal_odds;lay.addWidget(QLabel(f"Pago estimado · ${self.service.stake:.0f} → ${total:.2f}"))
                else:lay.addWidget(QLabel("SIN CUOTA CONJUNTA"))
            self.combo_row.addWidget(frame)
