from datetime import datetime, timedelta, timezone
from pathlib import Path

from mlb_hr.domain.enums import ConfidenceLabel, CriticVerdict, IntegrityStatus, ModelClassification, ModelHealth, SettlementStatus, UserActionLabel
from mlb_hr.domain.models import PlayerRef, Prediction, ProbabilityDistribution, ResultRecord
from mlb_hr.services.settlement import SettlementService
from mlb_hr.services.settlement_coordinator import SettlementCoordinator, SettlementRunResult
from mlb_hr.storage.sqlite import SQLiteStore

REPO_MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"


def _prediction(pid: str, prob: float = 0.2) -> Prediction:
    return Prediction(
        pid, "s1", 1, PlayerRef(10, "Batter"), PlayerRef(20, "Pitcher"), "A", "B",
        datetime.now(timezone.utc), prob, prob, 80, "A", 80, 80, ConfidenceLabel.HIGH,
        ProbabilityDistribution(prob, prob - .02, prob, prob + .02, .04, 90),
        ModelClassification.PRIMARY, UserActionLabel.RECOMMENDED, IntegrityStatus.PASS,
        CriticVerdict.PASS, ["Strong"], None, [], "V1", "F1", "C1", "Q1", ModelHealth.GREEN,
        datetime.now(timezone.utc),
    )


def _final_feed(hr: bool = True) -> dict:
    event = "home_run" if hr else "single"
    return {
        "gameData": {"status": {"abstractGameState": "Final", "detailedState": "Final"}},
        "liveData": {
            "plays": {"allPlays": [{
                "about": {"isComplete": True},
                "matchup": {"batter": {"id": 10}, "pitcher": {"id": 20}},
                "result": {"eventType": event},
            }]},
            "boxscore": {"teams": {
                "away": {"pitchers": [20, 21], "players": {
                    "ID10": {"battingOrder": "100", "stats": {"batting": {"homeRuns": 1 if hr else 0, "plateAppearances": 1}}},
                }},
                "home": {"pitchers": [30], "players": {}},
            }},
        },
    }


def _live_feed() -> dict:
    return {"gameData": {"status": {"abstractGameState": "Live", "detailedState": "In Progress"}}}


class _FakeMLB:
    def __init__(self, feed: dict) -> None:
        self.feed = feed
        self.calls = 0

    def game_feed(self, game_pk):
        self.calls += 1
        from types import SimpleNamespace
        return SimpleNamespace(ok=True, data=self.feed)


def _seed_locked_prediction(store: SQLiteStore, pid: str) -> None:
    store.save_snapshot(
        snapshot_id="s1", game_pk=1, lineup={}, starter={}, weather=None,
        source_timestamps={}, feature_vector={}, model_package_hash="h",
        deterministic_seed=1, created_at=datetime.now(timezone.utc),
    )
    store.save_prediction(_prediction(pid))
    store.save_model_ledger(
        prediction_id=pid, reference_stake=10.0, odds_at_prediction=150,
        decimal_odds=2.5, implied_probability=0.4, edge_pp=5.0,
    )
    store.lock_prediction(pid)


def query_settlement_counts_and_total_pnl(store: SQLiteStore) -> dict:
    with store.connection() as con:
        settlements = con.execute("SELECT count(*) FROM settlements").fetchone()[0]
        bankroll_events = con.execute("SELECT count(*) FROM paper_bankroll_events").fetchone()[0]
        total_pnl = con.execute("SELECT coalesce(sum(amount),0) FROM paper_bankroll_events").fetchone()[0]
        confirmed = con.execute(
            "SELECT count(*) FROM settlements WHERE active=1 AND status='CONFIRMED_SETTLEMENT'"
        ).fetchone()[0]
    return {
        "settlements": settlements,
        "bankroll_events": bankroll_events,
        "total_pnl": float(total_pnl),
        "confirmed": confirmed,
    }


def test_repeated_settlement_after_confirmation_does_not_duplicate_anything(tmp_path):
    store = SQLiteStore(tmp_path / "db.sqlite", REPO_MIGRATIONS)
    store.migrate()
    _seed_locked_prediction(store, "p1")
    # Pre-seed a PROVISIONAL_SETTLEMENT matching what the feed will independently
    # produce, backdated >24h so the first coordinator run promotes it to
    # CONFIRMED_SETTLEMENT and fires the bankroll event exactly once.
    store.save_settlement(ResultRecord(
        prediction_id="p1", game_pk=1, player_id=10, status=SettlementStatus.PROVISIONAL_SETTLEMENT,
        actual_hr_count=1, actual_hr_binary=1, actual_pa=1, actual_pa_vs_starter=1, actual_pa_vs_bullpen=0,
        result_version=1, result_source="MLB_OFFICIAL_GAME_FEED",
        fetched_at=datetime.now(timezone.utc) - timedelta(hours=25),
        verified_pbp=True, verified_box=True,
    ))
    mlb = _FakeMLB(_final_feed(hr=True))
    coordinator = SettlementCoordinator(SettlementService(store, mlb))

    first = coordinator.refresh_pending()
    snapshot1 = query_settlement_counts_and_total_pnl(store)
    assert snapshot1["confirmed"] == 1
    assert snapshot1["bankroll_events"] == 1

    second = coordinator.refresh_pending()
    snapshot2 = query_settlement_counts_and_total_pnl(store)

    assert snapshot2 == snapshot1
    assert second.updated == 0
    assert isinstance(first, SettlementRunResult)
    assert isinstance(second, SettlementRunResult)


def test_live_game_stays_pending_and_creates_no_bankroll_event(tmp_path):
    store = SQLiteStore(tmp_path / "db.sqlite", REPO_MIGRATIONS)
    store.migrate()
    _seed_locked_prediction(store, "p1")
    mlb = _FakeMLB(_live_feed())
    coordinator = SettlementCoordinator(SettlementService(store, mlb))

    first = coordinator.refresh_pending()
    snapshot1 = query_settlement_counts_and_total_pnl(store)
    second = coordinator.refresh_pending()
    snapshot2 = query_settlement_counts_and_total_pnl(store)

    assert snapshot1["bankroll_events"] == 0
    assert snapshot1["confirmed"] == 0
    assert snapshot2["bankroll_events"] == 0
    assert first.updated == 0
    assert second.updated == 0


def test_coordinator_has_no_path_to_analyze_slate(tmp_path):
    # SettlementCoordinator is constructed from a SettlementService alone, which
    # has no reference to AnalysisService/analyze_slate at all -- there is no
    # attribute path from here to the predictive pipeline. The UI-level
    # guarantee that clicking ACTUALIZAR RESULTADOS doesn't trigger a slate
    # re-analysis is covered separately in tests/ui/test_settlement_triggers.py.
    store = SQLiteStore(tmp_path / "db.sqlite", REPO_MIGRATIONS)
    store.migrate()
    mlb = _FakeMLB(_final_feed(hr=True))
    coordinator = SettlementCoordinator(SettlementService(store, mlb))

    assert not hasattr(coordinator, "analyze_slate")
    assert not hasattr(coordinator.settlement_service, "analyze_slate")
    result = coordinator.refresh_pending()
    assert isinstance(result, SettlementRunResult)
