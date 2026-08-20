from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from mlb_hr.domain.enums import DataFreshness, MarketPriceLabel
from mlb_hr.domain.math import american_to_decimal, decimal_to_implied, payout_for_stake
from mlb_hr.domain.models import MarketDecision, OddsQuote


@dataclass(slots=True)
class MarketPolicy:
    good_edge_pp: float = 2.0
    fair_edge_floor_pp: float = -1.0


class MarketLayer:
    def __init__(self, policy: MarketPolicy | None = None) -> None:
        self.policy = policy or MarketPolicy()

    def evaluate(self, model_probability: float, quote: OddsQuote | None, stake: float) -> MarketDecision:
        if quote is None or quote.american_odds is None:
            return MarketDecision(None, MarketPriceLabel.NO_ODDS)
        implied = quote.implied_probability
        if implied is None:
            dec = quote.decimal_odds or american_to_decimal(quote.american_odds)
            implied = decimal_to_implied(dec)
        edge_pp = (model_probability - implied) * 100.0
        total, profit = payout_for_stake(stake, quote.american_odds)
        ev = model_probability * profit - (1.0 - model_probability) * stake
        if quote.freshness == DataFreshness.STALE:
            label = MarketPriceLabel.NO_ODDS
        elif edge_pp >= self.policy.good_edge_pp:
            label = MarketPriceLabel.GOOD_VALUE
        elif edge_pp >= self.policy.fair_edge_floor_pp:
            label = MarketPriceLabel.FAIR
        else:
            label = MarketPriceLabel.BAD_PRICE
        return MarketDecision(quote, label, edge_pp, ev / max(stake, 1e-9), total, profit)

    def manual_quote(self, game_pk: int, player_id: int, american_odds: int) -> OddsQuote:
        dec=american_to_decimal(american_odds)
        now=datetime.now(timezone.utc)
        return OddsQuote(
            game_pk=game_pk,
            player_id=player_id,
            bookmaker="FanDuel",
            market="batter_home_runs",
            american_odds=american_odds,
            decimal_odds=dec,
            implied_probability=decimal_to_implied(dec),
            last_update=now,
            fetched_at=now,
            freshness=DataFreshness.FRESH,
            source="MANUAL_SOURCE",
        )
