from datetime import datetime,timezone
from mlb_hr.domain.enums import DataFreshness,MarketPriceLabel
from mlb_hr.domain.models import OddsQuote
from mlb_hr.odds.market import MarketLayer


def q(odds):
    from mlb_hr.domain.math import american_to_decimal,decimal_to_implied
    d=american_to_decimal(odds);now=datetime.now(timezone.utc)
    return OddsQuote(1,1,'FanDuel','batter_home_runs',odds,d,decimal_to_implied(d),now,now,DataFreshness.FRESH,'TEST')


def test_market_price_changes_without_touching_model_probability():
    layer=MarketLayer();p=.25
    a=layer.evaluate(p,q(500),10);b=layer.evaluate(p,q(150),10)
    assert p==.25
    assert a.edge_pp!=b.edge_pp
    assert a.label!=b.label
