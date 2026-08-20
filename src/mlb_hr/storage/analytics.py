from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import csv
from functools import lru_cache
import math
from pathlib import Path
import tempfile
from typing import Any, Iterable

from mlb_hr.domain.models import PitcherHistory, PlayerHistory


@dataclass(slots=True)
class SimilarPitcherResult:
    score: float = 0.0
    reliability: float = 0.0
    comparable_count: int = 0
    batter_pa: int = 0
    batter_hr_pa: float = 0.0
    batter_xslg: float = 0.0
    pitcher_ids: list[int] | None = None


class AnalyticsUnavailable(RuntimeError):
    pass


class AnalyticsStore:
    """DuckDB-over-Parquet analytical store.

    Completed Statcast day files are immutable. All queries are cut off strictly before
    the supplied date, which makes the same methods usable for live analysis and
    walk-forward historical reconstruction.
    """

    def __init__(self, parquet_dir: Path) -> None:
        self.parquet_dir = Path(parquet_dir)
        self.parquet_dir.mkdir(parents=True, exist_ok=True)
        self._duckdb = None
        self._con = None

    def _db(self):
        if self._con is not None:
            return self._con
        try:
            import duckdb
        except Exception as exc:
            raise AnalyticsUnavailable("DuckDB is not installed") from exc
        self._duckdb = duckdb
        self._con = duckdb.connect(database=":memory:")
        self._con.execute("PRAGMA threads=4")
        return self._con

    def close(self) -> None:
        if self._con is not None:
            self._con.close()
            self._con = None

    @property
    def glob(self) -> str:
        return str(self.parquet_dir / "season=*" / "month=*" / "statcast_*.parquet")

    def has_data(self) -> bool:
        return any(self.parquet_dir.glob("season=*/month=*/statcast_*.parquet"))

    def write_statcast_day(self, rows: list[dict[str, str]], day: date) -> Path:
        if not rows:
            raise ValueError("Cannot write an empty Statcast day")
        out_dir = self.parquet_dir / f"season={day.year}" / f"month={day.month:02d}"
        out_dir.mkdir(parents=True, exist_ok=True)
        final = out_dir / f"statcast_{day.isoformat()}.parquet"
        tmp_parquet = final.with_suffix(".parquet.tmp")
        fields = sorted({k for row in rows for k in row.keys()})
        with tempfile.NamedTemporaryFile("w", suffix=".csv", newline="", encoding="utf-8", delete=False) as f:
            csv_path = Path(f.name)
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        try:
            con = self._db()
            # all_varchar prevents schema drift from a day containing only blanks in a numeric column;
            # downstream queries use TRY_CAST explicitly.
            qcsv = str(csv_path).replace("'", "''")
            qout = str(tmp_parquet).replace("'", "''")
            con.execute(
                f"COPY (SELECT * FROM read_csv_auto('{qcsv}', header=true, all_varchar=true, sample_size=-1)) "
                f"TO '{qout}' (FORMAT PARQUET, COMPRESSION ZSTD)"
            )
            if not tmp_parquet.exists() or tmp_parquet.stat().st_size == 0:
                raise RuntimeError("DuckDB did not produce a valid Parquet file")
            tmp_parquet.replace(final)
            self._query_cached.cache_clear()
            self._pitcher_profiles.cache_clear()
            return final
        finally:
            csv_path.unlink(missing_ok=True)
            tmp_parquet.unlink(missing_ok=True)

    def _source_sql(self) -> str:
        g = self.glob.replace("'", "''")
        return f"read_parquet('{g}', union_by_name=true, hive_partitioning=true)"

    @lru_cache(maxsize=4096)
    def _query_cached(self, sql: str, params: tuple[Any, ...]) -> tuple[tuple[Any, ...], ...]:
        if not self.has_data():
            return tuple()
        con = self._db()
        rows = con.execute(sql, params).fetchall()
        return tuple(tuple(r) for r in rows)

    def query(self, sql: str, params: Iterable[Any] = ()) -> list[tuple[Any, ...]]:
        return [tuple(r) for r in self._query_cached(sql, tuple(params))]

    def batter_history(self, player_id: int, cutoff: date, pitcher_hand: str | None = None) -> PlayerHistory:
        if not self.has_data():
            return PlayerHistory(player_id=player_id)
        src = self._source_sql()
        split_clause = ""
        params: list[Any] = [str(player_id), cutoff.isoformat()]
        if pitcher_hand:
            split_clause = "AND p_throws = ?"
            params.append(pitcher_hand)
        sql = f"""
        WITH x AS (
            SELECT *, TRY_CAST(launch_speed AS DOUBLE) ev,
                      TRY_CAST(launch_angle AS DOUBLE) la,
                      TRY_CAST(estimated_slg_using_speedangle AS DOUBLE) exslg,
                      TRY_CAST(estimated_woba_using_speedangle AS DOUBLE) exwoba,
                      TRY_CAST(launch_speed_angle AS INTEGER) lsa,
                      TRY_CAST(game_date AS DATE) gd
            FROM {src}
            WHERE batter = ? AND TRY_CAST(game_date AS DATE) < ?
        ), agg AS (
            SELECT
              count(*) FILTER (WHERE events IS NOT NULL AND events <> '') AS pa,
              count(*) FILTER (WHERE ev IS NOT NULL) AS bbe,
              count(*) FILTER (WHERE events='home_run') AS hr,
              avg(CASE WHEN lsa=6 THEN 1.0 WHEN ev IS NOT NULL THEN 0.0 END) FILTER (WHERE ev IS NOT NULL) AS barrel,
              avg(CASE WHEN ev>=95 THEN 1.0 WHEN ev IS NOT NULL THEN 0.0 END) FILTER (WHERE ev IS NOT NULL) AS hardhit,
              avg(CASE WHEN la BETWEEN 8 AND 32 THEN 1.0 WHEN la IS NOT NULL THEN 0.0 END) FILTER (WHERE la IS NOT NULL) AS sweet,
              avg(ev) AS avg_ev, max(ev) AS max_ev, avg(la) AS avg_la,
              avg(CASE WHEN bb_type='fly_ball' THEN 1.0 WHEN bb_type IS NOT NULL AND bb_type<>'' THEN 0.0 END) FILTER (WHERE bb_type IS NOT NULL AND bb_type<>'') AS fb,
              avg(exslg) FILTER (WHERE exslg IS NOT NULL) AS xslg,
              avg(exwoba) FILTER (WHERE exwoba IS NOT NULL) AS xwoba,
              avg(CASE WHEN events IN ('strikeout','strikeout_double_play') THEN 1.0 WHEN events IS NOT NULL AND events<>'' THEN 0.0 END) FILTER (WHERE events IS NOT NULL AND events<>'') AS kr,
              avg(CASE WHEN events IN ('walk','intent_walk') THEN 1.0 WHEN events IS NOT NULL AND events<>'' THEN 0.0 END) FILTER (WHERE events IS NOT NULL AND events<>'') AS bbr,
              count(*) FILTER (WHERE events='home_run' AND gd >= TRY_CAST(? AS DATE)-INTERVAL 30 DAY) * 1.0 /
                NULLIF(count(*) FILTER (WHERE events IS NOT NULL AND events<>'' AND gd >= TRY_CAST(? AS DATE)-INTERVAL 30 DAY),0) AS hr30,
              count(*) FILTER (WHERE events='home_run' AND gd >= TRY_CAST(? AS DATE)-INTERVAL 60 DAY) * 1.0 /
                NULLIF(count(*) FILTER (WHERE events IS NOT NULL AND events<>'' AND gd >= TRY_CAST(? AS DATE)-INTERVAL 60 DAY),0) AS hr60
            FROM x
        ), spl AS (
            SELECT count(*) FILTER(WHERE events='home_run') * 1.0 /
                   NULLIF(count(*) FILTER(WHERE events IS NOT NULL AND events<>''),0) split_hr
            FROM x WHERE 1=1 {split_clause}
        )
        SELECT agg.*, spl.split_hr FROM agg, spl
        """
        # cutoff four times for recent windows; split hand after those.
        full_params: list[Any] = [str(player_id), cutoff.isoformat(), cutoff.isoformat(), cutoff.isoformat(), cutoff.isoformat(), cutoff.isoformat()]
        if pitcher_hand:
            full_params.append(pitcher_hand)
        rows = self.query(sql, full_params)
        if not rows:
            return PlayerHistory(player_id=player_id)
        r = rows[0]
        pa, bbe, hr = int(r[0] or 0), int(r[1] or 0), int(r[2] or 0)
        return PlayerHistory(
            player_id=player_id,
            pa=pa,
            bbe=bbe,
            hr=hr,
            hr_pa=_safe_div(hr, pa),
            barrel_rate=_f(r[3]), hardhit_rate=_f(r[4]), sweetspot_rate=_f(r[5]),
            avg_ev=_f(r[6]), max_ev=_f(r[7]), avg_launch_angle=_f(r[8]), flyball_rate=_f(r[9]),
            xslg=_f(r[10]), xwoba=_f(r[11]), k_rate=_f(r[12]), bb_rate=_f(r[13]),
            recent_30_hr_pa=_f(r[14]), recent_60_hr_pa=_f(r[15]), split_hr_pa=_f(r[16]),
            reliability=_sample_reliability(pa, 250.0),
            history_class=_history_class(pa),
            evidence_diversity=min(1.0, (min(pa, 500) / 500.0 + min(bbe, 250) / 250.0) / 2.0),
        )

    def pitcher_history(self, player_id: int, cutoff: date, batter_side: str | None = None) -> PitcherHistory:
        if not self.has_data():
            return PitcherHistory(player_id=player_id)
        src = self._source_sql()
        split_clause = ""
        params: list[Any] = [str(player_id), cutoff.isoformat(), cutoff.isoformat(), cutoff.isoformat(), cutoff.isoformat(), cutoff.isoformat()]
        if batter_side:
            split_clause = "AND stand = ?"
            params.append(batter_side)
        sql = f"""
        WITH x AS (
            SELECT *, TRY_CAST(launch_speed AS DOUBLE) ev,
                      TRY_CAST(launch_angle AS DOUBLE) la,
                      TRY_CAST(estimated_slg_using_speedangle AS DOUBLE) exslg,
                      TRY_CAST(estimated_woba_using_speedangle AS DOUBLE) exwoba,
                      TRY_CAST(launch_speed_angle AS INTEGER) lsa,
                      TRY_CAST(release_speed AS DOUBLE) velo,
                      TRY_CAST(game_date AS DATE) gd
            FROM {src}
            WHERE pitcher = ? AND TRY_CAST(game_date AS DATE) < ?
        ), agg AS (
            SELECT
              count(*) FILTER (WHERE events IS NOT NULL AND events <> '') AS bf,
              count(*) FILTER (WHERE ev IS NOT NULL) AS bbe,
              count(*) FILTER (WHERE events='home_run') AS hr,
              avg(CASE WHEN lsa=6 THEN 1.0 WHEN ev IS NOT NULL THEN 0.0 END) FILTER (WHERE ev IS NOT NULL) AS barrel,
              avg(CASE WHEN ev>=95 THEN 1.0 WHEN ev IS NOT NULL THEN 0.0 END) FILTER (WHERE ev IS NOT NULL) AS hardhit,
              avg(ev) AS avg_ev,
              avg(exslg) FILTER (WHERE exslg IS NOT NULL) AS xslg,
              avg(exwoba) FILTER (WHERE exwoba IS NOT NULL) AS xwoba,
              avg(CASE WHEN bb_type='fly_ball' THEN 1.0 WHEN bb_type IS NOT NULL AND bb_type<>'' THEN 0.0 END) FILTER (WHERE bb_type IS NOT NULL AND bb_type<>'') AS fb,
              count(*) FILTER (WHERE events='home_run' AND gd >= TRY_CAST(? AS DATE)-INTERVAL 30 DAY) * 1.0 /
                NULLIF(count(*) FILTER (WHERE events IS NOT NULL AND events<>'' AND gd >= TRY_CAST(? AS DATE)-INTERVAL 30 DAY),0) AS hr30,
              count(*) FILTER (WHERE events='home_run' AND gd >= TRY_CAST(? AS DATE)-INTERVAL 60 DAY) * 1.0 /
                NULLIF(count(*) FILTER (WHERE events IS NOT NULL AND events<>'' AND gd >= TRY_CAST(? AS DATE)-INTERVAL 60 DAY),0) AS hr60,
              avg(velo) FILTER(WHERE velo IS NOT NULL) AS avg_velo
            FROM x
        ), spl AS (
            SELECT count(*) FILTER(WHERE events='home_run') * 1.0 /
                   NULLIF(count(*) FILTER(WHERE events IS NOT NULL AND events<>''),0) split_hr
            FROM x WHERE 1=1 {split_clause}
        )
        SELECT agg.*, spl.split_hr FROM agg, spl
        """
        rows = self.query(sql, params)
        if not rows:
            return PitcherHistory(player_id=player_id)
        r = rows[0]
        bf, bbe, hr = int(r[0] or 0), int(r[1] or 0), int(r[2] or 0)
        return PitcherHistory(
            player_id=player_id,
            bf=bf, bbe=bbe, hr=hr, hr_bf=_safe_div(hr, bf), barrel_allowed=_f(r[3]),
            hardhit_allowed=_f(r[4]), avg_ev_allowed=_f(r[5]), xslg_allowed=_f(r[6]),
            xwoba_allowed=_f(r[7]), fb_rate_allowed=_f(r[8]), recent_30_hr_bf=_f(r[9]),
            recent_60_hr_bf=_f(r[10]), avg_velocity=_f(r[11]), split_hr_bf=_f(r[12]),
            reliability=_sample_reliability(bf, 300.0),
        )

    def pitch_type_match(self, batter_id: int, pitcher_id: int, cutoff: date) -> tuple[float, float]:
        """Weighted batter contact quality versus the target pitcher's actual pitch mix.

        Returns delta versus batter overall xSLG-on-contact, plus a reliability score.
        """
        if not self.has_data():
            return 0.0, 0.0
        src = self._source_sql()
        sql = f"""
        WITH pmix AS (
          SELECT pitch_type, count(*) n
          FROM {src}
          WHERE pitcher=? AND TRY_CAST(game_date AS DATE) < ? AND pitch_type IS NOT NULL AND pitch_type<>''
            AND TRY_CAST(game_date AS DATE) >= TRY_CAST(? AS DATE)-INTERVAL 730 DAY
          GROUP BY pitch_type
        ), b AS (
          SELECT pitch_type,
                 avg(TRY_CAST(estimated_slg_using_speedangle AS DOUBLE)) FILTER(WHERE estimated_slg_using_speedangle IS NOT NULL AND estimated_slg_using_speedangle<>'') x,
                 count(*) FILTER(WHERE launch_speed IS NOT NULL AND launch_speed<>'') n
          FROM {src}
          WHERE batter=? AND TRY_CAST(game_date AS DATE) < ?
          GROUP BY pitch_type
        ), overall AS (
          SELECT avg(TRY_CAST(estimated_slg_using_speedangle AS DOUBLE)) FILTER(WHERE estimated_slg_using_speedangle IS NOT NULL AND estimated_slg_using_speedangle<>'') x
          FROM {src} WHERE batter=? AND TRY_CAST(game_date AS DATE) < ?
        )
        SELECT sum(pmix.n * coalesce(b.x, overall.x))/NULLIF(sum(pmix.n),0)-overall.x,
               sum(CASE WHEN b.n IS NOT NULL THEN least(b.n,100) ELSE 0 END) * 1.0 / NULLIF(count(*)*100,0)
        FROM pmix LEFT JOIN b USING(pitch_type), overall
        """
        rows = self.query(sql, (str(pitcher_id), cutoff.isoformat(), cutoff.isoformat(), str(batter_id), cutoff.isoformat(), str(batter_id), cutoff.isoformat()))
        if not rows:
            return 0.0, 0.0
        return _f(rows[0][0]), max(0.0, min(1.0, _f(rows[0][1])))

    def velocity_match(self, batter_id: int, pitcher_id: int, cutoff: date) -> tuple[float, float]:
        if not self.has_data():
            return 0.0, 0.0
        src = self._source_sql()
        band = "CASE WHEN TRY_CAST(release_speed AS DOUBLE)<90 THEN 1 WHEN TRY_CAST(release_speed AS DOUBLE)<95 THEN 2 WHEN TRY_CAST(release_speed AS DOUBLE)<98 THEN 3 ELSE 4 END"
        sql = f"""
        WITH pmix AS (
          SELECT {band} band, count(*) n FROM {src}
          WHERE pitcher=? AND TRY_CAST(game_date AS DATE)< ? AND release_speed IS NOT NULL AND release_speed<>''
            AND TRY_CAST(game_date AS DATE)>=TRY_CAST(? AS DATE)-INTERVAL 730 DAY
          GROUP BY band
        ), b AS (
          SELECT {band} band,
                 avg(TRY_CAST(estimated_slg_using_speedangle AS DOUBLE)) FILTER(WHERE estimated_slg_using_speedangle IS NOT NULL AND estimated_slg_using_speedangle<>'') x,
                 count(*) FILTER(WHERE launch_speed IS NOT NULL AND launch_speed<>'') n
          FROM {src} WHERE batter=? AND TRY_CAST(game_date AS DATE)< ? AND release_speed IS NOT NULL AND release_speed<>'' GROUP BY band
        ), overall AS (
          SELECT avg(TRY_CAST(estimated_slg_using_speedangle AS DOUBLE)) FILTER(WHERE estimated_slg_using_speedangle IS NOT NULL AND estimated_slg_using_speedangle<>'') x
          FROM {src} WHERE batter=? AND TRY_CAST(game_date AS DATE)< ?
        )
        SELECT sum(pmix.n*coalesce(b.x,overall.x))/NULLIF(sum(pmix.n),0)-overall.x,
               sum(CASE WHEN b.n IS NOT NULL THEN least(b.n,100) ELSE 0 END)*1.0/NULLIF(count(*)*100,0)
        FROM pmix LEFT JOIN b USING(band), overall
        """
        rows = self.query(sql, (str(pitcher_id), cutoff.isoformat(), cutoff.isoformat(), str(batter_id), cutoff.isoformat(), str(batter_id), cutoff.isoformat()))
        if not rows:
            return 0.0, 0.0
        return _f(rows[0][0]), max(0.0, min(1.0, _f(rows[0][1])))

    def zone_match(self, batter_id: int, pitcher_id: int, cutoff: date) -> tuple[float, float]:
        if not self.has_data():
            return 0.0, 0.0
        src = self._source_sql()
        sql = f"""
        WITH pz AS (
          SELECT TRY_CAST(zone AS INTEGER) zone_i, count(*) n FROM {src}
          WHERE pitcher=? AND TRY_CAST(game_date AS DATE)< ? AND TRY_CAST(zone AS INTEGER) BETWEEN 1 AND 9
            AND TRY_CAST(game_date AS DATE)>=TRY_CAST(? AS DATE)-INTERVAL 730 DAY
          GROUP BY zone_i
        ), b AS (
          SELECT TRY_CAST(zone AS INTEGER) zone_i,
                 avg(TRY_CAST(estimated_slg_using_speedangle AS DOUBLE)) FILTER(WHERE estimated_slg_using_speedangle IS NOT NULL AND estimated_slg_using_speedangle<>'') x,
                 count(*) FILTER(WHERE launch_speed IS NOT NULL AND launch_speed<>'') n
          FROM {src} WHERE batter=? AND TRY_CAST(game_date AS DATE)< ? AND TRY_CAST(zone AS INTEGER) BETWEEN 1 AND 9 GROUP BY zone_i
        ), overall AS (
          SELECT avg(TRY_CAST(estimated_slg_using_speedangle AS DOUBLE)) FILTER(WHERE estimated_slg_using_speedangle IS NOT NULL AND estimated_slg_using_speedangle<>'') x
          FROM {src} WHERE batter=? AND TRY_CAST(game_date AS DATE)< ?
        )
        SELECT sum(pz.n*coalesce(b.x,overall.x))/NULLIF(sum(pz.n),0)-overall.x,
               sum(CASE WHEN b.n IS NOT NULL THEN least(b.n,80) ELSE 0 END)*1.0/NULLIF(count(*)*80,0)
        FROM pz LEFT JOIN b USING(zone_i), overall
        """
        rows = self.query(sql, (str(pitcher_id), cutoff.isoformat(), cutoff.isoformat(), str(batter_id), cutoff.isoformat(), str(batter_id), cutoff.isoformat()))
        if not rows:
            return 0.0, 0.0
        return _f(rows[0][0]), max(0.0, min(1.0, _f(rows[0][1])))

    def bvp(self, batter_id: int, pitcher_id: int, cutoff: date) -> tuple[int, int, float]:
        if not self.has_data():
            return 0, 0, 0.0
        src = self._source_sql()
        sql = f"""SELECT count(*) FILTER(WHERE events IS NOT NULL AND events<>''),
                           count(*) FILTER(WHERE events='home_run')
                    FROM {src} WHERE batter=? AND pitcher=? AND TRY_CAST(game_date AS DATE)< ?"""
        rows = self.query(sql, (str(batter_id), str(pitcher_id), cutoff.isoformat()))
        if not rows:
            return 0, 0, 0.0
        pa, hr = int(rows[0][0] or 0), int(rows[0][1] or 0)
        return pa, hr, _safe_div(hr, pa)

    def starter_avg_bf(self, pitcher_id: int, cutoff: date, lookback_days: int = 730) -> tuple[float, int]:
        if not self.has_data():
            return 18.0, 0
        src = self._source_sql()
        sql = f"""
        WITH per_game_pitcher AS (
          SELECT TRY_CAST(game_pk AS BIGINT) game_pk,
                 CASE WHEN lower(inning_topbot)='top' THEN home_team ELSE away_team END pitching_team,
                 pitcher,
                 min(TRY_CAST(at_bat_number AS INTEGER)) first_ab,
                 count(*) FILTER(WHERE events IS NOT NULL AND events<>'') bf
          FROM {src}
          WHERE TRY_CAST(game_date AS DATE)< ? AND TRY_CAST(game_date AS DATE)>=TRY_CAST(? AS DATE)-INTERVAL {int(lookback_days)} DAY
          GROUP BY game_pk,pitching_team,pitcher
        ), starters AS (
          SELECT game_pk, pitching_team, pitcher, bf,
                 row_number() OVER(PARTITION BY game_pk,pitching_team ORDER BY first_ab,pitcher) rn
          FROM per_game_pitcher
        )
        SELECT avg(bf), count(*) FROM starters WHERE rn=1 AND pitcher=?
        """
        rows = self.query(sql, (cutoff.isoformat(), cutoff.isoformat(), str(pitcher_id)))
        if not rows or rows[0][0] is None:
            return 18.0, 0
        return float(rows[0][0]), int(rows[0][1] or 0)

    def league_hr_per_pa(self, cutoff: date, lookback_days: int = 730) -> float:
        if not self.has_data():
            return 0.03
        src = self._source_sql()
        sql = f"""SELECT count(*) FILTER(WHERE events='home_run')*1.0/
                           NULLIF(count(*) FILTER(WHERE events IS NOT NULL AND events<>''),0)
                    FROM {src}
                    WHERE TRY_CAST(game_date AS DATE)< ? AND TRY_CAST(game_date AS DATE)>=TRY_CAST(? AS DATE)-INTERVAL {int(lookback_days)} DAY"""
        rows = self.query(sql, (cutoff.isoformat(), cutoff.isoformat()))
        return _f(rows[0][0]) if rows and rows[0][0] is not None else 0.03

    @lru_cache(maxsize=256)
    def _pitcher_profiles(self, cutoff_iso: str, hand: str) -> tuple[tuple[Any, ...], ...]:
        if not self.has_data():
            return tuple()
        src = self._source_sql()
        sql = f"""
        SELECT TRY_CAST(pitcher AS BIGINT) pid,
               avg(TRY_CAST(release_speed AS DOUBLE)) velo,
               avg(TRY_CAST(pfx_x AS DOUBLE)) pfx_x,
               avg(TRY_CAST(pfx_z AS DOUBLE)) pfx_z,
               avg(TRY_CAST(release_pos_x AS DOUBLE)) rpx,
               avg(TRY_CAST(release_pos_z AS DOUBLE)) rpz,
               avg(TRY_CAST(release_extension AS DOUBLE)) ext,
               avg(CASE WHEN pitch_type IN ('FF','FA') THEN 1.0 ELSE 0.0 END) ff,
               avg(CASE WHEN pitch_type='SI' THEN 1.0 ELSE 0.0 END) si,
               avg(CASE WHEN pitch_type='SL' THEN 1.0 ELSE 0.0 END) sl,
               avg(CASE WHEN pitch_type='CH' THEN 1.0 ELSE 0.0 END) ch,
               avg(CASE WHEN pitch_type='CU' THEN 1.0 ELSE 0.0 END) cu,
               avg(CASE WHEN pitch_type='FC' THEN 1.0 ELSE 0.0 END) fc,
               count(*) n
        FROM {src}
        WHERE p_throws=? AND TRY_CAST(game_date AS DATE)< ?
          AND TRY_CAST(game_date AS DATE)>=TRY_CAST(? AS DATE)-INTERVAL 730 DAY
        GROUP BY pitcher HAVING count(*)>=200
        """
        return tuple(self.query(sql, (hand, cutoff_iso, cutoff_iso)))

    def similar_pitcher_signal(self, batter_id: int, pitcher_id: int, pitcher_hand: str, cutoff: date) -> SimilarPitcherResult:
        profiles = self._pitcher_profiles(cutoff.isoformat(), pitcher_hand)
        if not profiles:
            return SimilarPitcherResult()
        feature_rows: list[tuple[int, list[float], int]] = []
        for row in profiles:
            vals = [_f(v) for v in row[1:12]]
            feature_rows.append((int(row[0]), vals, int(row[12] or 0)))
        target = next((x for x in feature_rows if x[0] == pitcher_id), None)
        if target is None:
            return SimilarPitcherResult()
        cols = list(zip(*(x[1] for x in feature_rows)))
        means = [sum(c)/len(c) for c in cols]
        sds = [math.sqrt(sum((v-m)**2 for v in c)/max(len(c)-1,1)) or 1.0 for c,m in zip(cols,means)]
        # Pitch mix gets more total weight, matching the frozen design.
        weights = [0.20,0.06,0.06,0.05,0.05,0.08,0.10,0.08,0.08,0.08,0.08]
        def dist(vals: list[float]) -> float:
            return math.sqrt(sum(w*((v-t)/sd)**2 for w,v,t,sd in zip(weights, vals, target[1], sds)))
        ranked = sorted((dist(vals), pid) for pid, vals, _ in feature_rows if pid != pitcher_id)
        # Adaptive, no forced padding. Keep at most 15 and only reasonably close profiles.
        chosen = [(d,pid) for d,pid in ranked[:15] if d <= 1.75]
        if len(chosen) < 3:
            return SimilarPitcherResult(score=0.0, reliability=0.1, comparable_count=len(chosen), pitcher_ids=[p for _,p in chosen])
        ids = [pid for _,pid in chosen]
        placeholders = ",".join("?" for _ in ids)
        src = self._source_sql()
        sql = f"""
        SELECT count(*) FILTER(WHERE events IS NOT NULL AND events<>''),
               count(*) FILTER(WHERE events='home_run'),
               avg(TRY_CAST(estimated_slg_using_speedangle AS DOUBLE)) FILTER(WHERE estimated_slg_using_speedangle IS NOT NULL AND estimated_slg_using_speedangle<>'')
        FROM {src}
        WHERE batter=? AND pitcher IN ({placeholders}) AND TRY_CAST(game_date AS DATE)< ?
        """
        params = [str(batter_id), *[str(x) for x in ids], cutoff.isoformat()]
        rows = self.query(sql, params)
        if not rows:
            return SimilarPitcherResult(comparable_count=len(ids), pitcher_ids=ids)
        pa, hr, xslg = int(rows[0][0] or 0), int(rows[0][1] or 0), _f(rows[0][2])
        rel = _sample_reliability(pa, 60.0) * min(1.0, len(ids)/8.0)
        avg_dist = sum(d for d,_ in chosen)/len(chosen)
        score = max(0.0, min(1.0, 1.0-avg_dist/2.0))
        return SimilarPitcherResult(score=score, reliability=rel, comparable_count=len(ids), batter_pa=pa, batter_hr_pa=_safe_div(hr,pa), batter_xslg=xslg, pitcher_ids=ids)


    def batter_profile_change(self, batter_id: int, cutoff: date) -> tuple[float, float]:
        """Multi-metric process-change proxy using EV, hard-hit, barrel and launch geometry.

        Returns a signed score in roughly [-1,1] and a reliability. Results-only HR rate is
        intentionally excluded so a hot streak alone cannot establish structural change.
        """
        if not self.has_data():
            return 0.0, 0.0
        src=self._source_sql()
        sql=f"""
        WITH x AS (
          SELECT TRY_CAST(game_date AS DATE) gd,
                 TRY_CAST(launch_speed AS DOUBLE) ev,
                 TRY_CAST(launch_angle AS DOUBLE) la,
                 TRY_CAST(launch_speed_angle AS INTEGER) lsa
          FROM {src}
          WHERE batter=? AND TRY_CAST(game_date AS DATE)< ?
            AND TRY_CAST(game_date AS DATE)>=TRY_CAST(? AS DATE)-INTERVAL 425 DAY
            AND launch_speed IS NOT NULL AND launch_speed<>''
        ), r AS (
          SELECT avg(ev) ev,
                 avg(CASE WHEN ev>=95 THEN 1.0 ELSE 0.0 END) hh,
                 avg(CASE WHEN lsa=6 THEN 1.0 ELSE 0.0 END) barrel,
                 avg(la) la,
                 count(*) n
          FROM x WHERE gd>=TRY_CAST(? AS DATE)-INTERVAL 60 DAY
        ), b AS (
          SELECT avg(ev) ev,
                 avg(CASE WHEN ev>=95 THEN 1.0 ELSE 0.0 END) hh,
                 avg(CASE WHEN lsa=6 THEN 1.0 ELSE 0.0 END) barrel,
                 avg(la) la,
                 count(*) n
          FROM x WHERE gd<TRY_CAST(? AS DATE)-INTERVAL 60 DAY
        )
        SELECT r.ev-b.ev, r.hh-b.hh, r.barrel-b.barrel, r.la-b.la, r.n, b.n FROM r,b
        """
        rows=self.query(sql,(str(batter_id),cutoff.isoformat(),cutoff.isoformat(),cutoff.isoformat(),cutoff.isoformat()))
        if not rows: return 0.0,0.0
        evd,hhd,bd,lad,nr,nb=rows[0]
        nr=int(nr or 0); nb=int(nb or 0)
        if nr<10 or nb<30: return 0.0,_sample_reliability(nr,50)*_sample_reliability(nb,100)
        # Scale each process metric to a conservative material-change unit, require evidence diversity.
        comps=[_f(evd)/3.0, _f(hhd)/0.08, _f(bd)/0.05, _f(lad)/6.0]
        clipped=[max(-1.5,min(1.5,x)) for x in comps]
        signs=[1 if x>0.25 else -1 if x<-0.25 else 0 for x in clipped]
        positive=sum(1 for x in signs if x>0); negative=sum(1 for x in signs if x<0)
        if max(positive,negative)<2:
            score=0.0
        else:
            score=sum(clipped)/len(clipped)
        rel=_sample_reliability(nr,60)*_sample_reliability(nb,180)*min(1.0,max(positive,negative)/3.0)
        return max(-1.0,min(1.0,score)), rel

    def pitcher_profile_change(self, pitcher_id: int, cutoff: date) -> tuple[float, float]:
        if not self.has_data():
            return 0.0,0.0
        src=self._source_sql()
        sql=f"""
        WITH x AS (
          SELECT TRY_CAST(game_date AS DATE) gd,
                 TRY_CAST(release_speed AS DOUBLE) velo,
                 TRY_CAST(launch_speed AS DOUBLE) ev,
                 TRY_CAST(launch_speed_angle AS INTEGER) lsa
          FROM {src}
          WHERE pitcher=? AND TRY_CAST(game_date AS DATE)< ?
            AND TRY_CAST(game_date AS DATE)>=TRY_CAST(? AS DATE)-INTERVAL 425 DAY
        ), r AS (
          SELECT avg(velo) velo, avg(ev) ev,
                 avg(CASE WHEN ev>=95 THEN 1.0 WHEN ev IS NOT NULL THEN 0.0 END) hh,
                 avg(CASE WHEN lsa=6 THEN 1.0 WHEN ev IS NOT NULL THEN 0.0 END) barrel,
                 count(*) FILTER(WHERE velo IS NOT NULL) n
          FROM x WHERE gd>=TRY_CAST(? AS DATE)-INTERVAL 60 DAY
        ), b AS (
          SELECT avg(velo) velo, avg(ev) ev,
                 avg(CASE WHEN ev>=95 THEN 1.0 WHEN ev IS NOT NULL THEN 0.0 END) hh,
                 avg(CASE WHEN lsa=6 THEN 1.0 WHEN ev IS NOT NULL THEN 0.0 END) barrel,
                 count(*) FILTER(WHERE velo IS NOT NULL) n
          FROM x WHERE gd<TRY_CAST(? AS DATE)-INTERVAL 60 DAY
        )
        SELECT r.velo-b.velo, r.ev-b.ev, r.hh-b.hh, r.barrel-b.barrel, r.n,b.n FROM r,b
        """
        rows=self.query(sql,(str(pitcher_id),cutoff.isoformat(),cutoff.isoformat(),cutoff.isoformat(),cutoff.isoformat()))
        if not rows:return 0.0,0.0
        vd,evd,hhd,bd,nr,nb=rows[0]; nr=int(nr or 0);nb=int(nb or 0)
        if nr<50 or nb<150:return 0.0,_sample_reliability(nr,150)*_sample_reliability(nb,400)
        # For pitcher contact allowed, higher EV/HH/barrel is worse for pitcher and favorable to batter.
        comps=[_f(vd)/2.0, _f(evd)/2.5, _f(hhd)/0.06, _f(bd)/0.04]
        clipped=[max(-1.5,min(1.5,x)) for x in comps]
        active=sum(1 for x in clipped if abs(x)>0.25)
        score=sum(clipped)/len(clipped) if active>=2 else 0.0
        rel=_sample_reliability(nr,180)*_sample_reliability(nb,500)*min(1.0,active/3.0)
        return max(-1.0,min(1.0,score)),rel

    def team_bullpen_candidates(self, team_abbr: str, cutoff: date, active_ids: set[int] | None = None) -> list[dict[str, Any]]:
        """Recent reliever pool reconstructed from Statcast usage.

        Pitching team is inferred from inning half (top -> home defense, bottom -> away defense).
        The first pitcher used by that team in a game is treated as the starter for usage
        classification only. This is an operational reconstruction, not a predictive feature by itself.
        """
        if not self.has_data() or not team_abbr:
            return []
        src = self._source_sql()
        sql = f"""
        WITH raw AS (
          SELECT TRY_CAST(game_pk AS BIGINT) game_pk,
                 TRY_CAST(game_date AS DATE) gd,
                 TRY_CAST(pitcher AS BIGINT) pid,
                 p_throws,
                 TRY_CAST(at_bat_number AS INTEGER) abn,
                 TRY_CAST(inning AS INTEGER) inning_i,
                 CASE WHEN lower(inning_topbot)='top' THEN home_team ELSE away_team END pitching_team,
                 events,
                 TRY_CAST(launch_speed AS DOUBLE) ev
          FROM {src}
          WHERE TRY_CAST(game_date AS DATE)< ?
            AND TRY_CAST(game_date AS DATE)>=TRY_CAST(? AS DATE)-INTERVAL 45 DAY
        ), per_game AS (
          SELECT game_pk, gd, pitching_team, pid,
                 any_value(p_throws) hand,
                 min(abn) first_ab,
                 min(inning_i) entry_inning,
                 count(*) pitches,
                 count(*) FILTER(WHERE events IS NOT NULL AND events<>'') bf,
                 count(*) FILTER(WHERE events='home_run') hr,
                 avg(CASE WHEN ev>=95 THEN 1.0 WHEN ev IS NOT NULL THEN 0.0 END) FILTER(WHERE ev IS NOT NULL) hardhit
          FROM raw WHERE pitching_team=?
          GROUP BY game_pk,gd,pitching_team,pid
        ), ordered AS (
          SELECT *, row_number() OVER(PARTITION BY game_pk,pitching_team ORDER BY first_ab,pid) rn
          FROM per_game
        ), relief AS (
          SELECT * FROM ordered WHERE rn>1
        )
        SELECT pid, any_value(hand) hand,
               count(*) relief_apps,
               avg(bf) avg_bf,
               avg(entry_inning) avg_entry_inning,
               sum(hr)*1.0/NULLIF(sum(bf),0) hr_bf,
               avg(hardhit) hardhit_allowed,
               max(gd) last_date,
               sum(pitches) FILTER(WHERE gd>=TRY_CAST(? AS DATE)-INTERVAL 1 DAY) pitches_1d,
               sum(pitches) FILTER(WHERE gd>=TRY_CAST(? AS DATE)-INTERVAL 2 DAY) pitches_2d,
               sum(pitches) FILTER(WHERE gd>=TRY_CAST(? AS DATE)-INTERVAL 3 DAY) pitches_3d,
               count(*) FILTER(WHERE gd>=TRY_CAST(? AS DATE)-INTERVAL 2 DAY) apps_2d
        FROM relief
        GROUP BY pid
        HAVING count(*)>=2
        ORDER BY relief_apps DESC
        """
        params=(cutoff.isoformat(),cutoff.isoformat(),team_abbr,cutoff.isoformat(),cutoff.isoformat(),cutoff.isoformat(),cutoff.isoformat())
        rows=self.query(sql,params)
        out=[]
        for r in rows:
            pid=int(r[0])
            if active_ids is not None and pid not in active_ids:
                continue
            out.append({
                "pitcher_id":pid,
                "hand":r[1] or "R",
                "relief_apps":int(r[2] or 0),
                "avg_bf":_f(r[3]),
                "avg_entry_inning":_f(r[4]),
                "hr_bf":_f(r[5]),
                "hardhit_allowed":_f(r[6]),
                "last_date":str(r[7]) if r[7] else None,
                "pitches_1d":_f(r[8]),
                "pitches_2d":_f(r[9]),
                "pitches_3d":_f(r[10]),
                "apps_2d":int(r[11] or 0),
            })
        return out

    def batter_vs_pitcher_group(self, batter_id: int, pitcher_ids: list[int], cutoff: date) -> tuple[int,float,float]:
        if not self.has_data() or not pitcher_ids:
            return 0,0.0,0.0
        src=self._source_sql()
        placeholders=','.join('?' for _ in pitcher_ids)
        sql=f"""
        SELECT count(*) FILTER(WHERE events IS NOT NULL AND events<>''),
               count(*) FILTER(WHERE events='home_run')*1.0/NULLIF(count(*) FILTER(WHERE events IS NOT NULL AND events<>''),0),
               avg(TRY_CAST(estimated_slg_using_speedangle AS DOUBLE)) FILTER(WHERE estimated_slg_using_speedangle IS NOT NULL AND estimated_slg_using_speedangle<>'')
        FROM {src}
        WHERE batter=? AND pitcher IN ({placeholders}) AND TRY_CAST(game_date AS DATE)< ?
        """
        rows=self.query(sql,[str(batter_id), *[str(x) for x in pitcher_ids], cutoff.isoformat()])
        if not rows: return 0,0.0,0.0
        return int(rows[0][0] or 0), _f(rows[0][1]), _f(rows[0][2])

def _safe_div(a: float, b: float) -> float:
    return float(a) / float(b) if b else 0.0


def _f(v: Any) -> float:
    try:
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return 0.0
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _sample_reliability(n: float, k: float) -> float:
    n = max(float(n), 0.0)
    return n / (n + k) if n + k else 0.0


def _history_class(pa: int) -> str:
    # Classification labels only; exact production boundaries are ultimately stored in the model package.
    if pa >= 1000:
        return "ESTABLISHED_MLB"
    if pa >= 200:
        return "LIMITED_MLB"
    if pa > 0:
        return "MINIMAL_HISTORY"
    return "MINIMAL_HISTORY"
