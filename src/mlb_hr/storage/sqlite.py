from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator

from mlb_hr.domain.models import Combination, OddsQuote, Prediction, ResultRecord


SCHEMA_VERSION = 3


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SQLiteStore:
    def __init__(self, db_path: Path, migrations_dir: Path | None = None) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.migrations_dir = migrations_dir or Path(__file__).resolve().parents[3] / "migrations"

    def connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path, timeout=15.0)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=NORMAL")
        return con

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """Yield a SQLite connection and always close it on exit.

        sqlite3.Connection's own context manager commits/rolls back but does
        not close the underlying file handle. That leaks handles on Windows
        and can prevent TemporaryDirectory cleanup with WinError 32.
        """
        con = self.connect()
        try:
            with con:
                yield con
        finally:
            con.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        con = self.connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def migrate(self) -> None:
        self.migrations_dir.mkdir(parents=True, exist_ok=True)
        existed_before = self.db_path.exists() and self.db_path.stat().st_size > 0
        files = sorted(self.migrations_dir.glob("*.sql"))
        versions=[]
        for path in files:
            try: versions.append((int(path.name.split("_",1)[0]),path))
            except ValueError: continue
        with self.connection() as con:
            con.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
            applied={int(r[0]) for r in con.execute("SELECT version FROM schema_migrations")}
        pending=[(v,p) for v,p in versions if v not in applied]
        if existed_before and pending:
            self._backup_before_migration()
        with self.connection() as con:
            for version,path in pending:
                script=path.read_text(encoding="utf-8")
                con.executescript(script)
                con.execute("INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",(version,utcnow_iso()))
            con.commit()

    def _backup_before_migration(self) -> Path:
        backup=self.db_path.with_suffix(self.db_path.suffix+".pre_migration.bak")
        tmp=backup.with_suffix(backup.suffix+".tmp")
        tmp.unlink(missing_ok=True)
        source=self.connect()
        dest=sqlite3.connect(tmp)
        try:
            source.backup(dest);dest.commit()
        finally:
            dest.close();source.close()
        tmp.replace(backup)
        return backup

    def set_state(self, key: str, value: Any) -> None:
        payload = json.dumps(value, ensure_ascii=False, default=str)
        with self.transaction() as con:
            con.execute(
                "INSERT INTO app_state(key,value_json,updated_at) VALUES(?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, updated_at=excluded.updated_at",
                (key, payload, utcnow_iso()),
            )

    def get_state(self, key: str, default: Any = None) -> Any:
        with self.connection() as con:
            row = con.execute("SELECT value_json FROM app_state WHERE key=?", (key,)).fetchone()
        if not row:
            return default
        return json.loads(row[0])

    def save_snapshot(
        self,
        *,
        snapshot_id: str,
        game_pk: int,
        lineup: Any,
        starter: Any,
        weather: Any,
        source_timestamps: Any,
        feature_vector: Any,
        model_package_hash: str,
        deterministic_seed: int,
        created_at: datetime,
    ) -> None:
        with self.transaction() as con:
            con.execute(
                """
                INSERT OR REPLACE INTO snapshots(
                    snapshot_id,game_pk,created_at,lineup_json,starter_json,weather_json,
                    source_timestamps_json,feature_vector_json,model_package_hash,deterministic_seed
                ) VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    snapshot_id,
                    game_pk,
                    created_at.isoformat(),
                    json.dumps(lineup, default=str),
                    json.dumps(starter, default=str),
                    json.dumps(weather, default=str) if weather is not None else None,
                    json.dumps(source_timestamps, default=str),
                    json.dumps(feature_vector, default=str),
                    model_package_hash,
                    deterministic_seed,
                ),
            )


    def invalidate_stale_predictions(self, game_pk: int, valid_matchups: dict[int, int]) -> list[dict[str, Any]]:
        """Invalidate an old latest snapshot after MLB confirms a scratch or SP change.

        This is deliberately called only with a fully confirmed current lineup/starter map.
        A temporary provider outage therefore cannot erase the last valid pregame snapshot.
        """
        changes: list[dict[str, Any]]=[]
        with self.transaction() as con:
            rows=con.execute(
                "SELECT prediction_id,player_id,player_name,pitcher_id FROM predictions WHERE game_pk=? AND is_latest_pregame=1 AND pregame_valid=1",
                (game_pk,),
            ).fetchall()
            for row in rows:
                player_id=int(row['player_id']);expected=valid_matchups.get(player_id)
                reason=None
                if expected is None:
                    reason='POST_LOCK_LINEUP_INVALIDATION'
                elif int(row['pitcher_id'])!=int(expected):
                    reason='STARTER_CHANGED'
                if reason:
                    con.execute(
                        "UPDATE predictions SET is_latest_pregame=0,pregame_valid=0,invalidation_reason=? WHERE prediction_id=?",
                        (reason,row['prediction_id']),
                    )
                    changes.append({'prediction_id':row['prediction_id'],'player_id':player_id,'player_name':row['player_name'],'reason':reason})
                    con.execute(
                        "INSERT INTO audit_events(occurred_at,prediction_id,game_pk,module,severity,event_code,payload_json) VALUES(?,?,?,?,?,?,?)",
                        (utcnow_iso(),row['prediction_id'],game_pk,'integrity','WARNING',reason,json.dumps({'player_id':player_id,'expected_pitcher_id':expected},default=str)),
                    )
        return changes

    def save_prediction(self, p: Prediction, tracked: bool = True) -> None:
        warnings = [asdict(w) for w in p.warnings]
        series_key = f"{p.game_pk}:{p.player.player_id}:{p.model_version}"
        with self.transaction() as con:
            con.execute("UPDATE predictions SET is_latest_pregame=0, superseded_by=? WHERE series_key=? AND is_latest_pregame=1", (p.prediction_id, series_key))
            con.execute(
                """
                INSERT OR IGNORE INTO predictions(
                    prediction_id,series_key,snapshot_id,game_pk,player_id,player_name,pitcher_id,pitcher_name,
                    team_name,opponent_name,game_time,raw_probability,final_probability,matchup_score,
                    reliability,confidence_score,confidence_label,p10,p50,p90,classification,user_action,
                    critic,integrity,reasons_json,main_risk,warnings_json,model_version,feature_version,
                    calibration_version,quality_gate_version,model_health,tracked,created_at,pregame_locked
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    p.prediction_id,
                    series_key,
                    p.snapshot_id,
                    p.game_pk,
                    p.player.player_id,
                    p.player.full_name,
                    p.opposing_pitcher.player_id,
                    p.opposing_pitcher.full_name,
                    p.team_name,
                    p.opponent_name,
                    p.game_time.isoformat() if p.game_time else None,
                    p.raw_hr_probability,
                    p.final_hr_probability,
                    p.matchup_score,
                    p.reliability,
                    p.confidence_score,
                    p.confidence_label.value,
                    p.distribution.p10,
                    p.distribution.p50,
                    p.distribution.p90,
                    p.classification.value,
                    p.user_action.value,
                    p.critic.value,
                    p.integrity.value,
                    json.dumps(p.reasons, ensure_ascii=False),
                    p.main_risk,
                    json.dumps(warnings, ensure_ascii=False),
                    p.model_version,
                    p.feature_version,
                    p.calibration_version,
                    p.quality_gate_version,
                    p.model_health.value,
                    1 if tracked else 0,
                    p.created_at.isoformat(),
                    0,
                ),
            )

    def lock_prediction(self, prediction_id: str) -> None:
        with self.transaction() as con:
            con.execute("UPDATE predictions SET pregame_locked=1 WHERE prediction_id=?", (prediction_id,))

    def save_odds(self, quote: OddsQuote, prediction_id: str | None = None, is_at_prediction: bool = False) -> None:
        with self.transaction() as con:
            con.execute(
                """
                INSERT INTO odds_snapshots(
                    prediction_id,game_pk,player_id,bookmaker,market,american_odds,decimal_odds,
                    implied_probability,source_last_update,fetched_at,freshness,source,point,is_odds_at_prediction
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    prediction_id,
                    quote.game_pk,
                    quote.player_id,
                    quote.bookmaker,
                    quote.market,
                    quote.american_odds,
                    quote.decimal_odds,
                    quote.implied_probability,
                    quote.last_update.isoformat() if quote.last_update else None,
                    quote.fetched_at.isoformat(),
                    quote.freshness.value,
                    quote.source,
                    quote.point,
                    int(is_at_prediction),
                ),
            )

    def save_model_ledger(
        self,
        *,
        prediction_id: str,
        reference_stake: float,
        odds_at_prediction: int | None,
        decimal_odds: float | None,
        implied_probability: float | None,
        edge_pp: float | None,
        user_bet: bool = False,
    ) -> None:
        with self.transaction() as con:
            con.execute(
                """
                INSERT OR REPLACE INTO model_ledger(
                    prediction_id,reference_stake,odds_at_prediction,decimal_odds_at_prediction,
                    implied_probability_at_prediction,edge_pp_at_prediction,user_bet,recorded_at
                ) VALUES(?,?,?,?,?,?,?,?)
                """,
                (
                    prediction_id,
                    reference_stake,
                    odds_at_prediction,
                    decimal_odds,
                    implied_probability,
                    edge_pp,
                    int(user_bet),
                    utcnow_iso(),
                ),
            )

    def pending_predictions(self) -> list[sqlite3.Row]:
        with self.connection() as con:
            return list(
                con.execute(
                    """
                    SELECT p.* FROM predictions p
                    LEFT JOIN settlements s ON s.prediction_id=p.prediction_id AND s.active=1
                    WHERE p.tracked=1 AND p.pregame_locked=1 AND p.is_latest_pregame=1 AND p.pregame_valid=1
                      AND (s.settlement_id IS NULL OR s.status NOT IN ('CONFIRMED_SETTLEMENT','VOID','CANCELLED'))
                    ORDER BY p.game_time
                    """
                )
            )

    def save_settlement(self, result: ResultRecord) -> None:
        with self.transaction() as con:
            con.execute("UPDATE settlements SET active=0 WHERE prediction_id=?", (result.prediction_id,))
            con.execute(
                """
                INSERT INTO settlements(
                    prediction_id,result_version,status,actual_hr_count,actual_hr_binary,actual_pa,
                    actual_pa_vs_starter,actual_pa_vs_bullpen,appearance_status,verified_pbp,
                    verified_box,result_source,fetched_at,change_reason,active
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)
                """,
                (
                    result.prediction_id,
                    result.result_version,
                    result.status.value,
                    result.actual_hr_count,
                    result.actual_hr_binary,
                    result.actual_pa,
                    result.actual_pa_vs_starter,
                    result.actual_pa_vs_bullpen,
                    result.appearance_status.value,
                    int(result.verified_pbp),
                    int(result.verified_box),
                    result.result_source,
                    result.fetched_at.isoformat(),
                    result.change_reason,
                ),
            )


    def save_combination(self, combo: Combination) -> None:
        legs=[asdict(x) for x in combo.legs]
        with self.transaction() as con:
            con.execute(
                """INSERT OR IGNORE INTO combinations(
                       combination_id,kind,created_at,legs_json,model_probability_proxy,robustness,
                       actual_parlay_odds,estimated_decimal_odds,warnings_json
                   ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (combo.combination_id,combo.kind,utcnow_iso(),json.dumps(legs,default=str),
                 combo.model_probability_proxy,combo.robustness,combo.actual_parlay_american_odds,
                 combo.estimated_decimal_odds,json.dumps(combo.warnings,ensure_ascii=False)),
            )

    def pending_combinations(self) -> list[sqlite3.Row]:
        with self.connection() as con:
            return list(con.execute(
                """SELECT c.* FROM combinations c
                   LEFT JOIN combination_settlements s ON s.combination_id=c.combination_id AND s.active=1
                   WHERE s.combination_settlement_id IS NULL OR s.status NOT IN ('CONFIRMED_SETTLEMENT','VOID','CANCELLED')
                   ORDER BY c.created_at"""
            ))

    def active_combination_settlement(self, combination_id: str) -> sqlite3.Row | None:
        with self.connection() as con:
            return con.execute(
                "SELECT * FROM combination_settlements WHERE combination_id=? AND active=1 ORDER BY result_version DESC LIMIT 1",
                (combination_id,),
            ).fetchone()

    def save_combination_settlement(self, combination_id: str, *, status: str, won: bool | None, void_leg_count: int, profit_loss: float | None) -> None:
        with self.transaction() as con:
            prev=con.execute("SELECT coalesce(max(result_version),0) FROM combination_settlements WHERE combination_id=?",(combination_id,)).fetchone()[0]
            con.execute("UPDATE combination_settlements SET active=0 WHERE combination_id=?",(combination_id,))
            con.execute(
                """INSERT INTO combination_settlements(combination_id,result_version,status,won,void_leg_count,profit_loss,fetched_at,active)
                   VALUES(?,?,?,?,?,?,?,1)""",
                (combination_id,int(prev)+1,status,None if won is None else int(won),int(void_leg_count),profit_loss,utcnow_iso()),
            )

    def leg_settlements(self, prediction_ids: list[str]) -> dict[str, sqlite3.Row]:
        if not prediction_ids:return {}
        marks=','.join('?' for _ in prediction_ids)
        with self.connection() as con:
            rows=con.execute(
                f"SELECT * FROM settlements WHERE active=1 AND prediction_id IN ({marks})",prediction_ids
            ).fetchall()
        return {str(r['prediction_id']):r for r in rows}

    def log_audit(
        self,
        *,
        module: str,
        severity: str,
        event_code: str,
        payload: dict[str, Any],
        run_id: str | None = None,
        snapshot_id: str | None = None,
        prediction_id: str | None = None,
        game_pk: int | None = None,
    ) -> None:
        with self.transaction() as con:
            con.execute(
                """
                INSERT INTO audit_events(
                    occurred_at,run_id,snapshot_id,prediction_id,game_pk,module,severity,event_code,payload_json
                ) VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (
                    utcnow_iso(),
                    run_id,
                    snapshot_id,
                    prediction_id,
                    game_pk,
                    module,
                    severity,
                    event_code,
                    json.dumps(payload, ensure_ascii=False, default=str),
                ),
            )

    def active_settlement(self, prediction_id: str) -> sqlite3.Row | None:
        with self.connection() as con:
            return con.execute(
                "SELECT * FROM settlements WHERE prediction_id=? AND active=1 ORDER BY result_version DESC LIMIT 1",
                (prediction_id,),
            ).fetchone()

    def latest_prediction_rows(self, limit: int = 200) -> list[sqlite3.Row]:
        with self.connection() as con:
            return list(con.execute(
                """
                SELECT p.*, ml.reference_stake, ml.odds_at_prediction, ml.edge_pp_at_prediction,
                       s.status settlement_status, s.actual_hr_binary, s.actual_hr_count,
                       s.actual_pa
                FROM predictions p
                LEFT JOIN model_ledger ml ON ml.prediction_id=p.prediction_id
                LEFT JOIN settlements s ON s.prediction_id=p.prediction_id AND s.active=1
                WHERE p.is_latest_pregame=1 AND p.pregame_valid=1
                ORDER BY p.created_at DESC LIMIT ?
                """,(limit,)))

    def history_summary(self) -> dict[str, Any]:
        with self.connection() as con:
            row=con.execute(
                """
                SELECT count(*) FILTER(WHERE s.status='CONFIRMED_SETTLEMENT' AND s.actual_hr_binary IS NOT NULL) n,
                       sum(CASE WHEN s.status='CONFIRMED_SETTLEMENT' THEN s.actual_hr_binary ELSE 0 END) hits,
                       avg(CASE WHEN s.status='CONFIRMED_SETTLEMENT' THEN p.final_probability END) mean_pred,
                       avg(CASE WHEN s.status='CONFIRMED_SETTLEMENT' THEN (p.final_probability-s.actual_hr_binary)*(p.final_probability-s.actual_hr_binary) END) brier
                FROM predictions p
                JOIN settlements s ON s.prediction_id=p.prediction_id AND s.active=1
                WHERE p.is_latest_pregame=1 AND p.pregame_valid=1
                """
            ).fetchone()
            econ=con.execute("SELECT coalesce(sum(amount),0) pnl FROM paper_bankroll_events WHERE event_type IN ('WIN','LOSS')").fetchone()
            last=con.execute("SELECT balance_after FROM paper_bankroll_events ORDER BY event_id DESC LIMIT 1").fetchone()
            staked=con.execute("""SELECT coalesce(sum(ml.reference_stake),0) FROM model_ledger ml JOIN settlements s ON s.prediction_id=ml.prediction_id AND s.active=1 AND s.status='CONFIRMED_SETTLEMENT' WHERE ml.odds_at_prediction IS NOT NULL""").fetchone()
            balances=[float(r[0]) for r in con.execute("SELECT balance_after FROM paper_bankroll_events ORDER BY event_id").fetchall()]
            counts=con.execute("SELECT classification,count(*) n FROM predictions WHERE is_latest_pregame=1 GROUP BY classification").fetchall()
        n=int(row[0] or 0);hits=int(row[1] or 0);pnl=float(econ[0] or 0);total_staked=float(staked[0] or 0)
        peak=1000.0;max_dd=0.0
        for bal in balances:
            peak=max(peak,bal);max_dd=max(max_dd,peak-bal)
        return {
            "n":n,"hits":hits,"misses":max(0,n-hits),"actual_hr_rate":hits/n if n else None,
            "mean_predicted":float(row[2]) if row[2] is not None else None,
            "brier":float(row[3]) if row[3] is not None else None,
            "pnl":pnl,"total_staked":total_staked,"roi":pnl/total_staked if total_staked else None,
            "bankroll":float(last[0]) if last else 1000.0,"max_drawdown":max_dd,
            "classification_counts":{r[0]:int(r[1]) for r in counts},
        }

    def apply_paper_settlement(self, prediction_id: str, won: bool) -> None:
        with self.transaction() as con:
            exists=con.execute("SELECT 1 FROM paper_bankroll_events WHERE prediction_id=? AND event_type IN ('WIN','LOSS')",(prediction_id,)).fetchone()
            if exists:return
            led=con.execute("SELECT reference_stake,odds_at_prediction FROM model_ledger WHERE prediction_id=?",(prediction_id,)).fetchone()
            if not led or led[1] is None:return
            stake=float(led[0]);odds=int(led[1])
            from mlb_hr.domain.math import payout_for_stake
            _,profit=payout_for_stake(stake,odds)
            amount=profit if won else -stake
            last=con.execute("SELECT balance_after FROM paper_bankroll_events ORDER BY event_id DESC LIMIT 1").fetchone()
            balance=float(last[0]) if last else 1000.0
            new_balance=balance+amount
            con.execute("INSERT INTO paper_bankroll_events(prediction_id,amount,event_type,balance_after,recorded_at,note) VALUES(?,?,?,?,?,?)",
                        (prediction_id,amount,"WIN" if won else "LOSS",new_balance,utcnow_iso(),"Automatic model-ledger settlement"))
