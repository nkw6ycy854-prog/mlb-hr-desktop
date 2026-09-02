from datetime import datetime, timezone

import pytest

from mlb_hr.services.favorites import FavoriteAlreadyExists, FavoritesService
from mlb_hr.storage.sqlite import SQLiteStore


@pytest.fixture()
def store(tmp_path):
    from mlb_hr.resources_runtime import packaged_migrations_dir
    with packaged_migrations_dir() as migrations_dir:
        s = SQLiteStore(tmp_path / "app.db", migrations_dir=migrations_dir)
        s.migrate()
    return s


def _snapshot(**overrides):
    base = dict(
        player_id=1, game_pk=100, player_name="Aaron Judge", team_name="Yankees",
        opponent_name="Red Sox", game_time=datetime(2026, 8, 30, 23, 0, tzinfo=timezone.utc),
        hr_probability=0.22, practical_status="RECOMENDADO", classification="PRIMARY",
        confidence_label="HIGH", eligible=True, best_bookmaker="DraftKings",
        best_american_odds=350, fanduel_american_odds=390, source_prediction_id="pred-1",
    )
    base.update(overrides)
    return base


def test_save_favorite_persists_immutable_snapshot(store):
    svc = FavoritesService(store)
    favorite_id = svc.save_favorite(**_snapshot())
    fav = svc.get_favorite(player_id=1, game_pk=100)
    assert fav is not None
    assert fav["favorite_id"] == favorite_id
    assert fav["player_name"] == "Aaron Judge"
    assert fav["snapshot_hr_probability"] == 0.22
    assert fav["snapshot_practical_status"] == "RECOMENDADO"
    assert fav["snapshot_eligible"] == 1
    assert fav["snapshot_best_american_odds"] == 350
    assert fav["snapshot_fanduel_american_odds"] == 390


def test_saving_the_same_identity_twice_raises_already_exists(store):
    svc = FavoritesService(store)
    svc.save_favorite(**_snapshot())
    with pytest.raises(FavoriteAlreadyExists):
        svc.save_favorite(**_snapshot())


def test_remove_favorite_is_a_real_delete_not_soft_delete(store):
    svc = FavoritesService(store)
    svc.save_favorite(**_snapshot())
    svc.remove_favorite(player_id=1, game_pk=100)
    assert svc.get_favorite(player_id=1, game_pk=100) is None
    with store.connection() as con:
        count = con.execute("SELECT count(*) FROM favorites").fetchone()[0]
    assert count == 0


def test_save_remove_save_again_works_without_conflict(store):
    svc = FavoritesService(store)
    first_id = svc.save_favorite(**_snapshot())
    svc.remove_favorite(player_id=1, game_pk=100)
    second_id = svc.save_favorite(**_snapshot(hr_probability=0.30))
    assert second_id != first_id
    fav = svc.get_favorite(player_id=1, game_pk=100)
    assert fav["snapshot_hr_probability"] == 0.30


def test_list_favorites_returns_all_current_ones_most_recent_first(store):
    svc = FavoritesService(store)
    svc.save_favorite(**_snapshot(player_id=1, game_pk=100, player_name="A"))
    svc.save_favorite(**_snapshot(player_id=2, game_pk=200, player_name="B"))
    names = [f["player_name"] for f in svc.list_favorites()]
    assert names == ["B", "A"]


def test_snapshot_never_updates_after_save(store):
    svc = FavoritesService(store)
    svc.save_favorite(**_snapshot(hr_probability=0.22))
    fav = svc.get_favorite(player_id=1, game_pk=100)
    assert fav["snapshot_hr_probability"] == 0.22
    # No update method exists at all for snapshot fields -- there is nothing
    # to call here. This test documents that guarantee via the public API
    # surface: FavoritesService only exposes save/remove/get/list.
    assert not hasattr(svc, "update_snapshot")


def test_different_players_or_games_do_not_collide(store):
    svc = FavoritesService(store)
    svc.save_favorite(**_snapshot(player_id=1, game_pk=100))
    svc.save_favorite(**_snapshot(player_id=1, game_pk=200))  # same player, different game
    svc.save_favorite(**_snapshot(player_id=2, game_pk=100))  # different player, same game
    assert len(svc.list_favorites()) == 3


def _insert_snapshot_and_prediction(store, prediction_id, player_id, game_pk):
    with store.transaction() as con:
        con.execute(
            """INSERT INTO snapshots(snapshot_id,game_pk,created_at,lineup_json,starter_json,weather_json,
                source_timestamps_json,feature_vector_json,model_package_hash,deterministic_seed)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (f"snap-{prediction_id}", game_pk, "2026-08-30T18:00:00+00:00", "{}", "{}", None, "{}", "{}", "hash", 1),
        )
        con.execute(
            """INSERT INTO predictions(
                prediction_id,series_key,snapshot_id,game_pk,player_id,player_name,pitcher_id,pitcher_name,
                team_name,opponent_name,game_time,raw_probability,final_probability,matchup_score,reliability,
                confidence_score,confidence_label,p10,p50,p90,classification,user_action,critic,integrity,
                reasons_json,main_risk,warnings_json,model_version,feature_version,calibration_version,
                quality_gate_version,model_health,tracked,created_at,pregame_locked,is_latest_pregame,pregame_valid
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,1)""",
            (prediction_id, f"series-{prediction_id}", f"snap-{prediction_id}", game_pk, player_id, "Aaron Judge",
             9, "Pitcher", "Yankees", "Red Sox", "2026-08-30T23:00:00+00:00", 0.22, 0.22, 80, 90, 80, "HIGH",
             0.22, 0.22, 0.22, "PRIMARY", "RECOMENDADO", "PASS", "PASS", "[]", None, "[]", "V1", "F1", "C1", "Q1",
             "GREEN", 1, "2026-08-30T18:00:00+00:00", 1),
        )


def _insert_settlement(store, prediction_id, status, actual_hr_binary):
    with store.transaction() as con:
        con.execute(
            """INSERT INTO settlements(
                prediction_id,result_version,status,actual_hr_count,actual_hr_binary,actual_pa,
                actual_pa_vs_starter,actual_pa_vs_bullpen,appearance_status,verified_pbp,verified_box,
                result_source,fetched_at,active
            ) VALUES(?,1,?,?,?,?,?,?,?,?,?,?,?,1)""",
            (prediction_id, status, actual_hr_binary, actual_hr_binary, 3, 2, 1, "STARTED_AND_BATTED", 1, 1,
             "MLB", "2026-08-31T02:00:00+00:00"),
        )


def test_list_favorites_with_results_shows_pendiente_when_not_settled(store):
    svc = FavoritesService(store)
    svc.save_favorite(**_snapshot())
    _insert_snapshot_and_prediction(store, "pred-1", 1, 100)

    rows = svc.list_favorites_with_results()

    assert rows[0]["result"] == "PENDING"


def test_list_favorites_with_results_shows_hr_when_settled_confirmed(store):
    svc = FavoritesService(store)
    svc.save_favorite(**_snapshot())
    _insert_snapshot_and_prediction(store, "pred-1", 1, 100)
    _insert_settlement(store, "pred-1", "CONFIRMED_SETTLEMENT", 1)

    rows = svc.list_favorites_with_results()

    assert rows[0]["result"] == "HR"


def test_list_favorites_with_results_shows_no_disponible_when_no_current_prediction(store):
    svc = FavoritesService(store)
    svc.save_favorite(**_snapshot())
    # No predictions/settlements inserted -- the canonical prediction is gone.

    rows = svc.list_favorites_with_results()

    assert rows[0]["result"] == "NO_DISPONIBLE"


def test_list_favorites_with_results_never_touches_snapshot_fields(store):
    svc = FavoritesService(store)
    svc.save_favorite(**_snapshot(hr_probability=0.22))
    _insert_snapshot_and_prediction(store, "pred-1", 1, 100)
    _insert_settlement(store, "pred-1", "CONFIRMED_SETTLEMENT", 1)

    rows = svc.list_favorites_with_results()

    assert rows[0]["snapshot_hr_probability"] == 0.22


def test_reconcile_operational_status_marks_postponed_from_game_state(store):
    from types import SimpleNamespace

    svc = FavoritesService(store)
    svc.save_favorite(**_snapshot(player_id=1, game_pk=100))
    game_contexts = [SimpleNamespace(game_pk=100, state=SimpleNamespace(value="POSTPONED"))]

    svc.reconcile_operational_status(game_contexts)

    fav = svc.get_favorite(player_id=1, game_pk=100)
    assert fav["operational_status"] == "POSTPONED"


def test_reconcile_operational_status_marks_cancelled(store):
    from types import SimpleNamespace

    svc = FavoritesService(store)
    svc.save_favorite(**_snapshot(player_id=1, game_pk=100))
    game_contexts = [SimpleNamespace(game_pk=100, state=SimpleNamespace(value="CANCELLED"))]

    svc.reconcile_operational_status(game_contexts)

    fav = svc.get_favorite(player_id=1, game_pk=100)
    assert fav["operational_status"] == "CANCELLED"


def test_reconcile_operational_status_leaves_untouched_when_game_pregame(store):
    from types import SimpleNamespace

    svc = FavoritesService(store)
    svc.save_favorite(**_snapshot(player_id=1, game_pk=100))
    game_contexts = [SimpleNamespace(game_pk=100, state=SimpleNamespace(value="PREGAME"))]

    svc.reconcile_operational_status(game_contexts)

    fav = svc.get_favorite(player_id=1, game_pk=100)
    assert fav["operational_status"] is None


def test_reconcile_operational_status_never_touches_a_favorite_whose_game_is_simply_absent(store):
    # A favorite's game_pk not appearing in *today's* schedule is normal
    # (the game already happened on a prior day) -- must never be
    # auto-labeled RESCHEDULED from absence alone; that would misfire on
    # every single already-resolved favorite. Only explicit POSTPONED/
    # CANCELLED signals from a real GameContext update this field.
    from types import SimpleNamespace

    svc = FavoritesService(store)
    svc.save_favorite(**_snapshot(player_id=1, game_pk=100))
    svc.reconcile_operational_status([SimpleNamespace(game_pk=999, state=SimpleNamespace(value="PREGAME"))])

    fav = svc.get_favorite(player_id=1, game_pk=100)
    assert fav["operational_status"] is None
