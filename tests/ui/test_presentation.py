from datetime import datetime, timezone
from types import SimpleNamespace

from mlb_hr.domain.enums import ModelClassification
from mlb_hr.ui.presentation import (
    combination_result_label,
    format_local_time,
    player_result_label,
    practical_status,
    quote_display,
    visible_cards,
)


def test_practical_status_mapping():
    assert practical_status(ModelClassification.PRIMARY) == "RECOMENDADO"
    assert practical_status(ModelClassification.SECONDARY) == "RECOMENDADO"
    assert practical_status(ModelClassification.WATCH) == "VIGILAR"
    assert practical_status(ModelClassification.NO_BET) == "NO CUMPLE FILTRO"


def test_visible_cards_defaults_to_top_15():
    cards = [SimpleNamespace(prediction=SimpleNamespace(final_hr_probability=1 - i / 100)) for i in range(30)]
    assert len(visible_cards(cards, expanded=False)) == 15
    assert len(visible_cards(cards, expanded=True)) == 30


def _quote(bookmaker, odds):
    return SimpleNamespace(bookmaker=bookmaker, american_odds=odds)


def _card(best_bookmaker, best_odds, fanduel_odds):
    fanduel_quote = _quote("FanDuel", fanduel_odds) if fanduel_odds is not None else None
    best_quote = _quote(best_bookmaker, best_odds) if best_odds is not None else None
    return SimpleNamespace(
        market=SimpleNamespace(quote=fanduel_quote),
        best_market=SimpleNamespace(quote=best_quote),
    )


def test_quote_display_shows_best_and_fanduel_when_different():
    card = _card("DraftKings", 430, 390)
    qd = quote_display(card)
    assert qd.best_text == "DraftKings +430 · MEJOR CUOTA"
    assert qd.fanduel_text == "FanDuel +390"


def test_quote_display_avoids_duplicate_when_fanduel_is_best():
    card = _card("FanDuel", 430, 430)
    qd = quote_display(card)
    assert qd.best_text == "FanDuel +430 · MEJOR CUOTA"
    assert qd.fanduel_text is None


def test_format_local_time_converts_to_configured_timezone():
    dt = datetime(2026, 8, 26, 23, 5, tzinfo=timezone.utc)
    assert format_local_time(dt, "America/Santo_Domingo") == "7:05 PM"


def test_format_local_time_handles_missing_datetime():
    assert format_local_time(None, "UTC") == "—"


def test_player_result_label_uses_hr_no_hr_pendiente():
    assert player_result_label("HR") == "HR"
    assert player_result_label("NO_HR") == "NO HR"
    assert player_result_label("PENDING") == "PENDIENTE"


def test_combination_result_label_uses_ganada_perdida_pendiente():
    assert combination_result_label("HR") == "GANADA"
    assert combination_result_label("NO_HR") == "PERDIDA"
    assert combination_result_label("PENDING") == "PENDIENTE"
