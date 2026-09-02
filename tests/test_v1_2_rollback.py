"""Mandatory V1.2.0 -> V1.1.0 rollback test (approved plan, point 3).

Builds a DB with V1.2.0's current migrations (001-005) applied and seeded
with representative data, then runs the REAL, unmodified v1.1.0 tag's own
`storage/sqlite.py` -- via a genuinely separate subprocess with its own
PYTHONPATH pointing at a `git worktree` checkout of that tag, not a
same-process import -- against that exact DB file. Confirms V1.1.0's own
migrate() is a no-op (it only knows migrations 001-004) and that its real
read/write methods keep working without exception or data loss, proving the
rollback path the plan requires.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from mlb_hr.storage.sqlite import SQLiteStore

ROOT = Path(__file__).resolve().parents[1]
BASELINE_TAG = "v1.1.0"


@pytest.fixture(scope="module")
def v1_1_0_worktree(tmp_path_factory):
    path = tmp_path_factory.mktemp("v1_1_0_worktree_parent") / "worktree"
    subprocess.run(
        ["git", "worktree", "add", "--detach", str(path), BASELINE_TAG],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )
    try:
        yield path
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", str(path)], cwd=ROOT, check=False, capture_output=True)
        subprocess.run(["git", "worktree", "prune"], cwd=ROOT, check=False, capture_output=True)


_V1_1_0_PROBE_SCRIPT = """
import json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[2])
from mlb_hr.storage.sqlite import SQLiteStore, SCHEMA_VERSION

db_path = Path(sys.argv[1])
store = SQLiteStore(db_path, migrations_dir=Path(sys.argv[2]).parent / "migrations")
result = {"schema_version_constant": SCHEMA_VERSION}

before = None
with store.connection() as con:
    before = sorted(r[0] for r in con.execute("SELECT version FROM schema_migrations"))
result["applied_before_migrate"] = before

store.migrate()  # must be a safe no-op: v1.1.0 only knows migrations 001-004

with store.connection() as con:
    result["applied_after_migrate"] = sorted(r[0] for r in con.execute("SELECT version FROM schema_migrations"))
    result["prediction_count"] = con.execute("SELECT count(*) FROM predictions").fetchone()[0]
    result["combination_count"] = con.execute("SELECT count(*) FROM combinations").fetchone()[0]
    result["favorites_row_survives"] = con.execute("SELECT count(*) FROM favorites").fetchone()[0]

rows = store.history_combination_rows()
result["history_combination_rows_count"] = len(rows)
rows = store.history_prediction_rows()
result["history_prediction_rows_count"] = len(rows)

# V1.1.0 must still be able to WRITE new rows against this migrated DB.
store.log_audit(module="rollback_probe", severity="INFO", event_code="V1_1_0_WRITE_PROBE", payload={"ok": True})
with store.connection() as con:
    result["audit_write_succeeded"] = con.execute(
        "SELECT count(*) FROM audit_events WHERE event_code='V1_1_0_WRITE_PROBE'"
    ).fetchone()[0] == 1

print(json.dumps(result))
"""


def _seed_v1_2_0_db(db_path: Path) -> None:
    from mlb_hr.resources_runtime import packaged_migrations_dir

    with packaged_migrations_dir() as migrations_dir:
        store = SQLiteStore(db_path, migrations_dir=migrations_dir)
        store.migrate()

    with store.transaction() as con:
        con.execute(
            """INSERT INTO snapshots(snapshot_id,game_pk,created_at,lineup_json,starter_json,weather_json,
                source_timestamps_json,feature_vector_json,model_package_hash,deterministic_seed)
               VALUES('snap-1',100,'2026-08-30T20:00:00+00:00','{}','{}',NULL,'{}','{}','hash',1)"""
        )
        con.execute(
            """INSERT INTO predictions(
                prediction_id,series_key,snapshot_id,game_pk,player_id,player_name,pitcher_id,pitcher_name,
                team_name,opponent_name,game_time,raw_probability,final_probability,matchup_score,reliability,
                confidence_score,confidence_label,p10,p50,p90,classification,user_action,critic,integrity,
                reasons_json,main_risk,warnings_json,model_version,feature_version,calibration_version,
                quality_gate_version,model_health,tracked,created_at,pregame_locked
            ) VALUES('pred-1','series-1','snap-1',100,1,'Aaron Judge',9,'Pitcher','Yankees','Red Sox',
                '2026-08-30T20:00:00+00:00',0.2,0.2,80,90,80,'HIGH',0.2,0.2,0.2,'PRIMARY','RECOMENDADO',
                'PASS','PASS','[]',NULL,'[]','V1','F1','C1','Q1','GREEN',1,'2026-08-30T18:00:00+00:00',1)"""
        )
        con.execute(
            """INSERT INTO combinations(
                combination_id,kind,created_at,legs_json,model_probability_proxy,robustness,
                actual_parlay_odds,estimated_decimal_odds,warnings_json,filter_status
            ) VALUES('combo-1','BEST_2_MAN','2026-08-30T18:05:00+00:00',
                '[{"prediction_id":"pred-1","player_id":1,"player_name":"Aaron Judge","probability":0.2,"classification":"PRIMARY","game_pk":100}]',
                0.05,80.0,NULL,NULL,'[]','QUALIFIED')"""
        )
        con.execute(
            """INSERT INTO favorites(
                favorite_id,player_id,game_pk,created_at,player_name,team_name,opponent_name,game_time,
                snapshot_hr_probability,snapshot_practical_status,snapshot_classification,
                snapshot_confidence_label,snapshot_eligible,snapshot_best_bookmaker,snapshot_best_american_odds,
                snapshot_fanduel_american_odds,source_prediction_id,operational_status
            ) VALUES('fav-1',1,100,'2026-08-30T18:10:00+00:00','Aaron Judge','Yankees','Red Sox',
                '2026-08-30T20:00:00+00:00',0.2,'RECOMENDADO','PRIMARY','HIGH',1,'DraftKings',350,390,
                'pred-1',NULL)"""
        )

    # Mirrors the real forward-going flow: canonicalization runs after new
    # combination rows are saved, not just once at migration time.
    from mlb_hr.services.canonical_combinations import CanonicalCombinationService
    CanonicalCombinationService(store).backfill_and_recanonicalize()


def test_v1_1_0_code_opens_a_v1_2_0_migrated_db_without_error_or_data_loss(v1_1_0_worktree, tmp_path):
    db_path = tmp_path / "rollback.db"
    _seed_v1_2_0_db(db_path)

    with SQLiteStore(db_path).connection() as con:
        applied_before = sorted(r[0] for r in con.execute("SELECT version FROM schema_migrations"))
    assert applied_before == [1, 2, 3, 4, 5]

    worktree_src = v1_1_0_worktree / "src"
    proc = subprocess.run(
        [sys.executable, "-c", _V1_1_0_PROBE_SCRIPT, str(db_path), str(worktree_src)],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, f"v1.1.0 code raised against the migrated DB:\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr}"
    result = json.loads(proc.stdout.strip().splitlines()[-1])

    assert result["schema_version_constant"] == 4, "sanity check: this really is v1.1.0's own code, not V1.2.0's"
    # The core finding of the approved plan's inspection: v1.1.0's migrate()
    # has no future-version guard -- it only knows migrations 1-4, sees all
    # of them already applied, and is a silent, safe no-op.
    assert result["applied_before_migrate"] == [1, 2, 3, 4, 5]
    assert result["applied_after_migrate"] == [1, 2, 3, 4, 5], "v1.1.0's migrate() must not alter schema_migrations at all"

    assert result["prediction_count"] == 1
    assert result["combination_count"] == 1
    assert result["favorites_row_survives"] == 1, "the favorites table (unknown to v1.1.0) must survive untouched"
    assert result["history_combination_rows_count"] == 1
    assert result["history_prediction_rows_count"] == 1
    assert result["audit_write_succeeded"] is True, "v1.1.0 must still be able to write new rows to this DB"

    # And nothing on the V1.2.0 side got corrupted by the v1.1.0 process either.
    with SQLiteStore(db_path).connection() as con:
        canonical_key = con.execute("SELECT canonical_key FROM combinations WHERE combination_id='combo-1'").fetchone()[0]
        fav = con.execute("SELECT * FROM favorites WHERE favorite_id='fav-1'").fetchone()
    assert canonical_key is not None
    assert fav["snapshot_hr_probability"] == 0.2
