from __future__ import annotations

from mlb_hr.domain.enums import ModelClassification


def practical_status(classification: ModelClassification) -> str:
    if classification in {ModelClassification.PRIMARY, ModelClassification.SECONDARY}:
        return "RECOMENDADO"
    if classification == ModelClassification.WATCH:
        return "VIGILAR"
    return "NO CUMPLE FILTRO"


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
