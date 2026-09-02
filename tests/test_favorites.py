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
