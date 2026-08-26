from __future__ import annotations

from dataclasses import dataclass

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
