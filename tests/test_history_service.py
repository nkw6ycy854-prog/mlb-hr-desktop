from datetime import datetime, timedelta, timezone
import json

from mlb_hr.services.history import (
    HistoryFilter,
    HistoryService,
    PlayerHistoryRecord,
)


class FakeStore:
    def __init__(self, player_rows=None, combo_rows=None, prediction_rows=None):
        self._player_rows = player_rows or []
        self._combo_rows = combo_rows or []
        self._prediction_rows = prediction_rows or {}

    def history_prediction_rows(self, limit=2000):
        return list(self._player_rows)

    def history_combination_rows(self, limit=1000):
        return list(self._combo_rows)

    def prediction_rows_by_ids(self, ids):
        return {pid: self._prediction_rows[pid] for pid in ids if pid in self._prediction_rows}


def _player_row(prediction_id, *, classification, game_time, created_at, final_probability=0.25,
                 reference_stake=10.0, odds_at_prediction=150, actual_hr_binary=None, pnl_amount=None,
                 player_name="Aaron Judge"):
    return {
        "prediction_id": prediction_id, "player_name": player_name,
        "game_time": game_time, "created_at": created_at,
        "classification": classification, "final_probability": final_probability,
        "reference_stake": reference_stake, "odds_at_prediction": odds_at_prediction,
        "actual_hr_binary": actual_hr_binary, "pnl_amount": pnl_amount,
    }


def _combo_row(combination_id, *, filter_status, created_at, legs, won=None, profit_loss=None,
               kind="BEST_2_MAN", estimated_decimal_odds=2.5):
    return {
        "combination_id": combination_id, "kind": kind, "created_at": created_at,
        "legs_json": json.dumps(legs), "filter_status": filter_status,
        "won": won, "profit_loss": profit_loss, "estimated_decimal_odds": estimated_decimal_odds,
    }


def test_history_filter_combines_period_status_and_result():
    now = datetime(2026, 8, 26, 20, 0, tzinfo=timezone.utc)
    rows = [
        _player_row("p1", classification="PRIMARY", game_time=(now - timedelta(days=5)).isoformat(),
                    created_at=(now - timedelta(days=5)).isoformat(), actual_hr_binary=1),
        _player_row("p2", classification="PRIMARY", game_time=(now - timedelta(days=5)).isoformat(),
                    created_at=(now - timedelta(days=5)).isoformat(), actual_hr_binary=0),
        _player_row("p3", classification="WATCH", game_time=(now - timedelta(days=5)).isoformat(),
                    created_at=(now - timedelta(days=5)).isoformat(), actual_hr_binary=1),
        _player_row("p4", classification="PRIMARY", game_time=(now - timedelta(days=40)).isoformat(),
                    created_at=(now - timedelta(days=40)).isoformat(), actual_hr_binary=1),
    ]
    store = FakeStore(player_rows=rows)
    service = HistoryService(store)

    records = service.player_records(HistoryFilter(period="30D", status="RECOMMENDED", result="HR"), now)

    assert [r.prediction_id for r in records] == ["p1"]


def test_not_eligible_rows_never_appear_in_player_history():
    now = datetime(2026, 8, 26, 20, 0, tzinfo=timezone.utc)
    rows = [_player_row("p1", classification="NOT_ELIGIBLE", game_time=now.isoformat(), created_at=now.isoformat())]
    store = FakeStore(player_rows=rows)
    service = HistoryService(store)

    records = service.player_records(HistoryFilter(), now)

    assert records == []


def test_player_records_parses_game_time_as_timezone_aware_and_does_not_mutate_store():
    now = datetime(2026, 8, 26, 20, 0, tzinfo=timezone.utc)
    rows = [_player_row("p1", classification="PRIMARY", game_time="2026-08-26T19:05:00+00:00",
                         created_at="2026-08-26T18:00:00+00:00", actual_hr_binary=None)]
    store = FakeStore(player_rows=rows)
    service = HistoryService(store)

    records = service.player_records(HistoryFilter(), now)

    assert records[0].game_time.tzinfo is not None
    assert store.history_prediction_rows() == rows


def test_combination_records_uses_earliest_leg_game_time_as_start():
    now = datetime(2026, 8, 26, 20, 0, tzinfo=timezone.utc)
    legs = [
        {"prediction_id": "p1", "player_id": 1, "player_name": "Aaron Judge", "probability": .3, "classification": "PRIMARY", "game_pk": 1},
        {"prediction_id": "p2", "player_id": 2, "player_name": "Juan Soto", "probability": .28, "classification": "SECONDARY", "game_pk": 2},
    ]
    combo_row = _combo_row("c1", filter_status="QUALIFIED", created_at=now.isoformat(), legs=legs, won=1, profit_loss=25.0)
    prediction_rows = {
        "p1": {"game_time": "2026-08-26T19:05:00+00:00"},
        "p2": {"game_time": "2026-08-26T18:40:00+00:00"},
    }
    store = FakeStore(combo_rows=[combo_row], prediction_rows=prediction_rows)
    service = HistoryService(store)

    records = service.combination_records(HistoryFilter(), now)

    assert len(records) == 1
    record = records[0]
    assert record.start_time == datetime(2026, 8, 26, 18, 40, tzinfo=timezone.utc)
    assert record.status == "RECOMMENDED"
    assert record.result == "HR"
    assert {leg.player_name for leg in record.legs} == {"Aaron Judge", "Juan Soto"}
    assert all(leg.game_time is not None for leg in record.legs)


def test_fallback_combination_with_no_settlement_is_pending_and_no_filter():
    now = datetime(2026, 8, 26, 20, 0, tzinfo=timezone.utc)
    legs = [{"prediction_id": "p1", "player_id": 1, "player_name": "Player C", "probability": .1, "classification": "WATCH", "game_pk": 1}]
    combo_row = _combo_row("c2", filter_status="FALLBACK", created_at=now.isoformat(), legs=legs)
    store = FakeStore(combo_rows=[combo_row], prediction_rows={"p1": {"game_time": None}})
    service = HistoryService(store)

    records = service.combination_records(HistoryFilter(), now)

    assert records[0].status == "NO_FILTER"
    assert records[0].result == "PENDING"


def test_summarize_players_computes_hit_rate_and_roi():
    now = datetime(2026, 8, 26, 20, 0, tzinfo=timezone.utc)
    records = [
        PlayerHistoryRecord(prediction_id="p1", player_name="A", game_time=None, created_at=now,
                             classification="PRIMARY", status="RECOMMENDED", final_probability=.3,
                             reference_stake=10.0, odds_at_prediction=150, result="HR", pnl=25.0),
        PlayerHistoryRecord(prediction_id="p2", player_name="B", game_time=None, created_at=now,
                             classification="PRIMARY", status="RECOMMENDED", final_probability=.25,
                             reference_stake=10.0, odds_at_prediction=-120, result="NO_HR", pnl=-10.0),
    ]
    summary = HistoryService.summarize_players(records)
    assert summary["analyzed"] == 2
    assert summary["hits"] == 1
    assert summary["hit_rate"] == 0.5
    assert summary["pnl"] == 15.0
    assert summary["roi"] == 15.0 / 20.0
