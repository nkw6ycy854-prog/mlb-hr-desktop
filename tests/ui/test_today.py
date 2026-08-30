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


def test_today_defaults_to_top_15_and_can_expand():
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

    assert widget.table.rowCount() == 15
    assert widget.view_all_btn.text() == "VER TODOS"
    widget.toggle_all()
    assert widget.table.rowCount() == 20
    assert widget.view_all_btn.text() == "VER TOP 15"
    assert widget.table.horizontalHeaderItem(7).text() == "Estado"


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
    statuses = {widget.table.item(r, 7).text() for r in range(widget.table.rowCount())}
    assert statuses == {"VIGILAR", "NO CUMPLE FILTRO"}
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

    assert button.text() == "COPIADO ✓"
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


def _lineup_entry(index: int, name: str, order: int) -> LineupEntry:
    return LineupEntry(player=PlayerRef(player_id=index, full_name=name), batting_order=order)


def _game_context(
    game_pk: int, *, away_entries=(), home_entries=(),
    away_confirmed=True, home_confirmed=True, state=GameState.PREGAME,
    game_time=datetime(2026, 8, 26, 23, 15, tzinfo=timezone.utc),
) -> GameContext:
    return GameContext(
        game_pk=game_pk, game_date=game_time.date() if game_time else None, game_time=game_time,
        away_team_id=1, away_team_name="Team A", home_team_id=2, home_team_name="Team B",
        venue=VenueRef(1, "Park"), state=state,
        away_lineup=TeamLineup(team_id=1, team_name="Team A", entries=list(away_entries), confirmed=away_confirmed),
        home_lineup=TeamLineup(team_id=2, team_name="Team B", entries=list(home_entries), confirmed=home_confirmed),
        away_starter=PlayerRef(500, "Away SP"), home_starter=PlayerRef(501, "Home SP"),
    )


def _games_page_texts(widget) -> str:
    from PySide6.QtWidgets import QPushButton
    labels = [label.text() for label in widget.games_page.findChildren(QLabel)]
    buttons = [button.text() for button in widget.games_page.findChildren(QPushButton)]
    return "\n".join(labels + buttons)


def test_top15_and_por_partidos_switch_toggles_view_stack():
    app()
    widget = TodayWidget(_make_service(), None)
    result = SlateResult(
        cards=[], combinations=[], slate_quality=SlateQuality.GREEN, model_health=ModelHealth.GREEN,
        confirmed_lineups=0, total_games=0, updated_at=datetime.now(timezone.utc),
    )
    widget._loaded(result)

    assert widget.view_stack.currentIndex() == 0
    widget.by_games_btn.click()
    assert widget.view_stack.currentIndex() == 1
    widget.top15_btn.click()
    assert widget.view_stack.currentIndex() == 0


def test_por_partidos_shows_both_teams_all_lineup_players_hr_descending_and_canonical_time():
    app()
    widget = TodayWidget(_make_service(), None)
    game = _game_context(
        1,
        away_entries=[_lineup_entry(1, "Low", 1), _lineup_entry(2, "High", 2)],
        home_entries=[_lineup_entry(3, "Home Player", 1)],
    )
    away_low = _make_card(1, 0.05)
    away_high = _make_card(2, 0.20)
    home_card = _make_card(3, 0.10)
    for card, game_pk in ((away_low, 1), (away_high, 1), (home_card, 1)):
        card.prediction.game_pk = game_pk
    result = SlateResult(
        cards=[away_low, away_high, home_card], combinations=[], slate_quality=SlateQuality.GREEN,
        model_health=ModelHealth.GREEN, confirmed_lineups=1, total_games=1,
        updated_at=datetime.now(timezone.utc), pregame_games=1, game_contexts=(game,),
    )

    widget._loaded(result)
    texts = _games_page_texts(widget)

    assert texts.index("High") < texts.index("Low")
    assert "Home Player" in texts
    assert "Team A" in texts and "Team B" in texts
    assert "7:15 PM" in texts


def test_por_partidos_distinguishes_pending_lineup_live_and_final_empty_states():
    app()
    widget = TodayWidget(_make_service(), None)
    pending = _game_context(1, away_confirmed=True, home_confirmed=False)
    live = _game_context(2, state=GameState.LIVE)
    final = _game_context(3, state=GameState.FINAL)
    result = SlateResult(
        cards=[], combinations=[], slate_quality=SlateQuality.GREEN, model_health=ModelHealth.GREEN,
        confirmed_lineups=0, total_games=3, updated_at=datetime.now(timezone.utc),
        game_contexts=(pending, live, final),
    )

    widget._loaded(result)
    texts = _games_page_texts(widget)

    assert "ESPERANDO LINEUP" in texts
    assert "EN VIVO" in texts
    assert "FINAL" in texts


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

