import json
from datetime import datetime, timedelta, timezone

import pytest

from mlb_hr.services.canonical_combinations import (
    CanonicalCombinationService,
    compute_canonical_key,
    compute_slate_scope_key,
)
from mlb_hr.storage.sqlite import SQLiteStore


@pytest.fixture()
def store(tmp_path):
    from mlb_hr.resources_runtime import packaged_migrations_dir
    with packaged_migrations_dir() as migrations_dir:
        s = SQLiteStore(tmp_path / "app.db", migrations_dir=migrations_dir)
        s.migrate()
    return s


def _insert_prediction(store, prediction_id, game_pk, game_time_iso):
    with store.transaction() as con:
        con.execute(
            """INSERT INTO snapshots(
                snapshot_id,game_pk,created_at,lineup_json,starter_json,weather_json,
                source_timestamps_json,feature_vector_json,model_package_hash,deterministic_seed
            ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (f"snap-{prediction_id}", game_pk, datetime.now(timezone.utc).isoformat(), "{}", "{}", None, "{}", "{}", "hash", 1),
        )
        con.execute(
            """INSERT INTO predictions(
                prediction_id,series_key,snapshot_id,game_pk,player_id,player_name,pitcher_id,pitcher_name,
                team_name,opponent_name,game_time,raw_probability,final_probability,matchup_score,reliability,
                confidence_score,confidence_label,p10,p50,p90,classification,user_action,critic,integrity,
                reasons_json,main_risk,warnings_json,model_version,feature_version,calibration_version,
                quality_gate_version,model_health,tracked,created_at,pregame_locked
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (prediction_id, f"series-{prediction_id}", f"snap-{prediction_id}", game_pk, hash(prediction_id) % 10000, "Player",
             1, "Pitcher", "A", "B", game_time_iso, 0.2, 0.2, 80, 90, 80, "HIGH", 0.2, 0.2, 0.2,
             "PRIMARY", "RECOMENDADO", "PASS", "PASS", "[]", None, "[]", "V1", "F1", "C1", "Q1", "GREEN",
             1, datetime.now(timezone.utc).isoformat(), 0),
        )


def _insert_combination(store, combination_id, kind, legs, created_at_iso):
    with store.transaction() as con:
        con.execute(
            """INSERT INTO combinations(
                combination_id,kind,created_at,legs_json,model_probability_proxy,robustness,
                actual_parlay_odds,estimated_decimal_odds,warnings_json,filter_status
            ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (combination_id, kind, created_at_iso, json.dumps(legs), 0.05, 80.0, None, None, "[]", "QUALIFIED"),
        )


def test_compute_canonical_key_is_stable_regardless_of_leg_order():
    legs_a = [{"player_id": 1, "game_pk": 100}, {"player_id": 2, "game_pk": 200}]
    legs_b = [{"player_id": 2, "game_pk": 200}, {"player_id": 1, "game_pk": 100}]
    assert compute_canonical_key("BEST_2_MAN", legs_a) == compute_canonical_key("BEST_2_MAN", legs_b)


def test_compute_canonical_key_differs_for_different_players():
    legs_a = [{"player_id": 1, "game_pk": 100}]
    legs_b = [{"player_id": 2, "game_pk": 100}]
    assert compute_canonical_key("BEST_2_MAN", legs_a) != compute_canonical_key("BEST_2_MAN", legs_b)


def test_compute_slate_scope_key_uses_min_game_time_in_utc_not_created_at():
    game_times = {"p1": datetime(2026, 8, 30, 23, 0, tzinfo=timezone.utc), "p2": datetime(2026, 8, 31, 1, 0, tzinfo=timezone.utc)}
    legs = [{"prediction_id": "p1", "game_pk": 100}, {"prediction_id": "p2", "game_pk": 200}]
    key = compute_slate_scope_key("BEST_2_MAN", legs, game_times)
    assert key == "BEST_2_MAN|2026-08-30"


def test_compute_slate_scope_key_stable_across_midnight_regenerations():
    # Same underlying games (fixed game_time), regenerated at two different
    # wall-clock moments -- must produce the identical slate_scope_key.
    game_times = {"p1": datetime(2026, 8, 30, 20, 0, tzinfo=timezone.utc)}
    legs = [{"prediction_id": "p1", "game_pk": 100}]
    key_before_midnight = compute_slate_scope_key("BEST_2_MAN", legs, game_times)
    key_after_midnight = compute_slate_scope_key("BEST_2_MAN", legs, game_times)
    assert key_before_midnight == key_after_midnight == "BEST_2_MAN|2026-08-30"


def test_backfill_computes_canonical_key_and_slate_scope_key_from_stored_data(store):
    _insert_prediction(store, "p1", 100, "2026-08-30T20:00:00+00:00")
    _insert_prediction(store, "p2", 200, "2026-08-30T22:00:00+00:00")
    legs = [{"prediction_id": "p1", "player_id": 1, "player_name": "A", "probability": 0.2, "classification": "PRIMARY", "game_pk": 100},
            {"prediction_id": "p2", "player_id": 2, "player_name": "B", "probability": 0.2, "classification": "PRIMARY", "game_pk": 200}]
    _insert_combination(store, "combo-1", "BEST_2_MAN", legs, "2026-08-30T23:59:00+00:00")

    CanonicalCombinationService(store).backfill_and_recanonicalize()

    with store.connection() as con:
        row = con.execute("SELECT canonical_key, slate_scope_key, is_canonical, superseded_by FROM combinations WHERE combination_id='combo-1'").fetchone()
    assert row["canonical_key"] == compute_canonical_key("BEST_2_MAN", legs)
    assert row["slate_scope_key"] == "BEST_2_MAN|2026-08-30"
    assert row["is_canonical"] == 1
    assert row["superseded_by"] is None


def test_newer_combination_with_different_legs_supersedes_older_same_slate(store):
    _insert_prediction(store, "p1", 100, "2026-08-30T20:00:00+00:00")
    _insert_prediction(store, "p2", 200, "2026-08-30T20:00:00+00:00")
    _insert_prediction(store, "p3", 300, "2026-08-30T20:00:00+00:00")
    legs_old = [{"prediction_id": "p1", "player_id": 1, "player_name": "A", "probability": 0.2, "classification": "PRIMARY", "game_pk": 100},
                {"prediction_id": "p2", "player_id": 2, "player_name": "B", "probability": 0.2, "classification": "PRIMARY", "game_pk": 200}]
    legs_new = [{"prediction_id": "p1", "player_id": 1, "player_name": "A", "probability": 0.2, "classification": "PRIMARY", "game_pk": 100},
                {"prediction_id": "p3", "player_id": 3, "player_name": "C", "probability": 0.25, "classification": "PRIMARY", "game_pk": 300}]
    _insert_combination(store, "combo-old", "BEST_2_MAN", legs_old, "2026-08-30T10:00:00+00:00")
    _insert_combination(store, "combo-new", "BEST_2_MAN", legs_new, "2026-08-30T14:00:00+00:00")

    CanonicalCombinationService(store).backfill_and_recanonicalize()

    with store.connection() as con:
        old = con.execute("SELECT is_canonical, superseded_by FROM combinations WHERE combination_id='combo-old'").fetchone()
        new = con.execute("SELECT is_canonical, superseded_by FROM combinations WHERE combination_id='combo-new'").fetchone()
    assert old["is_canonical"] == 0
    assert old["superseded_by"] == "combo-new"
    assert new["is_canonical"] == 1
    assert new["superseded_by"] is None


def test_different_slates_never_affect_each_others_canonical_row(store):
    _insert_prediction(store, "p1", 100, "2026-08-30T20:00:00+00:00")
    _insert_prediction(store, "p2", 500, "2026-09-05T20:00:00+00:00")
    legs_day1 = [{"prediction_id": "p1", "player_id": 1, "player_name": "A", "probability": 0.2, "classification": "PRIMARY", "game_pk": 100}]
    legs_day2 = [{"prediction_id": "p2", "player_id": 9, "player_name": "Z", "probability": 0.2, "classification": "PRIMARY", "game_pk": 500}]
    _insert_combination(store, "combo-day1", "BEST_2_MAN", legs_day1, "2026-08-30T10:00:00+00:00")
    _insert_combination(store, "combo-day2", "BEST_2_MAN", legs_day2, "2026-09-05T10:00:00+00:00")

    CanonicalCombinationService(store).backfill_and_recanonicalize()

    with store.connection() as con:
        day1 = con.execute("SELECT is_canonical, superseded_by FROM combinations WHERE combination_id='combo-day1'").fetchone()
        day2 = con.execute("SELECT is_canonical, superseded_by FROM combinations WHERE combination_id='combo-day2'").fetchone()
    assert day1["is_canonical"] == 1 and day1["superseded_by"] is None
    assert day2["is_canonical"] == 1 and day2["superseded_by"] is None


def test_backfill_is_idempotent(store):
    _insert_prediction(store, "p1", 100, "2026-08-30T20:00:00+00:00")
    legs = [{"prediction_id": "p1", "player_id": 1, "player_name": "A", "probability": 0.2, "classification": "PRIMARY", "game_pk": 100}]
    _insert_combination(store, "combo-1", "BEST_2_MAN", legs, "2026-08-30T10:00:00+00:00")

    svc = CanonicalCombinationService(store)
    svc.backfill_and_recanonicalize()
    with store.connection() as con:
        first = dict(con.execute("SELECT canonical_key, slate_scope_key, is_canonical, superseded_by FROM combinations WHERE combination_id='combo-1'").fetchone())
    svc.backfill_and_recanonicalize()
    with store.connection() as con:
        second = dict(con.execute("SELECT canonical_key, slate_scope_key, is_canonical, superseded_by FROM combinations WHERE combination_id='combo-1'").fetchone())
    assert first == second


def test_combination_with_a_leg_missing_its_prediction_row_is_skipped_not_crashed(store):
    # Defensive: a leg whose prediction_id was never persisted (should not
    # happen in production, but must never crash the app).
    legs = [{"prediction_id": "missing", "player_id": 1, "player_name": "A", "probability": 0.2, "classification": "PRIMARY", "game_pk": 100}]
    _insert_combination(store, "combo-1", "BEST_2_MAN", legs, "2026-08-30T10:00:00+00:00")

    CanonicalCombinationService(store).backfill_and_recanonicalize()

    with store.connection() as con:
        row = con.execute("SELECT canonical_key, slate_scope_key FROM combinations WHERE combination_id='combo-1'").fetchone()
    assert row["canonical_key"] is not None
    assert row["slate_scope_key"] is None
