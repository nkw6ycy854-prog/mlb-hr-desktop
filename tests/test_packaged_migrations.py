from pathlib import Path
import shutil
import tempfile

from mlb_hr.resources_runtime import packaged_migrations_dir
from mlb_hr.storage.sqlite import SQLiteStore

ROOT = Path(__file__).resolve().parents[1]


def _build_v3_database_with_existing_combination(db_path: Path) -> None:
    """Reproduce a real pre-existing user database that only ever saw migrations
    001-003 (i.e. created before combinations.filter_status existed), with one
    real row already saved under the old (pre-004) schema.
    """
    canonical_migrations = ROOT / "migrations"
    with tempfile.TemporaryDirectory() as staged:
        staged_dir = Path(staged)
        for name in ("001_initial.sql", "002_combination_settlement.sql", "003_pregame_invalidation.sql"):
            shutil.copy2(canonical_migrations / name, staged_dir / name)
        store = SQLiteStore(db_path, staged_dir)
        store.migrate()
        with store.connection() as con:
            con.execute(
                """INSERT INTO combinations(
                       combination_id,kind,created_at,legs_json,model_probability_proxy,
                       robustness,actual_parlay_odds,estimated_decimal_odds,warnings_json
                   ) VALUES(?,?,?,?,?,?,?,?,?)""",
                ("existing-combo-1", "BEST_2_MAN", "2026-08-22T00:00:00+00:00", "[]", 0.05, 80.0, None, None, "[]"),
            )


def test_packaged_migrations_directory_brings_a_v3_user_database_to_current(tmp_path):
    db_path = tmp_path / "app.db"
    _build_v3_database_with_existing_combination(db_path)

    # Sanity check: confirm this reproduces the exact reported bug state.
    with SQLiteStore(db_path).connection() as con:
        applied_before = {r[0] for r in con.execute("SELECT version FROM schema_migrations")}
        assert applied_before == {1, 2, 3}
        cols_before = {r[1] for r in con.execute("PRAGMA table_info(combinations)")}
        assert "filter_status" not in cols_before

    # This is the exact mechanism build_services() (and therefore the real native
    # app) uses to resolve its migrations directory -- NOT the top-level
    # migrations/ folder that most tests reference directly.
    with packaged_migrations_dir() as migrations_dir:
        store = SQLiteStore(db_path, migrations_dir)
        store.migrate()

    with store.connection() as con:
        applied_after = {r[0] for r in con.execute("SELECT version FROM schema_migrations")}
        assert applied_after == {1, 2, 3, 4, 5}
        cols_after = {r[1] for r in con.execute("PRAGMA table_info(combinations)")}
        assert "filter_status" in cols_after
        assert {"canonical_key", "slate_scope_key", "is_canonical", "superseded_by"} <= cols_after
        assert {r[1] for r in con.execute("PRAGMA table_info(favorites)")}, "favorites table must exist after migration"

        row = con.execute(
            "SELECT combination_id, filter_status, canonical_key, is_canonical FROM combinations WHERE combination_id=?",
            ("existing-combo-1",),
        ).fetchone()
        assert row is not None, "pre-existing user data must survive the migration"
        assert row["filter_status"] == "QUALIFIED"
        # V1.2.0's backfill (migration 005) must reach this v3-origin row too --
        # it has no legs (legs_json="[]"), so canonical_key is still computed
        # deterministically (empty-but-present); slate_scope_key stays NULL
        # (no leg game_time to resolve), so this row is never grouped by the
        # recanonicalization pass and simply keeps its column default (true).
        assert row["canonical_key"] is not None
        assert row["is_canonical"] == 1


def test_packaged_migrations_directory_matches_canonical_migrations_directory():
    """Guard against the two migration directories drifting apart again: every
    migration file present at the repo root must also be packaged under
    src/mlb_hr/resources/migrations (and vice versa).
    """
    canonical = {p.name for p in (ROOT / "migrations").glob("*.sql")}
    with packaged_migrations_dir() as migrations_dir:
        packaged = {p.name for p in migrations_dir.glob("*.sql")}
    assert canonical == packaged
