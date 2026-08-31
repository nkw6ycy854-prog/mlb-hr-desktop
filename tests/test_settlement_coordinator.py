from datetime import datetime, timedelta, timezone
from pathlib import Path

from mlb_hr.domain.enums import CombinationFilterStatus, ConfidenceLabel, CriticVerdict, IntegrityStatus, ModelClassification, ModelHealth, PlayerAppearanceStatus, SettlementStatus, UserActionLabel
from mlb_hr.domain.models import Combination, CombinationLeg, PlayerRef, Prediction, ProbabilityDistribution, ResultRecord
from mlb_hr.services.settlement import SettlementService
from mlb_hr.services.settlement_coordinator import SettlementCoordinator, SettlementRunResult
from mlb_hr.storage.sqlite import SQLiteStore

REPO_MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"


def _prediction(pid: str, prob: float = 0.2, player_id: int = 10, player_name: str = "Batter", snapshot_id: str = "s1") -> Prediction:
    return Prediction(
        pid, snapshot_id, 1, PlayerRef(player_id, player_name), PlayerRef(20, "Pitcher"), "A", "B",
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


def _seed_locked_prediction(store: SQLiteStore, pid: str, *, player_id: int = 10, player_name: str = "Batter", snapshot_id: str = "s1") -> None:
    store.save_snapshot(
        snapshot_id=snapshot_id, game_pk=1, lineup={}, starter={}, weather=None,
        source_timestamps={}, feature_vector={}, model_package_hash="h",
        deterministic_seed=1, created_at=datetime.now(timezone.utc),
    )
    store.save_prediction(_prediction(pid, player_id=player_id, player_name=player_name, snapshot_id=snapshot_id))
    store.save_model_ledger(
        prediction_id=pid, reference_stake=10.0, odds_at_prediction=150,
        decimal_odds=2.5, implied_probability=0.4, edge_pp=5.0,
    )
    store.lock_prediction(pid)


def _settlement_row_count(store: SQLiteStore, prediction_id: str) -> int:
    with store.connection() as con:
        return con.execute(
            "SELECT count(*) FROM settlements WHERE prediction_id=?", (prediction_id,)
        ).fetchone()[0]


def _audit_events(store: SQLiteStore, event_code: str) -> list:
    with store.connection() as con:
        return list(con.execute(
            "SELECT * FROM audit_events WHERE event_code=?", (event_code,)
        ).fetchall())


def _final_feed_for_batters(batter_ids_hr: dict) -> dict:
    plays = []
    players = {}
    for bid, hr in batter_ids_hr.items():
        plays.append({
            "about": {"isComplete": True},
            "matchup": {"batter": {"id": bid}, "pitcher": {"id": 20}},
            "result": {"eventType": "home_run" if hr else "single"},
        })
        players[f"ID{bid}"] = {"battingOrder": "100", "stats": {"batting": {"homeRuns": 1 if hr else 0, "plateAppearances": 1}}}
    return {
        "gameData": {"status": {"abstractGameState": "Final", "detailedState": "Final"}},
        "liveData": {
            "plays": {"allPlays": plays},
            "boxscore": {"teams": {
                "away": {"pitchers": [20, 21], "players": players},
                "home": {"pitchers": [30], "players": {}},
            }},
        },
    }


def _matching_provisional_seed(prediction_id: str, player_id: int, *, hours_old: float = 25) -> ResultRecord:
    # Mirrors exactly what PostgameEngine.evaluate() produces for the single-play,
    # started-and-batted feeds built above -- a pre-seed that doesn't match this
    # would make _materially_same() see a (fake) real change on the first check,
    # not a genuine prior result.
    return ResultRecord(
        prediction_id=prediction_id, game_pk=1, player_id=player_id, status=SettlementStatus.PROVISIONAL_SETTLEMENT,
        actual_hr_count=1, actual_hr_binary=1, actual_pa=1, actual_pa_vs_starter=1, actual_pa_vs_bullpen=0,
        appearance_status=PlayerAppearanceStatus.STARTED_AND_BATTED,
        result_version=1, result_source="MLB_OFFICIAL_GAME_FEED",
        fetched_at=datetime.now(timezone.utc) - timedelta(hours=hours_old),
        verified_pbp=True, verified_box=True,
    )


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
    store.save_settlement(_matching_provisional_seed("p1", 10))
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


# --- Idempotency correction: repeated PROVISIONAL_SETTLEMENT rechecks ---

def test_identical_provisional_recheck_does_not_add_a_new_settlement_row(tmp_path):
    # Scenario A: same official feed checked twice while still < 24h old
    # (i.e. genuinely still provisional, not yet eligible for auto-confirm).
    store = SQLiteStore(tmp_path / "db.sqlite", REPO_MIGRATIONS)
    store.migrate()
    _seed_locked_prediction(store, "p1")
    mlb = _FakeMLB(_final_feed(hr=True))
    service = SettlementService(store, mlb)

    first_stats = service.reconcile_pending()
    row_count1 = _settlement_row_count(store, "p1")
    snapshot1 = query_settlement_counts_and_total_pnl(store)
    assert row_count1 == 1
    assert snapshot1["confirmed"] == 0  # still provisional, not yet 24h old

    second_stats = service.reconcile_pending()
    row_count2 = _settlement_row_count(store, "p1")
    snapshot2 = query_settlement_counts_and_total_pnl(store)

    assert row_count2 == row_count1
    assert second_stats["settled"] == 0
    assert snapshot2 == snapshot1


def test_materially_changed_provisional_adds_exactly_one_new_version(tmp_path):
    # Scenario B: the official feed's provisional result genuinely changes
    # (e.g. a box-score correction) between two checks -- a new version is
    # expected and an audit trail must record the real change. A third,
    # unchanged recheck of the corrected value must not add a fourth... a
    # second extra row.
    store = SQLiteStore(tmp_path / "db.sqlite", REPO_MIGRATIONS)
    store.migrate()
    _seed_locked_prediction(store, "p1")
    mlb = _FakeMLB(_final_feed(hr=False))
    service = SettlementService(store, mlb)

    service.reconcile_pending()
    row_count1 = _settlement_row_count(store, "p1")
    active1 = store.active_settlement("p1")
    assert row_count1 == 1
    assert int(active1["actual_hr_binary"]) == 0

    mlb.feed = _final_feed(hr=True)  # official correction
    service.reconcile_pending()
    row_count2 = _settlement_row_count(store, "p1")
    active2 = store.active_settlement("p1")
    assert row_count2 == row_count1 + 1
    assert int(active2["actual_hr_binary"]) == 1
    assert active2["status"] == "PROVISIONAL_SETTLEMENT"
    snapshot_after_change = query_settlement_counts_and_total_pnl(store)
    assert snapshot_after_change["bankroll_events"] == 0  # not terminal yet -- no P/L

    changed_events = _audit_events(store, "PROVISIONAL_SETTLEMENT_CHANGED")
    assert len(changed_events) == 1

    service.reconcile_pending()  # recheck the corrected (now identical) value
    row_count3 = _settlement_row_count(store, "p1")
    assert row_count3 == row_count2


def test_provisional_to_confirmed_applies_pnl_and_bankroll_exactly_once(tmp_path):
    # Scenario C.
    store = SQLiteStore(tmp_path / "db.sqlite", REPO_MIGRATIONS)
    store.migrate()
    _seed_locked_prediction(store, "p1")
    store.save_settlement(_matching_provisional_seed("p1", 10))
    mlb = _FakeMLB(_final_feed(hr=True))
    service = SettlementService(store, mlb)

    stats = service.reconcile_pending()
    snapshot = query_settlement_counts_and_total_pnl(store)

    assert stats["settled"] == 1
    assert snapshot["confirmed"] == 1
    assert snapshot["bankroll_events"] == 1
    assert _settlement_row_count(store, "p1") == 2  # original provisional + the confirmation


def test_confirmed_settlement_rechecked_adds_zero_rows(tmp_path):
    # Scenario D.
    store = SQLiteStore(tmp_path / "db.sqlite", REPO_MIGRATIONS)
    store.migrate()
    _seed_locked_prediction(store, "p1")
    store.save_settlement(_matching_provisional_seed("p1", 10))
    mlb = _FakeMLB(_final_feed(hr=True))
    service = SettlementService(store, mlb)
    service.reconcile_pending()
    row_count_after_confirm = _settlement_row_count(store, "p1")
    snapshot1 = query_settlement_counts_and_total_pnl(store)

    second = service.reconcile_pending()
    third = service.reconcile_pending()
    row_count_final = _settlement_row_count(store, "p1")
    snapshot2 = query_settlement_counts_and_total_pnl(store)

    assert row_count_final == row_count_after_confirm
    assert second["settled"] == 0 and third["settled"] == 0
    assert snapshot2 == snapshot1


def test_repeated_reconcile_does_not_duplicate_combination_settlement(tmp_path):
    # Scenario E: two legs, each independently confirmed, both HR -> combo wins.
    # Repeated reconcile_pending() calls (which also drive reconcile_combinations())
    # must not add a second combination_settlements row or a second P/L.
    store = SQLiteStore(tmp_path / "db.sqlite", REPO_MIGRATIONS)
    store.migrate()
    _seed_locked_prediction(store, "leg1", player_id=10, player_name="Batter A", snapshot_id="s1")
    _seed_locked_prediction(store, "leg2", player_id=11, player_name="Batter B", snapshot_id="s2")
    for pid, pid_player in (("leg1", 10), ("leg2", 11)):
        store.save_settlement(_matching_provisional_seed(pid, pid_player))
    combo = Combination(
        combination_id="combo1", kind="BEST_2_MAN",
        legs=[
            CombinationLeg("leg1", 10, "Batter A", 0.2, ModelClassification.PRIMARY, 1),
            CombinationLeg("leg2", 11, "Batter B", 0.2, ModelClassification.PRIMARY, 1),
        ],
        model_probability_proxy=0.04, robustness=80.0, filter_status=CombinationFilterStatus.QUALIFIED,
        actual_parlay_american_odds=250, estimated_decimal_odds=3.5, warnings=[],
    )
    store.save_combination(combo)
    mlb = _FakeMLB(_final_feed_for_batters({10: True, 11: True}))
    service = SettlementService(store, mlb)

    service.reconcile_pending()  # both legs -> CONFIRMED, combo -> won
    with store.connection() as con:
        combo_rows1 = con.execute("SELECT count(*) FROM combination_settlements WHERE combination_id='combo1'").fetchone()[0]
    snapshot1 = query_settlement_counts_and_total_pnl(store)
    active_combo1 = store.active_combination_settlement("combo1")
    assert combo_rows1 == 1
    assert active_combo1["status"] == "CONFIRMED_SETTLEMENT"
    assert int(active_combo1["won"]) == 1

    service.reconcile_pending()
    service.reconcile_pending()
    with store.connection() as con:
        combo_rows2 = con.execute("SELECT count(*) FROM combination_settlements WHERE combination_id='combo1'").fetchone()[0]
    snapshot2 = query_settlement_counts_and_total_pnl(store)

    assert combo_rows2 == combo_rows1
    assert snapshot2 == snapshot1
