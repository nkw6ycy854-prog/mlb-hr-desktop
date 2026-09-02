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

    def list_favorites_with_results(self) -> list[dict]:
        """Favorites joined to their canonical current prediction/settlement
        (is_latest_pregame=1 AND pregame_valid=1, the same pattern used
        everywhere else in the app) -- never derives or invents a result;
        only reads what settlement already produced. Snapshot fields are
        passed through untouched.
        """
        with self.store.connection() as con:
            rows = con.execute(
                """
                SELECT f.*, s.status settlement_status, s.actual_hr_binary, p.prediction_id cur_prediction_id
                FROM favorites f
                LEFT JOIN predictions p
                  ON p.player_id=f.player_id AND p.game_pk=f.game_pk
                 AND p.is_latest_pregame=1 AND p.pregame_valid=1
                LEFT JOIN settlements s ON s.prediction_id=p.prediction_id AND s.active=1
                ORDER BY f.created_at DESC
                """
            ).fetchall()
        out = []
        for row in rows:
            d = dict(row)
            if d["cur_prediction_id"] is None:
                d["result"] = "NO_DISPONIBLE"
            elif d["settlement_status"] == "CONFIRMED_SETTLEMENT":
                d["result"] = "HR" if d["actual_hr_binary"] else "NO_HR"
            else:
                d["result"] = "PENDING"
            out.append(d)
        return out

    def reconcile_operational_status(self, game_contexts) -> None:
        """Updates favorites.operational_status from real GameState signals
        only (POSTPONED/CANCELLED on the SAME game_pk) -- never inferred
        from a game_pk simply being absent from today's schedule, which is
        the normal case for any already-resolved favorite and would
        misfire as a false RESCHEDULED on every one of them. Never touches
        the immutable snapshot fields.
        """
        state_by_game_pk = {g.game_pk: g.state.value for g in game_contexts}
        with self.store.transaction() as con:
            for row in con.execute("SELECT player_id, game_pk FROM favorites").fetchall():
                state = state_by_game_pk.get(row["game_pk"])
                if state in ("POSTPONED", "CANCELLED"):
                    con.execute(
                        "UPDATE favorites SET operational_status=? WHERE player_id=? AND game_pk=?",
                        (state, row["player_id"], row["game_pk"]),
                    )
