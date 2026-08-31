from datetime import date, datetime, timedelta, timezone
import json

from mlb_hr.services.daily_accuracy import DailyAccuracyService


class FakeStore:
    def __init__(self, player_rows=None, combo_rows=None, prediction_rows=None, leg_settlement_rows=None):
        self._player_rows = player_rows or []
        self._combo_rows = combo_rows or []
        self._prediction_rows = prediction_rows or {}
        self._leg_settlement_rows = leg_settlement_rows or {}

    def history_prediction_rows(self, limit=2000):
        return list(self._player_rows)

    def history_combination_rows(self, limit=1000):
        return list(self._combo_rows)

    def prediction_rows_by_ids(self, ids):
        return {pid: self._prediction_rows[pid] for pid in ids if pid in self._prediction_rows}

    def leg_settlements(self, ids):
        return {pid: self._leg_settlement_rows[pid] for pid in ids if pid in self._leg_settlement_rows}


TODAY = date(2026, 8, 30)
GAME_TIME = datetime(2026, 8, 30, 23, 15, tzinfo=timezone.utc)  # 7:15 PM America/Santo_Domingo, still 8/30 there


def _player_row(prediction_id, *, classification="PRIMARY", final_probability=0.10,
                 game_time=GAME_TIME, created_at=None, actual_hr_binary=None,
                 odds_at_prediction=150, pnl_amount=None, player_name="Aaron Judge",
                 game_pk=1, team_name="Team A", opponent_name="Team B"):
    created_at = created_at or (game_time - timedelta(hours=3))
    return {
        "prediction_id": prediction_id, "player_name": player_name,
        "game_time": game_time.isoformat(), "created_at": created_at.isoformat(),
        "classification": classification, "final_probability": final_probability,
        "reference_stake": 10.0, "odds_at_prediction": odds_at_prediction,
        "actual_hr_binary": actual_hr_binary, "pnl_amount": pnl_amount,
        "game_pk": game_pk, "team_name": team_name, "opponent_name": opponent_name,
    }


def _combo_row(combination_id, *, filter_status="QUALIFIED", created_at=GAME_TIME, legs,
               won=None, profit_loss=None, kind="BEST_2_MAN", estimated_decimal_odds=2.5):
    return {
        "combination_id": combination_id, "kind": kind, "created_at": created_at.isoformat(),
        "legs_json": json.dumps(legs), "filter_status": filter_status,
        "won": won, "profit_loss": profit_loss, "estimated_decimal_odds": estimated_decimal_odds,
    }


def test_only_predictions_at_or_above_5_percent_enter_the_eligible_population():
    rows = [
        _player_row("below", final_probability=0.049),
        _player_row("at_threshold", final_probability=0.050),
        _player_row("well_above", final_probability=0.12),
        _player_row("not_eligible", classification="NOT_ELIGIBLE", final_probability=0.20),
    ]
    store = FakeStore(player_rows=rows)
    service = DailyAccuracyService(store)

    result = service.for_date(TODAY, "America/Santo_Domingo")

    ids = {p.prediction_id for p in result.players}
    assert ids == {"at_threshold", "well_above"}


def test_pending_does_not_count_as_a_miss_or_enter_the_denominator():
    rows = (
        [_player_row(f"hr{i}", actual_hr_binary=1) for i in range(2)]
        + [_player_row(f"no{i}", actual_hr_binary=0) for i in range(6)]
        + [_player_row(f"pending{i}", actual_hr_binary=None) for i in range(2)]
    )
    store = FakeStore(player_rows=rows)
    service = DailyAccuracyService(store)

    summary = service.for_date(TODAY, "America/Santo_Domingo").summary

    assert summary.resolved_predictions == 8
    assert summary.player_hits == 2
    assert summary.player_hit_rate == 0.25
    assert summary.player_pending == 2


def test_prediction_made_after_the_game_started_is_excluded():
    rows = [
        _player_row("pregame", created_at=GAME_TIME - timedelta(hours=1)),
        _player_row("too_late", created_at=GAME_TIME + timedelta(minutes=5)),
        _player_row("exactly_at_start", created_at=GAME_TIME),
    ]
    store = FakeStore(player_rows=rows)
    service = DailyAccuracyService(store)

    result = service.for_date(TODAY, "America/Santo_Domingo")

    ids = {p.prediction_id for p in result.players}
    assert ids == {"pregame"}


def test_combination_summary_counts_won_lost_and_pending():
    legs_a = [{"prediction_id": "a1", "player_id": 1, "player_name": "A1", "probability": .1, "classification": "PRIMARY", "game_pk": 1}]
    legs_b = [{"prediction_id": "b1", "player_id": 2, "player_name": "B1", "probability": .1, "classification": "PRIMARY", "game_pk": 1}]
    legs_c = [{"prediction_id": "c1", "player_id": 3, "player_name": "C1", "probability": .1, "classification": "PRIMARY", "game_pk": 1}]
    combo_rows = [
        _combo_row("won", legs=legs_a, won=1, profit_loss=25.0),
        _combo_row("lost", legs=legs_b, won=0, profit_loss=-10.0),
        _combo_row("pending", legs=legs_c, won=None),
    ]
    prediction_rows = {
        "a1": {"game_time": GAME_TIME.isoformat()},
        "b1": {"game_time": GAME_TIME.isoformat()},
        "c1": {"game_time": GAME_TIME.isoformat()},
    }
    store = FakeStore(combo_rows=combo_rows, prediction_rows=prediction_rows)
    service = DailyAccuracyService(store)

    summary = service.for_date(TODAY, "America/Santo_Domingo").summary

    assert summary.combo_wins == 1
    assert summary.combo_pending == 1
