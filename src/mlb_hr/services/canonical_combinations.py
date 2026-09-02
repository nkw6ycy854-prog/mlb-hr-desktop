from __future__ import annotations

import json
from datetime import datetime, timezone

from mlb_hr.storage.sqlite import SQLiteStore


def compute_canonical_key(kind: str, legs: list[dict]) -> str:
    """Identity of an exact combination attempt: kind + its players + its games.

    Order-independent (sorted), so the same set of legs always produces the
    same key regardless of what order CombinationEngine happened to list them
    in. Derived entirely from data already stored in legs_json.
    """
    player_ids = sorted({str(leg["player_id"]) for leg in legs})
    game_pks = sorted({str(leg["game_pk"]) for leg in legs})
    return f"{kind}|{'-'.join(player_ids)}|{'-'.join(game_pks)}"


def compute_slate_scope_key(kind: str, legs: list[dict], game_time_by_prediction_id: dict) -> str | None:
    """Identity of "this kind's slot for this real slate day", per the
    approved formula: kind + "|" + min(leg game_time, UTC).date().isoformat().

    game_time is MLB's own fixed scheduled first-pitch timestamp for that
    game_pk (parsed once in providers/mlb.py from MLB's "gameDate") -- it
    never changes between re-runs of analyze_slate(), unlike created_at.
    Returns None if no leg's game_time could be resolved (defensive; must
    never crash, a missing prediction row is a data anomaly, not a crash).
    """
    times = []
    for leg in legs:
        gt = game_time_by_prediction_id.get(leg.get("prediction_id"))
        if gt is not None:
            times.append(gt)
    if not times:
        return None
    earliest = min(times)
    if earliest.tzinfo is None:
        earliest = earliest.replace(tzinfo=timezone.utc)
    return f"{kind}|{earliest.astimezone(timezone.utc).date().isoformat()}"


class CanonicalCombinationService:
    """Additive, decoupled bookkeeping over the `combinations` table.

    Never touches CombinationEngine.build() or SQLiteStore.save_combination()
    -- this runs strictly after they have already written rows, either right
    after a real analyze_slate() call (forward-going canonicalization) or
    once against legacy pre-V1.2.0 rows (migration backfill). Both paths are
    the exact same idempotent operation.
    """

    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def backfill_and_recanonicalize(self) -> dict[str, int]:
        stats = {"keys_filled": 0, "keys_skipped_missing_prediction": 0, "groups_recanonicalized": 0}
        with self.store.transaction() as con:
            rows = con.execute(
                "SELECT combination_id, kind, legs_json, created_at FROM combinations WHERE canonical_key IS NULL OR slate_scope_key IS NULL"
            ).fetchall()
            all_prediction_ids: set[str] = set()
            parsed_by_id: dict[str, tuple[str, list[dict]]] = {}
            for row in rows:
                legs = json.loads(row["legs_json"] or "[]")
                parsed_by_id[row["combination_id"]] = (row["kind"], legs)
                all_prediction_ids.update(str(leg.get("prediction_id")) for leg in legs if leg.get("prediction_id"))

            game_time_by_prediction_id: dict[str, datetime] = {}
            if all_prediction_ids:
                marks = ",".join("?" for _ in all_prediction_ids)
                for pred_row in con.execute(
                    f"SELECT prediction_id, game_time FROM predictions WHERE prediction_id IN ({marks})",
                    list(all_prediction_ids),
                ).fetchall():
                    if pred_row["game_time"]:
                        game_time_by_prediction_id[pred_row["prediction_id"]] = datetime.fromisoformat(pred_row["game_time"])

            for row in rows:
                kind, legs = parsed_by_id[row["combination_id"]]
                canonical_key = compute_canonical_key(kind, legs)
                slate_scope_key = compute_slate_scope_key(kind, legs, game_time_by_prediction_id)
                if slate_scope_key is None:
                    stats["keys_skipped_missing_prediction"] += 1
                con.execute(
                    "UPDATE combinations SET canonical_key=?, slate_scope_key=? WHERE combination_id=?",
                    (canonical_key, slate_scope_key, row["combination_id"]),
                )
                stats["keys_filled"] += 1

            groups = con.execute(
                "SELECT DISTINCT kind, slate_scope_key FROM combinations WHERE slate_scope_key IS NOT NULL"
            ).fetchall()
            for group in groups:
                members = con.execute(
                    "SELECT combination_id, created_at FROM combinations WHERE kind=? AND slate_scope_key=? ORDER BY created_at DESC, combination_id DESC",
                    (group["kind"], group["slate_scope_key"]),
                ).fetchall()
                if not members:
                    continue
                canonical_id = members[0]["combination_id"]
                con.execute(
                    "UPDATE combinations SET is_canonical=1, superseded_by=NULL WHERE combination_id=?",
                    (canonical_id,),
                )
                for member in members[1:]:
                    con.execute(
                        "UPDATE combinations SET is_canonical=0, superseded_by=? WHERE combination_id=?",
                        (canonical_id, member["combination_id"]),
                    )
                stats["groups_recanonicalized"] += 1
        return stats
