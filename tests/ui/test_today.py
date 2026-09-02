from datetime import datetime, timezone
from types import SimpleNamespace

from PySide6.QtWidgets import QApplication, QLabel

from mlb_hr.domain.enums import (
    CombinationFilterStatus,
    ConfidenceLabel,
    CriticVerdict,
    GameState,
    IntegrityStatus,
    MarketPriceLabel,
    ModelClassification,
    ModelHealth,
    SlateQuality,
    UserActionLabel,
)
from mlb_hr.domain.models import (
    Combination,
    CombinationLeg,
    GameContext,
    LineupEntry,
    MarketDecision,
    PlayerRef,
    Prediction,
    PredictionCard,
    ProbabilityDistribution,
    SlateResult,
    TeamLineup,
    VenueRef,
)
from mlb_hr.ui.style import APP_STYLESHEET
from mlb_hr.ui.today import TodayWidget


def app():
    return QApplication.instance() or QApplication([])


def _make_card(index: int, probability: float, *, classification: ModelClassification = ModelClassification.PRIMARY) -> PredictionCard:
    player = PlayerRef(player_id=index, full_name=f"Player {index}")
    pitcher = PlayerRef(player_id=9000 + index, full_name="Opposing Pitcher")
    distribution = ProbabilityDistribution(
        point=probability, p10=probability, p50=probability, p90=probability,
        interval_width=0.0, stability_score=1.0,
    )
    prediction = Prediction(
        prediction_id=f"pred-{index}",
        snapshot_id="snap-1",
        game_pk=100 + index,
        player=player,
        opposing_pitcher=pitcher,
        team_name="Team A",
        opponent_name="Team B",
        game_time=datetime(2026, 8, 26, 19, 5, tzinfo=timezone.utc),
        final_hr_probability=probability,
        raw_hr_probability=probability,
        matchup_score=0.5,
        grade="B",
        reliability=0.9,
        confidence_score=0.8,
        confidence_label=ConfidenceLabel.HIGH,
        distribution=distribution,
        classification=classification,
        user_action=UserActionLabel.RECOMMENDED,
        integrity=IntegrityStatus.PASS,
        critic=CriticVerdict.PASS,
        reasons=["Strong matchup"],
        main_risk=None,
        warnings=[],
        model_version="V1.0.0",
        feature_version="1",
        calibration_version="1",
        quality_gate_version="1",
        model_health=ModelHealth.GREEN,
    )
    market = MarketDecision(quote=None, label=MarketPriceLabel.NO_ODDS)
    return PredictionCard(prediction=prediction, market=market)


def _make_service():
    return SimpleNamespace(stake=10.0)


def _make_combo(kind, filter_status, legs):
    return Combination(
        combination_id=f"combo-{kind}",
        kind=kind,
        legs=legs,
        model_probability_proxy=0.05,
        robustness=80.0,
        filter_status=filter_status,
        actual_parlay_american_odds=None,
        estimated_decimal_odds=None,
        warnings=[],
    )


def _combo_frame_texts(widget) -> str:
    texts = []
    for frame in widget._combo_frames:
        for label in frame.findChildren(QLabel):
            texts.append(label.text())
    return "\n".join(texts)


def test_today_defaults_to_top_15_under_the_todos_filter():
    app()
    widget = TodayWidget(_make_service(), None)
    cards = [_make_card(i, 1 - i / 100) for i in range(20)]
    result = SlateResult(
        cards=cards,
        combinations=[],
        slate_quality=SlateQuality.GREEN,
        model_health=ModelHealth.GREEN,
        confirmed_lineups=15,
        total_games=15,
        updated_at=datetime.now(timezone.utc),
    )
    widget._loaded(result)

    assert widget.filter_todos_btn.isChecked() is True
    assert widget.table.rowCount() == 15
    assert widget.table.horizontalHeaderItem(3).text() == "Estado"


def test_ge5_filter_searches_the_whole_slate_beyond_top_15():
    app()
    widget = TodayWidget(_make_service(), None)
    cards = [_make_card(i, 0.20 - i * 0.005) for i in range(20)]  # all >= 0.05
    result = SlateResult(
        cards=cards, combinations=[], slate_quality=SlateQuality.GREEN, model_health=ModelHealth.GREEN,
        confirmed_lineups=15, total_games=15, updated_at=datetime.now(timezone.utc),
    )
    widget._loaded(result)

    widget.filter_ge5_btn.click()

    assert widget.table.rowCount() == 20


def test_today_shows_watch_and_no_bet_when_no_primary_secondary_exist():
    # Reproduces the exact reported scenario: a confirmed slate with zero
    # PRIMARY/SECONDARY candidates but several WATCH/NO_BET ones. HOY must never
    # go empty in this case -- only NOT_ELIGIBLE rows may be omitted.
    app()
    widget = TodayWidget(_make_service(), None)
    cards = [
        _make_card(0, 0.20, classification=ModelClassification.WATCH),
        _make_card(1, 0.15, classification=ModelClassification.WATCH),
        _make_card(2, 0.10, classification=ModelClassification.NO_BET),
        _make_card(3, 0.05, classification=ModelClassification.NOT_ELIGIBLE),
    ]
    result = SlateResult(
        cards=cards,
        combinations=[],
        slate_quality=SlateQuality.GREEN,
        model_health=ModelHealth.GREEN,
        confirmed_lineups=15,
        total_games=15,
        updated_at=datetime.now(timezone.utc),
        pregame_games=15,
        live_games=0,
        final_games=0,
        messages=["NO HAY PICKS HR CALIFICADOS ENTRE LOS JUEGOS CONFIRMADOS"],
    )

    widget._loaded(result)

    # 3 visible rows: the WATCH/WATCH/NO_BET cards. The NOT_ELIGIBLE card is the
    # only one allowed to be excluded.
    assert widget.table.rowCount() == 3
    statuses = {widget.table.item(r, 3).text() for r in range(widget.table.rowCount())}
    assert statuses == {"VIGILAR", "ALTO RIESGO"}
    assert "NO HAY PICKS HR CALIFICADOS ENTRE LOS JUEGOS CONFIRMADOS" in widget.banner.text()


def test_today_header_shows_pregame_live_final_breakdown_not_juegos_listos():
    app()
    widget = TodayWidget(_make_service(), None)
    result = SlateResult(
        cards=[],
        combinations=[],
        slate_quality=SlateQuality.GREEN,
        model_health=ModelHealth.GREEN,
        confirmed_lineups=15,
        total_games=15,
        updated_at=datetime.now(timezone.utc),
        pregame_games=0,
        live_games=9,
        final_games=6,
        messages=["NO HAY JUEGOS PREGAME DISPONIBLES PARA ANALIZAR"],
    )

    widget._loaded(result)

    text = widget.lineups.text()
    assert "juegos listos" not in text
    assert "0" in text and "pregame" in text.lower()
    assert "9" in text and ("vivo" in text.lower())
    assert "6" in text and ("final" in text.lower())
    assert "NO HAY JUEGOS PREGAME DISPONIBLES PARA ANALIZAR" in widget.banner.text()


def test_copy_pick_shows_confirmation_and_resets():
    app()
    widget = TodayWidget(_make_service(), None)
    card = _make_card(0, 0.4)

    widget._show_detail(card)
    button = widget.copy_btn
    button.click()

    assert button.text() == "COPIADO"
    assert "HR" in QApplication.clipboard().text()


def test_today_layout_is_responsive():
    app()
    widget = TodayWidget(_make_service(), None)
    widget.resize(1200, 800)

    widget.main_pair.resize(1000, 500)
    widget.main_pair.reflow()
    widget.combo_grid.resize(1000, 400)
    widget.combo_grid.reflow()
    assert widget.main_pair.column_count == 2
    assert widget.combo_grid.column_count == 2

    widget.main_pair.resize(650, 500)
    widget.combo_grid.resize(650, 600)
    widget.main_pair.reflow()
    widget.combo_grid.reflow()
    assert widget.main_pair.column_count == 1
    assert widget.combo_grid.column_count == 1


def test_combo_cards_label_qualified_and_fallback_with_leg_classifications():
    app()
    widget = TodayWidget(_make_service(), None)
    legs_qualified = [
        CombinationLeg("p1", 1, "Aaron Judge", 0.2, ModelClassification.PRIMARY, 100),
        CombinationLeg("p2", 2, "Juan Soto", 0.18, ModelClassification.SECONDARY, 101),
    ]
    legs_fallback = [
        CombinationLeg("p3", 3, "Player C", 0.1, ModelClassification.WATCH, 102),
        CombinationLeg("p4", 4, "Player D", 0.08, ModelClassification.NO_BET, 103),
    ]
    combos = [
        _make_combo("BEST_2_MAN", CombinationFilterStatus.QUALIFIED, legs_qualified),
        _make_combo("LONG_SHOT_2_MAN", CombinationFilterStatus.FALLBACK, legs_fallback),
    ]
    result = SlateResult(
        cards=[],
        combinations=combos,
        slate_quality=SlateQuality.GREEN,
        model_health=ModelHealth.GREEN,
        confirmed_lineups=15,
        total_games=15,
        updated_at=datetime.now(timezone.utc),
    )
    widget.current = result
    widget._render_combos()
    combined = _combo_frame_texts(widget)

    assert "✅ CUMPLE FILTRO · RECOMENDADA" in combined
    assert "⚠ NO CUMPLE FILTRO · ALTO RIESGO" in combined
    assert "Aaron Judge · PRIMARY" in combined
    assert "Juan Soto · SECONDARY" in combined
    assert "Player C · WATCH" in combined
    assert "Player D · NO_BET" in combined


def test_combo_card_shows_not_enough_players_message_when_missing():
    app()
    widget = TodayWidget(_make_service(), None)
    result = SlateResult(
        cards=[],
        combinations=[],
        slate_quality=SlateQuality.GREEN,
        model_health=ModelHealth.GREEN,
        confirmed_lineups=15,
        total_games=15,
        updated_at=datetime.now(timezone.utc),
    )
    widget.current = result
    widget._render_combos()
    combined = _combo_frame_texts(widget)

    assert "NO HAY SUFICIENTES JUGADORES ANALIZADOS" in combined


def _detail_texts(widget) -> str:
    return "\n".join(label.text() for label in widget.detail.findChildren(QLabel))


def test_detail_panel_shows_best_and_fanduel_when_different():
    app()
    widget = TodayWidget(_make_service(), None)
    card = _make_card(0, 0.3)
    card.market = SimpleNamespace(quote=SimpleNamespace(bookmaker="FanDuel", american_odds=390))
    card.best_market = SimpleNamespace(quote=SimpleNamespace(bookmaker="DraftKings", american_odds=430))

    widget._show_detail(card)
    texts = _detail_texts(widget)

    assert "DraftKings +430 · MEJOR CUOTA" in texts
    assert "FanDuel +390" in texts


def test_detail_panel_avoids_duplicate_fanduel_line_when_best():
    app()
    widget = TodayWidget(_make_service(), None)
    card = _make_card(0, 0.3)
    fanduel_quote = SimpleNamespace(bookmaker="FanDuel", american_odds=430)
    card.market = SimpleNamespace(quote=fanduel_quote)
    card.best_market = SimpleNamespace(quote=fanduel_quote)

    widget._show_detail(card)
    texts = _detail_texts(widget)

    assert texts.count("FanDuel") == 1
    assert "FanDuel +430 · MEJOR CUOTA" in texts


_PLACEHOLDER_TEXT = "Selecciona un jugador para ver el motivo y el riesgo principal."


def _current_layout_texts(layout) -> list[str]:
    # Reads only what the layout currently holds, unlike QWidget.findChildren()
    # which can still see widgets scheduled for deleteLater() but not yet
    # destroyed (deferred deletion needs a running Qt event loop to complete,
    # which a synchronous test never runs) -- this is the deterministic way to
    # assert "no accumulation" regardless of GC timing.
    texts = []
    for i in range(layout.count()):
        w = layout.itemAt(i).widget()
        if isinstance(w, QLabel):
            texts.append(w.text())
    return texts


def test_selecting_a_player_shows_only_that_players_detail():
    app()
    widget = TodayWidget(_make_service(), None)
    card_a = _make_card(0, 0.3)

    widget._show_detail(card_a)
    texts = _current_layout_texts(widget.detail_layout)

    assert any("Player 0" in t for t in texts)
    assert _PLACEHOLDER_TEXT not in texts


def test_selecting_player_b_fully_replaces_player_a_detail():
    app()
    widget = TodayWidget(_make_service(), None)
    card_a = _make_card(0, 0.3)
    card_b = _make_card(1, 0.2)

    widget._show_detail(card_a)
    widget._show_detail(card_b)
    texts = _current_layout_texts(widget.detail_layout)

    assert any("Player 1" in t for t in texts)
    assert not any("Player 0" in t for t in texts)
    assert _PLACEHOLDER_TEXT not in texts


def test_clearing_detail_shows_exactly_one_placeholder():
    app()
    widget = TodayWidget(_make_service(), None)
    widget._show_detail(_make_card(0, 0.3))

    widget._clear_detail()
    texts = _current_layout_texts(widget.detail_layout)

    assert texts.count(_PLACEHOLDER_TEXT) == 1


def test_repeated_selection_and_clearing_does_not_accumulate_widgets():
    app()
    widget = TodayWidget(_make_service(), None)
    card = _make_card(0, 0.3)

    widget._clear_detail()
    baseline = widget.detail_layout.count()

    for _ in range(5):
        widget._show_detail(card)
        widget._clear_detail()

    assert widget.detail_layout.count() == baseline
    assert _current_layout_texts(widget.detail_layout).count(_PLACEHOLDER_TEXT) == 1


def _detail_label_geometries(widget):
    positions = []
    for i in range(widget.detail_layout.count()):
        w = widget.detail_layout.itemAt(i).widget()
        if isinstance(w, QLabel):
            g = w.geometry()
            positions.append((w.text(), g.y(), g.y() + g.height(), g.height(), w.minimumSizeHint().height()))
    return positions


def _top15_scroll_area(widget):
    # The QScrollArea wrapping the TOP 15 page, added by the earlier POR
    # PARTIDOS resize fix (POR PARTIDOS is now its own page entirely, but
    # TOP 15 keeps this same isolation wrapper).
    return widget.top15_scroll


def test_detail_labels_do_not_overlap_at_a_short_viewport():
    app().setStyleSheet(APP_STYLESHEET)
    widget = TodayWidget(_make_service(), None)
    widget.show()
    widget.resize(760, 640)

    widget._show_detail(_make_card(0, 0.4))
    app().processEvents()

    try:
        positions = _detail_label_geometries(widget)
        assert len(positions) > 1
        for i in range(len(positions) - 1):
            _, _, bottom, _, _ = positions[i]
            _, top, _, _, _ = positions[i + 1]
            assert bottom <= top, f"label {i} (bottom={bottom}) overlaps label {i+1} (top={top})"
    finally:
        app().setStyleSheet("")


def test_detail_labels_keep_their_full_readable_height_at_a_short_viewport():
    # No label may be compressed below its own minimumSizeHint -- that's what
    # produces the overlap; the page must scroll instead of shrinking content.
    app().setStyleSheet(APP_STYLESHEET)
    widget = TodayWidget(_make_service(), None)
    widget.show()
    widget.resize(760, 640)

    widget._show_detail(_make_card(0, 0.4))
    app().processEvents()

    try:
        for text, _, _, height, min_height in _detail_label_geometries(widget):
            assert height >= min_height, f"{text!r} got height={height} < minimumSizeHint={min_height}"
    finally:
        app().setStyleSheet("")


def test_top15_page_scrolls_vertically_when_content_does_not_fit_a_short_viewport():
    app().setStyleSheet(APP_STYLESHEET)
    widget = TodayWidget(_make_service(), None)
    widget.show()
    widget.resize(760, 640)

    widget._show_detail(_make_card(0, 0.4))
    app().processEvents()

    try:
        scroll_area = _top15_scroll_area(widget)
        assert scroll_area.verticalScrollBar().maximum() > 0
    finally:
        app().setStyleSheet("")


def test_wide_viewport_shows_no_unnecessary_scroll_and_keeps_normal_layout():
    app().setStyleSheet(APP_STYLESHEET)
    widget = TodayWidget(_make_service(), None)
    widget.show()
    widget.resize(1400, 900)
    cards = [_make_card(i, 1 - i / 100) for i in range(15)]
    result = SlateResult(
        cards=cards, combinations=[], slate_quality=SlateQuality.GREEN, model_health=ModelHealth.GREEN,
        confirmed_lineups=1, total_games=1, updated_at=datetime.now(timezone.utc),
    )

    widget._loaded(result)
    app().processEvents()

    try:
        scroll_area = _top15_scroll_area(widget)
        assert scroll_area.verticalScrollBar().maximum() == 0
        assert widget.main_pair.column_count == 2
        for _, _, _, height, min_height in _detail_label_geometries(widget):
            assert height >= min_height
    finally:
        app().setStyleSheet("")


def test_selecting_different_players_repeatedly_keeps_the_layout_stable():
    app().setStyleSheet(APP_STYLESHEET)
    widget = TodayWidget(_make_service(), None)
    widget.show()
    widget.resize(760, 640)
    cards = [_make_card(i, 1 - i / 100) for i in range(5)]

    try:
        for _ in range(3):
            for card in cards:
                widget._show_detail(card)
                app().processEvents()
                positions = _detail_label_geometries(widget)
                for i in range(len(positions) - 1):
                    assert positions[i][2] <= positions[i + 1][1]
                for _, _, _, height, min_height in positions:
                    assert height >= min_height
    finally:
        app().setStyleSheet("")


def test_short_viewport_fix_does_not_reintroduce_the_placeholder_accumulation_bug():
    app().setStyleSheet(APP_STYLESHEET)
    widget = TodayWidget(_make_service(), None)
    widget.show()
    widget.resize(760, 640)
    card = _make_card(0, 0.3)

    try:
        widget._clear_detail()
        baseline = widget.detail_layout.count()
        for _ in range(3):
            widget._show_detail(card)
            widget._clear_detail()
        assert widget.detail_layout.count() == baseline
        assert _current_layout_texts(widget.detail_layout).count(_PLACEHOLDER_TEXT) == 1
    finally:
        app().setStyleSheet("")

