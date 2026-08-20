from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView,QFrame,QGridLayout,QHBoxLayout,QLabel,QPushButton,QTableWidget,QTableWidgetItem,QVBoxLayout,QWidget

from mlb_hr.domain.math import payout_for_stake


class HistoryWidget(QWidget):
    def __init__(self,store,parent=None)->None:
        super().__init__(parent);self.store=store;self._build();self.refresh()

    def _build(self)->None:
        root=QVBoxLayout(self);root.setContentsMargins(22,18,22,22);root.setSpacing(14)
        top=QHBoxLayout();t=QLabel("HISTORIAL");t.setObjectName("title");top.addWidget(t);top.addStretch();b=QPushButton("ACTUALIZAR");b.clicked.connect(self.refresh);top.addWidget(b);root.addLayout(top)
        self.metrics=QGridLayout();root.addLayout(self.metrics)
        self.table=QTableWidget(0,7);self.table.setHorizontalHeaderLabels(["Jugador","Clase","HR %","Resultado","FanDuel","P/L","Fecha"]);self.table.verticalHeader().setVisible(False);self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);self.table.horizontalHeader().setStretchLastSection(True);root.addWidget(self.table,1)

    def refresh(self)->None:
        while self.metrics.count():
            item=self.metrics.takeAt(0);w=item.widget();
            if w:w.deleteLater()
        s=self.store.history_summary()
        vals=[
            ("P/L",f"${s['pnl']:+.2f}"),("ROI",f"{s['roi']*100:.1f}%" if s['roi'] is not None else "—"),
            ("Bankroll virtual",f"${s['bankroll']:.2f}"),("Picks resueltos",str(s['n'])),
            ("HR rate",f"{s['actual_hr_rate']*100:.1f}%" if s['actual_hr_rate'] is not None else "—"),("Max drawdown",f"${s['max_drawdown']:.2f}"),
        ]
        for i,(name,val) in enumerate(vals):
            frame=QFrame();frame.setObjectName("card");lay=QVBoxLayout(frame);a=QLabel(name);a.setObjectName("muted");v=QLabel(val);v.setStyleSheet("font-size:20px;font-weight:700");lay.addWidget(a);lay.addWidget(v);self.metrics.addWidget(frame,i//3,i%3)
        rows=self.store.latest_prediction_rows(200);self.table.setRowCount(len(rows))
        for r,row in enumerate(rows):
            result="—"
            if row["actual_hr_binary"] is not None:result="HR ✓" if int(row["actual_hr_binary"]) else "No HR"
            odds=row["odds_at_prediction"];odds_text=f"{int(odds):+d}" if odds is not None else "—"
            pl="—"
            if odds is not None and row["actual_hr_binary"] is not None:
                stake=float(row['reference_stake'] or 10.0)
                _,profit=payout_for_stake(stake,int(odds));pl=f"${profit:+.2f}" if int(row["actual_hr_binary"]) else f"${-stake:+.2f}"
            vals=[row["player_name"],row["classification"],f"{float(row['final_probability'])*100:.1f}%",result,odds_text,pl,str(row["created_at"])[:10]]
            for c,v in enumerate(vals):
                item=QTableWidgetItem(str(v));item.setTextAlignment(Qt.AlignmentFlag.AlignCenter if c!=0 else Qt.AlignmentFlag.AlignVCenter|Qt.AlignmentFlag.AlignLeft);self.table.setItem(r,c,item)
        self.table.resizeColumnsToContents();self.table.horizontalHeader().setStretchLastSection(True)
