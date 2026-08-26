from datetime import datetime, timezone
from types import SimpleNamespace

from mlb_hr.domain.enums import (
    ConfidenceLabel,
    CriticVerdict,
    DataFreshness,
    IntegrityStatus,
    MarketPriceLabel,
    ModelClassification,
    UserActionLabel,
)
from mlb_hr.domain.models import (
    MarketDecision,
    OddsQuote,
    PlayerRef,
    Prediction,
    PredictionCard,
    ProbabilityDistribution,
    ProviderMeta,
)
from mlb_hr.odds.market import MarketLayer
from mlb_hr.providers.base import ProviderResult
from mlb_hr.services.analysis import AnalysisService


def q(bookmaker: str, odds: int, player_id: int, game_pk: int = 1) -> OddsQuote:
    from mlb_hr.domain.math import american_to_decimal, decimal_to_implied
    dec = american_to_decimal(odds)
    now = datetime.now(timezone.utc)
    return OddsQuote(game_pk, player_id, bookmaker, "batter_home_runs", odds, dec, decimal_to_implied(dec), now, now, DataFreshness.FRESH, "TEST")


def _make_prediction(player_id: int, prob: float, classification, game_pk: int = 1) -> Prediction:
    player = PlayerRef(player_id, f"Player {player_id}")
    pitcher = PlayerRef(900 + player_id, "Pitcher")
    dist = ProbabilityDistribution(prob, prob, prob, prob, 0.0, 90.0)
    return Prediction(
        prediction_id=f"pred-{player_id}", snapshot_id="snap", game_pk=game_pk,
        player=player, opposing_pitcher=pitcher, team_name="A", opponent_name="B",
        game_time=None, final_hr_probability=prob, raw_hr_probability=prob,
        matchup_score=80, grade="B", reliability=90, confidence_score=80,
        confidence_label=ConfidenceLabel.HIGH, distribution=dist,
        classification=classification, user_action=UserActionLabel.RECOMMENDED,
        integrity=IntegrityStatus.PASS, critic=CriticVerdict.PASS,
        reasons=[], main_risk=None, warnings=[],
        model_version="V1", feature_version="F1", calibration_version="C1", quality_gate_version="Q1",
    )


class _FakeOddsProvider:
    def __init__(self, quotes_by_game_pk: dict[int, list[OddsQuote]]) -> None:
        self.quotes_by_game_pk = quotes_by_game_pk
        self.call_count = 0

    def fetch_us_hr_quotes(self, game) -> ProviderResult:
        self.call_count += 1
        quotes = self.quotes_by_game_pk.get(game.game_pk, [])
        return ProviderResult(list(quotes), ProviderMeta(provider="TEST", fetched_at=datetime.now(timezone.utc)))


def test_best_market_added_alongside_fanduel_without_changing_probability_or_ranking():
    fanduel = q("FanDuel", 390, player_id=1)
    draftkings = q("DraftKings", 430, player_id=1)

    pred_a = _make_prediction(1, 0.30, ModelClassification.PRIMARY)
    pred_b = _make_prediction(2, 0.20, ModelClassification.SECONDARY)
    card_a = PredictionCard(pred_a, MarketDecision(None, MarketPriceLabel.NO_ODDS))
    card_b = PredictionCard(pred_b, MarketDecision(None, MarketPriceLabel.NO_ODDS))
    cards = [card_a, card_b]

    service = object.__new__(AnalysisService)
    service.market = MarketLayer()
    service.stake = 10.0
    saved_odds: list[tuple[str, bool]] = []
    service.store = SimpleNamespace(
        save_odds=lambda quote, prediction_id, is_at_prediction=False: saved_odds.append((quote.bookmaker, is_at_prediction))
    )
    service.odds = _FakeOddsProvider({1: [fanduel, draftkings]})

    game_lookup = {1: SimpleNamespace(game_pk=1)}
    ranked_before = [c.prediction.prediction_id for c in sorted(cards, key=AnalysisService._rank_key, reverse=True)]

    service._assign_market_and_odds(cards, game_lookup)

    ranked_after = [c.prediction.prediction_id for c in sorted(cards, key=AnalysisService._rank_key, reverse=True)]
    assert ranked_before == ranked_after

    assert card_a.market.quote.bookmaker == "FanDuel"
    assert card_a.market.quote.american_odds == 390
    assert card_a.best_market.quote.bookmaker == "DraftKings"
    assert card_a.best_market.quote.american_odds == 430
    assert card_a.prediction.final_hr_probability == 0.30

    assert card_b.market.quote is None
    assert card_b.best_market.quote is None

    assert service.odds.call_count == 1
    assert ("FanDuel", True) in saved_odds
    assert ("FanDuel", False) in saved_odds
    assert ("DraftKings", False) in saved_odds
