from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from uuid import uuid4

from mlb_hr.storage.sqlite import SQLiteStore, utcnow_iso


class FavoriteAlreadyExists(Exception):
    """Raised when saving a (player_id, game_pk) that is already favorited.

    ELIMINAR DE FAVORITOS is a real DELETE (never soft-delete), so this can
    only happen while the same identity is still actively saved -- after a
    remove, the exact same identity can be saved again with no conflict.
    """


class FavoritesService:
    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def save_favorite(
        self, *, player_id: int, game_pk: int, player_name: str, team_name: str,
        opponent_name: str, game_time: datetime | None, hr_probability: float | None,
        practical_status: str, classification: str, confidence_label: str, eligible: bool,
        best_bookmaker: str | None, best_american_odds: int | None,
        fanduel_american_odds: int | None, source_prediction_id: str | None,
    ) -> str:
        favorite_id = str(uuid4())
        try:
            with self.store.transaction() as con:
                con.execute(
                    """INSERT INTO favorites(
                        favorite_id,player_id,game_pk,created_at,player_name,team_name,opponent_name,
                        game_time,snapshot_hr_probability,snapshot_practical_status,snapshot_classification,
                        snapshot_confidence_label,snapshot_eligible,snapshot_best_bookmaker,
                        snapshot_best_american_odds,snapshot_fanduel_american_odds,source_prediction_id,
                        operational_status
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL)""",
                    (
                        favorite_id, player_id, game_pk, utcnow_iso(), player_name, team_name, opponent_name,
                        game_time.isoformat() if game_time else None, hr_probability, practical_status,
                        classification, confidence_label, int(eligible), best_bookmaker, best_american_odds,
                        fanduel_american_odds, source_prediction_id,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise FavoriteAlreadyExists(f"player_id={player_id}, game_pk={game_pk} is already favorited") from exc
        return favorite_id

    def remove_favorite(self, *, player_id: int, game_pk: int) -> None:
        with self.store.transaction() as con:
            con.execute("DELETE FROM favorites WHERE player_id=? AND game_pk=?", (player_id, game_pk))

    def get_favorite(self, *, player_id: int, game_pk: int) -> sqlite3.Row | None:
        with self.store.connection() as con:
            return con.execute(
                "SELECT * FROM favorites WHERE player_id=? AND game_pk=?", (player_id, game_pk),
            ).fetchone()

    def list_favorites(self) -> list[sqlite3.Row]:
        with self.store.connection() as con:
            return list(con.execute("SELECT * FROM favorites ORDER BY created_at DESC"))
