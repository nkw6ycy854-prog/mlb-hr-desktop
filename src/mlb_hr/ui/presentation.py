from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from mlb_hr.domain.enums import ModelClassification
from mlb_hr.services.game_time import GameTimeService


def practical_status(classification: ModelClassification) -> str:
    if classification in {ModelClassification.PRIMARY, ModelClassification.SECONDARY}:
        return "RECOMENDADO"
    if classification == ModelClassification.WATCH:
        return "VIGILAR"
    return "NO CUMPLE FILTRO"


UNKNOWN_CLASSIFICATION_VISUAL_STATE = "ALTO RIESGO"

_KNOWN_CLASSIFICATIONS = frozenset(ModelClassification)

_VISUAL_STATE_BY_CLASSIFICATION = {
    ModelClassification.PRIMARY: "RECOMENDADO",
    ModelClassification.SECONDARY: "RECOMENDADO",
    ModelClassification.WATCH: "VIGILAR",
    ModelClassification.NO_BET: "ALTO RIESGO",
}


def is_known_classification(classification) -> bool:
    return classification in _KNOWN_CLASSIFICATIONS


_VISUAL_STATE_DISPLAY = {
    "RECOMENDADO": ("●", "recomendado"),
    "VIGILAR": ("◐", "vigilar"),
    "ALTO RIESGO": ("▲", "alto_riesgo"),
    "NO ELEGIBLE": ("✕", "no_elegible"),
}


def visual_state_display(state: str) -> tuple[str, str]:
    """(icon, QSS tone name) for a visual_state() string.

    The state is never shown as color alone -- always text + a distinct
    icon/shape + color, per the approved plan.
    """
    return _VISUAL_STATE_DISPLAY.get(state, ("▲", "alto_riesgo"))


def visual_state(classification, *, eligible: bool) -> str:
    """V1.2.0's presentation-only state mapping (approved plan).

    eligible=False is absolute and always wins, regardless of
    classification -- this is a display layer over `classification` and
    `eligible`, exactly as produced today; it never feeds back into either.
    An unknown/future classification value falls back to ALTO RIESGO,
    matching the approved plan's runtime-safety rule (callers are
    responsible for logging a REQUIERE ATENCIÓN audit event via
    is_known_classification()).
    """
    if not eligible:
        return "NO ELEGIBLE"
    return _VISUAL_STATE_BY_CLASSIFICATION.get(classification, UNKNOWN_CLASSIFICATION_VISUAL_STATE)


def visible_cards(cards, *, expanded: bool, limit: int = 15):
    ordered = sorted(cards, key=lambda c: c.prediction.final_hr_probability, reverse=True)
    return ordered if expanded else ordered[:limit]


def display_quote(card, *, best: bool) -> str:
    market = getattr(card, "best_market", None) if best else None
    market = market or card.market
    quote = market.quote if market else None
    if not quote or quote.american_odds is None:
        return "—"
    return f"{quote.bookmaker} {quote.american_odds:+d}" if best else f"{quote.american_odds:+d}"


@dataclass(frozen=True)
class QuoteDisplay:
    best_text: str
    fanduel_text: str | None


def quote_display(card) -> QuoteDisplay:
    best_market = getattr(card, "best_market", None)
    best_quote = best_market.quote if best_market else None
    fanduel_quote = card.market.quote if card.market else None

    if best_quote is None or best_quote.american_odds is None:
        return QuoteDisplay(best_text="—", fanduel_text=None)

    is_fanduel_best = best_quote.bookmaker.lower() == "fanduel"
    best_text = f"{best_quote.bookmaker} {best_quote.american_odds:+d} · MEJOR CUOTA"
    if is_fanduel_best or fanduel_quote is None or fanduel_quote.american_odds is None:
        fanduel_text = None
    else:
        fanduel_text = f"FanDuel {fanduel_quote.american_odds:+d}"
    return QuoteDisplay(best_text=best_text, fanduel_text=fanduel_text)


def format_local_time(dt: datetime | None, timezone_name: str) -> str:
    return GameTimeService(timezone_name).format_time(dt)


_PLAYER_RESULT_LABELS = {"HR": "HR", "NO_HR": "NO HR", "PENDING": "PENDIENTE"}
_COMBINATION_RESULT_LABELS = {"HR": "GANADA", "NO_HR": "PERDIDA", "PENDING": "PENDIENTE"}


def player_result_label(result: str) -> str:
    return _PLAYER_RESULT_LABELS.get(result, result)


def combination_result_label(result: str) -> str:
    return _COMBINATION_RESULT_LABELS.get(result, result)


def data_health_ok(report) -> bool:
    statcast_item = next((i for i in report.items if i.key == "statcast"), None)
    db_item = next((i for i in report.items if i.key == "database"), None)
    return (statcast_item is None or statcast_item.state == "OK") and (db_item is None or db_item.state == "OK")
