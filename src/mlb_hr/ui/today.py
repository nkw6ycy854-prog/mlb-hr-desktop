from __future__ import annotations

from datetime import timezone

from PySide6.QtCore import Qt, QThreadPool, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,QButtonGroup,QFrame,QHBoxLayout,QLabel,QLayout,QLineEdit,QMessageBox,QPushButton,
    QScrollArea,QSizePolicy,QSpinBox,QStackedWidget,QTableWidget,QTableWidgetItem,QVBoxLayout,QWidget
)

from mlb_hr.domain.enums import CombinationFilterStatus, ModelClassification, ModelHealth
from mlb_hr.domain.models import PredictionCard, SlateResult
from mlb_hr.services.favorites import FavoriteAlreadyExists, FavoritesService
from mlb_hr.services.game_time import GameTimeService
from mlb_hr.services.game_views import GamePredictionViewBuilder
from mlb_hr.ui.components import FeedbackButton, ResponsiveGrid
from mlb_hr.ui.presentation import data_health_ok, display_quote, practical_status, quote_display, visible_cards, visual_state, visual_state_display
from mlb_hr.ui.workers import FunctionWorker

_FILTER_TODOS = "TODOS"
_FILTER_GE5 = "GE5"
_FILTER_RECOMENDADOS = "RECOMENDADOS"
_FILTER_FAVORITOS = "FAVORITOS"

_EMPTY_STATE_MESSAGES = {
    _FILTER_GE5: "No hay jugadores con HR% ≥ 5% en este slate.",
    _FILTER_RECOMENDADOS: "No hay jugadores RECOMENDADOS en este slate.",
    _FILTER_FAVORITOS: "No hay favoritos para este slate.",
}


class TodayWidget(QWidget):
    def __init__(self,analysis_service,store=None,parent=None,favorites_service=None)->None:
        super().__init__(parent);self.service=analysis_service;self.store=store;self.thread_pool=QThreadPool.globalInstance();self.current:SlateResult|None=None;self._cards:list[PredictionCard]=[]
        self._on_open_settings=None;self._on_retry=None;self.settlement_trigger=None
        self.favorites_service=favorites_service or (FavoritesService(store) if store is not None else None)
        self._active_filter=_FILTER_TODOS
        self._build()

    def _build(self)->None:
        root=QVBoxLayout(self);root.setContentsMargins(22,18,22,22);root.setSpacing(14)
        top=QHBoxLayout();
        title=QLabel("HOY");title.setObjectName("title");top.addWidget(title);top.addStretch()
        self.status=QLabel("Listo");self.status.setObjectName("muted");top.addWidget(self.status)
        self.refresh_btn=QPushButton("ACTUALIZAR");self.refresh_btn.setObjectName("primaryButton");self.refresh_btn.clicked.connect(self.refresh);top.addWidget(self.refresh_btn)
        root.addLayout(top)
        meta=QHBoxLayout();self.model_status=QLabel("● Modelo —");self.data_status=QLabel("● Datos —");self.lineups=QLabel("0 juegos pregame");self.updated=QLabel("Sin actualizar")
        # This row sits directly in root (not inside any scroll area), so its
        # natural unwrapped width is TodayWidget's actual floor -- word-wrap lets
        # it shrink on a compact window instead of forcing the whole widget wide.
        for x in (self.model_status,self.data_status,self.lineups,self.updated):x.setWordWrap(True);meta.addWidget(x)
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

        self.nav_row_widget=QWidget();nav_row=QHBoxLayout(self.nav_row_widget);nav_row.setContentsMargins(0,0,0,0)
        self.nav_group=QButtonGroup(self);self.nav_group.setExclusive(True)
        self.top15_btn=QPushButton("TOP 15");self.top15_btn.setObjectName("navButton");self.top15_btn.setCheckable(True);self.top15_btn.setChecked(True);self.top15_btn.clicked.connect(lambda:self.view_stack.setCurrentIndex(0));nav_row.addWidget(self.top15_btn)
        self.by_games_btn=QPushButton("POR PARTIDOS");self.by_games_btn.setObjectName("navButton");self.by_games_btn.setCheckable(True);self.by_games_btn.clicked.connect(lambda:self.view_stack.setCurrentIndex(1));nav_row.addWidget(self.by_games_btn)
        for btn in (self.top15_btn,self.by_games_btn):self.nav_group.addButton(btn)
        nav_row.addStretch()
        root.addWidget(self.nav_row_widget)

        self.view_stack=QStackedWidget();root.addWidget(self.view_stack,1)

        top15_page=QWidget();top15_layout=QVBoxLayout(top15_page);top15_layout.setContentsMargins(0,0,0,0);top15_layout.setSpacing(14)
        # SetMinimumSize makes this layout push its true minimum height up onto
        # top15_page itself (not just report it via minimumSizeHint()) -- that is
        # what the wrapping QScrollArea below needs to see in order to enable
        # vertical scrolling instead of silently shrinking the page's content
        # (the detail panel's labels) below their own readable minimum height.
        top15_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)

        dash=QHBoxLayout()
        self.dash_games=QLabel("Juegos —");self.dash_lineups=QLabel("Lineups —");self.dash_recommended=QLabel("Recomendados —")
        self.dash_best_hr=QLabel("Mejor HR% —");self.dash_updated=QLabel("Sin actualizar")
        for lbl in (self.dash_games,self.dash_lineups,self.dash_recommended,self.dash_best_hr,self.dash_updated):
            lbl.setObjectName("muted");lbl.setWordWrap(True);dash.addWidget(lbl)
        dash.addStretch()
        top15_layout.addLayout(dash)

        filter_row=QHBoxLayout()
        self.ranking_section_label=QLabel("MEJORES HR DEL DÍA");self.ranking_section_label.setObjectName("section");filter_row.addWidget(self.ranking_section_label)
        filter_row.addStretch()
        self.filter_group=QButtonGroup(self);self.filter_group.setExclusive(True)
        self.filter_todos_btn=QPushButton("Todos");self.filter_ge5_btn=QPushButton("≥5%")
        self.filter_recomendados_btn=QPushButton("Recomendados");self.filter_favoritos_btn=QPushButton("★ Favoritos")
        for btn,code in (
            (self.filter_todos_btn,_FILTER_TODOS),(self.filter_ge5_btn,_FILTER_GE5),
            (self.filter_recomendados_btn,_FILTER_RECOMENDADOS),(self.filter_favoritos_btn,_FILTER_FAVORITOS),
        ):
            btn.setCheckable(True);btn.clicked.connect(lambda _checked=False,c=code:self._set_filter(c))
            self.filter_group.addButton(btn);filter_row.addWidget(btn)
        self.filter_todos_btn.setChecked(True)
        top15_layout.addLayout(filter_row)

        search_row=QHBoxLayout()
        self.search_box=QLineEdit();self.search_box.setPlaceholderText("Buscar jugador o equipo")
        self.search_box.textChanged.connect(lambda _text:self._render_table())
        search_row.addWidget(self.search_box)
        top15_layout.addLayout(search_row)

        self.empty_state_label=QLabel("");self.empty_state_label.setObjectName("muted");self.empty_state_label.setWordWrap(True);self.empty_state_label.hide()
        top15_layout.addWidget(self.empty_state_label)

        columns=["Jugador","Juego","HR%","Estado","Mejor cuota"]
        # Vertical policy Minimum (not Expanding): in single-column mode, main_pair's
        # grid gives row 0 (this table) its full sizeHint before row 1 (detail) gets
        # anything, so an Expanding table starves detail below its own minimum
        # height on a short window. The table has its own native scrollbar for
        # extra rows, so it doesn't need to claim vertical space detail can't spare.
        self.table=QTableWidget(0,len(columns));self.table.setHorizontalHeaderLabels(columns);self.table.verticalHeader().setVisible(False);self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);self.table.setAlternatingRowColors(False);self.table.cellClicked.connect(self._select_row);self.table.horizontalHeader().setStretchLastSection(True);self.table.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Minimum)
        self.detail=QFrame();self.detail.setObjectName("card");self.detail.setMinimumWidth(310);self.detail.setSizePolicy(QSizePolicy.Policy.Preferred,QSizePolicy.Policy.Expanding);self.detail_layout=QVBoxLayout(self.detail);self.detail_layout.setContentsMargins(18,18,18,18);self._clear_detail()
        self.main_pair=ResponsiveGrid(two_column_min_width=980);self.main_pair.set_widgets([self.table,self.detail]);self.main_pair.layout().setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize);top15_layout.addWidget(self.main_pair,1)
        self.combo_section_label=QLabel("COMBINACIONES");self.combo_section_label.setObjectName("section");top15_layout.addWidget(self.combo_section_label)
        self.combo_grid=ResponsiveGrid(two_column_min_width=760);self._combo_frames:list[QFrame]=[];top15_layout.addWidget(self.combo_grid)
        # QStackedWidget sizes itself to fit the largest minimum-size demand among
        # ALL of its pages, not just the current one -- without this wrapper, once
        # the detail panel is populated with real content, its natural (unwrapped)
        # width leaks into view_stack's shared floor and prevents POR PARTIDOS from
        # shrinking on a compact window even though its own content needs far less
        # space. Wrapping each page in its own QScrollArea (same pattern already
        # used for games_page below, and for every top-level page via
        # components.make_scroll_page) isolates that floor per page.
        top15_scroll=QScrollArea();top15_scroll.setWidgetResizable(True);top15_scroll.setFrameShape(QFrame.Shape.NoFrame)
        top15_scroll.setWidget(top15_page)
        self.view_stack.addWidget(top15_scroll)

        self.games_page=QScrollArea();self.games_page.setWidgetResizable(True)
        games_container=QWidget();self.games_layout=QVBoxLayout(games_container);self.games_layout.setContentsMargins(0,0,0,0);self.games_layout.addStretch()
        self.games_page.setWidget(games_container)
        self.view_stack.addWidget(self.games_page)
        self._game_frames:list[QFrame]=[]

    def refresh(self)->None:
        self.refresh_btn.setEnabled(False);self.status.setText("Verificando lineups · SP · clima · modelo…")
        worker=FunctionWorker(self.service.analyze_slate);worker.signals.finished.connect(self._loaded);worker.signals.error.connect(self._error);self.thread_pool.start(worker)

    def _time_service(self)->GameTimeService:
        name=self.store.get_state("timezone_name",None) if self.store else None
        return GameTimeService(name or GameTimeService.DEFAULT_TIMEZONE)

    def _loaded(self,result:SlateResult)->None:
        self.hide_health_failure()
        self.current=result;self.refresh_btn.setEnabled(True);self.status.setText("Actualización completa")
        self.model_status.setText(f"● Modelo {result.model_health.value}");self.model_status.setObjectName("good" if result.model_health==ModelHealth.GREEN else "warning")
        self.lineups.setText(f"{result.pregame_games} juegos pregame · {result.live_games} en vivo · {result.final_games} finalizados")
        self.updated.setText("Actualizado "+self._time_service().format_time(result.updated_at))
        self.banner.setText(" · ".join(result.messages));self.banner.setVisible(bool(result.messages));self.banner.setObjectName("warning" if result.messages else "muted")
        self._render_dashboard(result)
        self._render_table();self._render_combos();self.render_game_views()
        if self.settlement_trigger:self.settlement_trigger()

    def _render_dashboard(self,result:SlateResult)->None:
        self.dash_games.setText(f"Juegos {result.total_games}")
        self.dash_lineups.setText(f"Lineups confirmados {result.confirmed_lineups} / {result.total_games}")
        recommended=sum(
            1 for c in result.cards
            if visual_state(c.prediction.classification,eligible=c.prediction.classification!=ModelClassification.NOT_ELIGIBLE)=="RECOMENDADO"
        )
        self.dash_recommended.setText(f"Picks recomendados {recommended}")
        best=max((c.prediction.final_hr_probability for c in result.cards),default=None)
        self.dash_best_hr.setText(f"Mejor HR% {best*100:.1f}%" if best is not None else "Mejor HR% —")
        self.dash_updated.setText(self._time_service().format_time(result.updated_at))

    def _error(self,msg:str)->None:
        self.refresh_btn.setEnabled(True);self.status.setText("Error al actualizar");QMessageBox.warning(self,"Actualización",msg)

    def apply_health_report(self,report)->None:
        data_ok=data_health_ok(report)
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
        self.nav_row_widget.setVisible(False);self.view_stack.setVisible(False)

    def hide_health_failure(self)->None:
        self.health_failure_frame.setVisible(False)
        self.ranking_section_label.setVisible(True);self.main_pair.setVisible(True)
        self.combo_section_label.setVisible(True);self.combo_grid.setVisible(True)
        self.nav_row_widget.setVisible(True);self.view_stack.setVisible(True)

    def _handle_open_settings(self)->None:
        if self._on_open_settings:self._on_open_settings()

    def _handle_retry(self)->None:
        if self._on_retry:self._on_retry()

    def _set_filter(self,code:str)->None:
        self._active_filter=code
        self._render_table()

    def _card_eligible(self,card:PredictionCard)->bool:
        return card.prediction.classification!=ModelClassification.NOT_ELIGIBLE

    def _card_visual_state(self,card:PredictionCard)->str:
        return visual_state(card.prediction.classification,eligible=self._card_eligible(card))

    def _favorited_identities(self)->set[tuple[int,int]]:
        if not self.favorites_service:return set()
        return {(int(f["player_id"]),int(f["game_pk"])) for f in self.favorites_service.list_favorites()}

    def _filtered_cards(self)->list[PredictionCard]:
        if not self.current:return []
        all_cards=list(self.current.cards)
        if self._active_filter==_FILTER_GE5:
            base=[c for c in all_cards if c.prediction.final_hr_probability>=0.05]
        elif self._active_filter==_FILTER_RECOMENDADOS:
            base=[c for c in all_cards if self._card_visual_state(c)=="RECOMENDADO"]
        elif self._active_filter==_FILTER_FAVORITOS:
            identities=self._favorited_identities()
            base=[c for c in all_cards if (c.prediction.player.player_id,c.prediction.game_pk) in identities]
        else:
            eligible=[c for c in all_cards if self._card_eligible(c)]
            base=visible_cards(eligible,expanded=False)
        return sorted(base,key=lambda c:c.prediction.final_hr_probability,reverse=True)

    def _matching_cards_for_search(self,query:str)->list[PredictionCard]:
        if not self.current:return []
        q=query.strip().lower()
        matched=[
            c for c in self.current.cards
            if q in c.prediction.player.full_name.lower()
            or q in c.prediction.team_name.lower()
            or q in c.prediction.opponent_name.lower()
        ]
        return sorted(matched,key=lambda c:c.prediction.final_hr_probability,reverse=True)

    def _game_label(self,prediction)->str:
        time_text=self._time_service().format_time(prediction.game_time)
        game=None
        if self.current:
            game=next((g for g in self.current.game_contexts if g.game_pk==prediction.game_pk),None)
        if game and game.away_team_abbr and game.home_team_abbr:
            return f"{game.away_team_abbr} @ {game.home_team_abbr} · {time_text}"
        return f"{prediction.team_name} vs {prediction.opponent_name} · {time_text}"

    def _render_table(self)->None:
        if not self.current:
            self.table.setRowCount(0);self._cards=[];self._clear_detail();self.empty_state_label.hide();return

        query=self.search_box.text().strip()
        filtered=self._filtered_cards()
        filtered_ids={c.prediction.prediction_id for c in filtered}
        if query:
            cards=self._matching_cards_for_search(query)
        else:
            cards=filtered

        self.table.setRowCount(len(cards));self._cards=cards
        for r,card in enumerate(cards):
            p=card.prediction
            state=self._card_visual_state(card)
            if query and p.prediction_id not in filtered_ids:
                state=f"{state} · FUERA DEL FILTRO ACTIVO"
            vals=[p.player.full_name,self._game_label(p),f"{p.final_hr_probability*100:.1f}%",state,display_quote(card,best=True)]
            for c,v in enumerate(vals):
                item=QTableWidgetItem(v);item.setTextAlignment(Qt.AlignmentFlag.AlignCenter if c!=0 else Qt.AlignmentFlag.AlignVCenter|Qt.AlignmentFlag.AlignLeft);self.table.setItem(r,c,item)
        self.table.resizeColumnsToContents();self.table.horizontalHeader().setStretchLastSection(True)

        if not cards:
            if query:
                self.empty_state_label.setText(f"No se encontraron jugadores ni equipos para \"{query}\".")
            else:
                self.empty_state_label.setText(_EMPTY_STATE_MESSAGES.get(self._active_filter,"No hay jugadores para mostrar."))
            self.empty_state_label.show()
        else:
            self.empty_state_label.hide()

        if cards:self.table.selectRow(0);self._show_detail(cards[0])
        else:self._clear_detail()

    def _select_row(self,row:int,_col:int)->None:
        cards=self._cards
        if 0<=row<len(cards):self._show_detail(cards[row])

    def _wipe_detail(self)->None:
        while self.detail_layout.count():
            item=self.detail_layout.takeAt(0);w=item.widget();
            if w:w.deleteLater()

    def _clear_detail(self)->None:
        self._wipe_detail()
        self.detail_layout.addWidget(QLabel("Selecciona un jugador para ver el motivo y el riesgo principal."));self.detail_layout.addStretch()

    def _show_detail(self,card:PredictionCard)->None:
        self._wipe_detail();p=card.prediction;m=card.market
        title=QLabel(p.player.full_name);title.setObjectName("section");self.detail_layout.addWidget(title)
        game=QLabel(self._game_label(p));game.setObjectName("muted");self.detail_layout.addWidget(game)
        prob=QLabel(f"HR%\n{p.final_hr_probability*100:.1f}%");prob.setAlignment(Qt.AlignmentFlag.AlignCenter);prob.setStyleSheet("font-size:20px;font-weight:700;padding:10px;");self.detail_layout.addWidget(prob)
        status=self._card_visual_state(card)
        icon,tone=visual_state_display(status)
        conf=QLabel(f"{icon} {status} · {p.classification.value} · {p.confidence_label.value} CONFIANZA");conf.setAlignment(Qt.AlignmentFlag.AlignCenter);conf.setProperty("tone",tone);self.detail_layout.addWidget(conf)
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

        buttons=QHBoxLayout()
        self.copy_btn=FeedbackButton("COPIAR");self.copy_btn.clicked.connect(lambda:self.copy_pick(card));buttons.addWidget(self.copy_btn)
        favorited=bool(self.favorites_service and self.favorites_service.get_favorite(player_id=p.player.player_id,game_pk=p.game_pk))
        self.favorite_btn=QPushButton("★ GUARDADO" if favorited else "GUARDAR PICK")
        self.favorite_btn.setEnabled(self.favorites_service is not None)
        self.favorite_btn.clicked.connect(lambda:self._toggle_favorite(card))
        buttons.addWidget(self.favorite_btn)
        self.detail_layout.addLayout(buttons)

        self._analysis_expanded=getattr(self,"_analysis_expanded",False)
        self.analysis_btn=QPushButton("OCULTAR ANÁLISIS COMPLETO" if self._analysis_expanded else "VER ANÁLISIS COMPLETO")
        self.analysis_btn.clicked.connect(lambda:self._toggle_analysis(card))
        self.detail_layout.addWidget(self.analysis_btn)
        if self._analysis_expanded:
            self._render_full_analysis(p)

        self.detail_layout.addStretch()

    def _toggle_analysis(self,card:PredictionCard)->None:
        self._analysis_expanded=not getattr(self,"_analysis_expanded",False)
        self._show_detail(card)

    def _render_full_analysis(self,p)->None:
        # Reorganizes/surfaces the same explanatory data V1.1.0 already
        # produces -- never reinterprets it or invents new reasons.
        block=QLabel(
            "ANÁLISIS COMPLETO\n"
            f"Integridad: {p.integrity.value}\n"
            f"Revisión (critic): {p.critic.value}\n"
            f"Acción del modelo: {p.user_action.value}\n"
            f"Modelo {p.model_version} · Features {p.feature_version} · Calibración {p.calibration_version} · Quality gate {p.quality_gate_version}\n"
            +("\n".join(f"⚠ {w.message}" for w in p.warnings) if p.warnings else "Sin advertencias adicionales.")
        )
        block.setWordWrap(True);self.detail_layout.addWidget(block)

    def _toggle_favorite(self,card:PredictionCard)->None:
        if not self.favorites_service:return
        p=card.prediction
        existing=self.favorites_service.get_favorite(player_id=p.player.player_id,game_pk=p.game_pk)
        if existing:
            reply=QMessageBox.question(self,"Eliminar de favoritos",f"¿Eliminar a {p.player.full_name} de Favoritos?")
            if reply==QMessageBox.StandardButton.Yes:
                self.favorites_service.remove_favorite(player_id=p.player.player_id,game_pk=p.game_pk)
        else:
            best_quote=card.best_market.quote if card.best_market else None
            fanduel_quote=card.market.quote if card.market else None
            try:
                self.favorites_service.save_favorite(
                    player_id=p.player.player_id,game_pk=p.game_pk,player_name=p.player.full_name,
                    team_name=p.team_name,opponent_name=p.opponent_name,game_time=p.game_time,
                    hr_probability=p.final_hr_probability,practical_status=self._card_visual_state(card),
                    classification=p.classification.value,confidence_label=p.confidence_label.value,
                    eligible=self._card_eligible(card),
                    best_bookmaker=best_quote.bookmaker if best_quote else None,
                    best_american_odds=best_quote.american_odds if best_quote else None,
                    fanduel_american_odds=fanduel_quote.american_odds if fanduel_quote else None,
                    source_prediction_id=p.prediction_id,
                )
            except FavoriteAlreadyExists:
                pass
        self._show_detail(card)

    def copy_pick(self,card:PredictionCard)->None:
        p=card.prediction;m=card.market
        text=f"{p.player.full_name} — HR"
        if m.quote and m.quote.american_odds is not None:
            text+=f" | FanDuel {m.quote.american_odds:+d}"
        QGuiApplication.clipboard().setText(text)
        self.copy_btn.show_feedback("COPIADO")

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

    def render_game_views(self)->None:
        for frame in self._game_frames:frame.deleteLater()
        while self.games_layout.count():
            item=self.games_layout.takeAt(0)
            if item.widget():item.widget().deleteLater()
        views=GamePredictionViewBuilder().build(self.current,self._time_service().timezone_name) if self.current else ()
        frames=[]
        if not views:
            empty=QLabel("NO HAY JUEGOS PARA MOSTRAR.");empty.setObjectName("muted");self.games_layout.addWidget(empty)
        for view in views:
            frames.append(self._build_game_frame(view))
        for frame in frames:self.games_layout.addWidget(frame)
        self.games_layout.addStretch()
        self._game_frames=frames

    def _build_game_frame(self,view)->QFrame:
        frame=QFrame();frame.setObjectName("card");lay=QVBoxLayout(frame)
        time_text=self._time_service().format_time(view.game_time_utc)
        header=QLabel(f"{view.away.team_name} @ {view.home.team_name} · {time_text}");header.setStyleSheet("font-weight:700");lay.addWidget(header)
        if view.ready:
            status=QLabel("✅ Ambos lineups confirmados");status.setObjectName("good");lay.addWidget(status)
            for team in (view.away,view.home):
                team_label=QLabel(team.team_name);team_label.setStyleSheet("font-weight:700;margin-top:8px;");lay.addWidget(team_label)
                for player in team.players:
                    lay.addWidget(self._player_row_widget(player))
        else:
            for team in (view.away,view.home):
                mark="✅ LINEUP CONFIRMADO" if team.lineup_confirmed else "⏳ ESPERANDO LINEUP"
                lay.addWidget(QLabel(f"{team.team_name}  {mark}"))
            if view.empty_message:
                msg=QLabel(view.empty_message);msg.setWordWrap(True);msg.setObjectName("muted");lay.addWidget(msg)
        return frame

    def _player_row_widget(self,player)->QWidget:
        hr_text=f"{player.hr_probability*100:.1f}%" if player.hr_probability is not None else "—"
        if player.eligible and player.card is not None:
            btn=QPushButton(f"{player.player_name}   {hr_text}   {player.classification}")
            btn.setFlat(True);btn.clicked.connect(lambda:self._show_detail(player.card))
            return btn
        label=QLabel(f"{player.player_name}   {hr_text}   {player.practical_status}")
        label.setObjectName("muted")
        return label
