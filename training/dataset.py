from __future__ import annotations

from pathlib import Path


BASE_FEATURE_COLUMNS = [
    "league_hr_pa_raw","league_pa_prior",
    "batter_pa_prior","batter_hr_prior","batter_bbe_prior","batter_barrel_prior","batter_hardhit_prior","batter_ev_sum_prior","batter_ev_n_prior","batter_fb_prior","batter_bbtype_n_prior","batter_xslg_sum_prior","batter_xslg_n_prior",
    "batter_pa_recent","batter_hr_recent","batter_split_pa_prior","batter_split_hr_prior",
    "pitcher_bf_prior","pitcher_hr_prior","pitcher_bbe_prior","pitcher_barrel_prior","pitcher_hardhit_prior","pitcher_ev_sum_prior","pitcher_ev_n_prior","pitcher_xslg_sum_prior","pitcher_xslg_n_prior",
    "pitcher_bf_recent","pitcher_hr_recent","pitcher_split_bf_prior","pitcher_split_hr_prior",
]


def build_training_table(parquet_glob: str, output_path: Path) -> Path:
    """Build one row per completed PA with pre-game rolling features only.

    All windows operate on game-level aggregates and use `... 1 PRECEDING`, so nothing
    from the current game enters its own feature snapshot. The row's outcome is kept
    separately as `label_hr`.
    """
    try:
        import duckdb
    except Exception as exc:
        raise RuntimeError("DuckDB is required for training") from exc
    output_path.parent.mkdir(parents=True,exist_ok=True)
    g=parquet_glob.replace("'","''");out=str(output_path).replace("'","''")
    con=duckdb.connect(database=":memory:");con.execute("PRAGMA threads=4")
    sql=f"""
    COPY (
    WITH raw AS (
      SELECT TRY_CAST(game_pk AS BIGINT) game_pk,
             TRY_CAST(game_date AS DATE) game_date,
             TRY_CAST(at_bat_number AS INTEGER) at_bat_number,
             TRY_CAST(batter AS BIGINT) batter,
             TRY_CAST(pitcher AS BIGINT) pitcher,
             stand, p_throws, home_team, away_team, lower(inning_topbot) inning_topbot,
             events, pitch_type, bb_type,
             TRY_CAST(launch_speed AS DOUBLE) ev,
             TRY_CAST(launch_angle AS DOUBLE) la,
             TRY_CAST(launch_speed_angle AS INTEGER) lsa,
             TRY_CAST(estimated_slg_using_speedangle AS DOUBLE) exslg,
             CASE WHEN lower(inning_topbot)='top' THEN away_team ELSE home_team END batting_team,
             CASE WHEN lower(inning_topbot)='top' THEN home_team ELSE away_team END pitching_team
      FROM read_parquet('{g}',union_by_name=true,hive_partitioning=true)
      WHERE game_type='R' AND TRY_CAST(game_date AS DATE) IS NOT NULL
    ), pa AS (
      SELECT * FROM raw WHERE events IS NOT NULL AND events<>''
    ), batter_game AS (
      SELECT game_pk,game_date,batter,batting_team,
             min(at_bat_number) first_ab,
             count(*) pa,
             sum(CASE WHEN events='home_run' THEN 1 ELSE 0 END) hr,
             count(*) FILTER(WHERE ev IS NOT NULL) bbe,
             sum(CASE WHEN lsa=6 THEN 1 ELSE 0 END) FILTER(WHERE ev IS NOT NULL) barrel,
             sum(CASE WHEN ev>=95 THEN 1 ELSE 0 END) FILTER(WHERE ev IS NOT NULL) hardhit,
             sum(ev) FILTER(WHERE ev IS NOT NULL) ev_sum,
             count(ev) ev_n,
             sum(CASE WHEN bb_type='fly_ball' THEN 1 ELSE 0 END) FILTER(WHERE bb_type IS NOT NULL AND bb_type<>'') fb,
             count(*) FILTER(WHERE bb_type IS NOT NULL AND bb_type<>'') bbtype_n,
             sum(exslg) FILTER(WHERE exslg IS NOT NULL) xslg_sum,
             count(exslg) xslg_n
      FROM pa GROUP BY game_pk,game_date,batter,batting_team
    ), lineup AS (
      SELECT *, row_number() OVER(PARTITION BY game_pk,batting_team ORDER BY first_ab,batter) lineup_slot
      FROM batter_game
    ), batter_roll AS (
      SELECT *,
        sum(pa) OVER(PARTITION BY batter ORDER BY game_date,game_pk ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) batter_pa_prior,
        sum(hr) OVER(PARTITION BY batter ORDER BY game_date,game_pk ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) batter_hr_prior,
        sum(bbe) OVER(PARTITION BY batter ORDER BY game_date,game_pk ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) batter_bbe_prior,
        sum(barrel) OVER(PARTITION BY batter ORDER BY game_date,game_pk ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) batter_barrel_prior,
        sum(hardhit) OVER(PARTITION BY batter ORDER BY game_date,game_pk ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) batter_hardhit_prior,
        sum(ev_sum) OVER(PARTITION BY batter ORDER BY game_date,game_pk ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) batter_ev_sum_prior,
        sum(ev_n) OVER(PARTITION BY batter ORDER BY game_date,game_pk ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) batter_ev_n_prior,
        sum(fb) OVER(PARTITION BY batter ORDER BY game_date,game_pk ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) batter_fb_prior,
        sum(bbtype_n) OVER(PARTITION BY batter ORDER BY game_date,game_pk ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) batter_bbtype_n_prior,
        sum(xslg_sum) OVER(PARTITION BY batter ORDER BY game_date,game_pk ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) batter_xslg_sum_prior,
        sum(xslg_n) OVER(PARTITION BY batter ORDER BY game_date,game_pk ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) batter_xslg_n_prior,
        sum(pa) OVER(PARTITION BY batter ORDER BY game_date,game_pk ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING) batter_pa_recent,
        sum(hr) OVER(PARTITION BY batter ORDER BY game_date,game_pk ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING) batter_hr_recent
      FROM lineup
    ), pitcher_game AS (
      SELECT game_pk,game_date,pitcher,pitching_team,any_value(p_throws) p_throws,
             min(at_bat_number) first_ab,count(*) bf,
             sum(CASE WHEN events='home_run' THEN 1 ELSE 0 END) hr,
             count(*) FILTER(WHERE ev IS NOT NULL) bbe,
             sum(CASE WHEN lsa=6 THEN 1 ELSE 0 END) FILTER(WHERE ev IS NOT NULL) barrel,
             sum(CASE WHEN ev>=95 THEN 1 ELSE 0 END) FILTER(WHERE ev IS NOT NULL) hardhit,
             sum(ev) FILTER(WHERE ev IS NOT NULL) ev_sum,count(ev) ev_n,
             sum(exslg) FILTER(WHERE exslg IS NOT NULL) xslg_sum,count(exslg) xslg_n
      FROM pa GROUP BY game_pk,game_date,pitcher,pitching_team
    ), pitcher_order AS (
      SELECT *,row_number() OVER(PARTITION BY game_pk,pitching_team ORDER BY first_ab,pitcher) pitcher_order
      FROM pitcher_game
    ), pitcher_roll AS (
      SELECT *,
        sum(bf) OVER(PARTITION BY pitcher ORDER BY game_date,game_pk ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) pitcher_bf_prior,
        sum(hr) OVER(PARTITION BY pitcher ORDER BY game_date,game_pk ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) pitcher_hr_prior,
        sum(bbe) OVER(PARTITION BY pitcher ORDER BY game_date,game_pk ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) pitcher_bbe_prior,
        sum(barrel) OVER(PARTITION BY pitcher ORDER BY game_date,game_pk ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) pitcher_barrel_prior,
        sum(hardhit) OVER(PARTITION BY pitcher ORDER BY game_date,game_pk ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) pitcher_hardhit_prior,
        sum(ev_sum) OVER(PARTITION BY pitcher ORDER BY game_date,game_pk ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) pitcher_ev_sum_prior,
        sum(ev_n) OVER(PARTITION BY pitcher ORDER BY game_date,game_pk ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) pitcher_ev_n_prior,
        sum(xslg_sum) OVER(PARTITION BY pitcher ORDER BY game_date,game_pk ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) pitcher_xslg_sum_prior,
        sum(xslg_n) OVER(PARTITION BY pitcher ORDER BY game_date,game_pk ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) pitcher_xslg_n_prior,
        sum(bf) OVER(PARTITION BY pitcher ORDER BY game_date,game_pk ROWS BETWEEN 15 PRECEDING AND 1 PRECEDING) pitcher_bf_recent,
        sum(hr) OVER(PARTITION BY pitcher ORDER BY game_date,game_pk ROWS BETWEEN 15 PRECEDING AND 1 PRECEDING) pitcher_hr_recent
      FROM pitcher_order
    ), batter_split_game AS (
      SELECT game_pk,game_date,batter,p_throws,count(*) pa,sum(CASE WHEN events='home_run' THEN 1 ELSE 0 END) hr
      FROM pa GROUP BY game_pk,game_date,batter,p_throws
    ), batter_split_roll AS (
      SELECT *,
        sum(pa) OVER(PARTITION BY batter,p_throws ORDER BY game_date,game_pk ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) batter_split_pa_prior,
        sum(hr) OVER(PARTITION BY batter,p_throws ORDER BY game_date,game_pk ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) batter_split_hr_prior
      FROM batter_split_game
    ), pitcher_split_game AS (
      SELECT game_pk,game_date,pitcher,stand,count(*) bf,sum(CASE WHEN events='home_run' THEN 1 ELSE 0 END) hr
      FROM pa GROUP BY game_pk,game_date,pitcher,stand
    ), pitcher_split_roll AS (
      SELECT *,
        sum(bf) OVER(PARTITION BY pitcher,stand ORDER BY game_date,game_pk ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) pitcher_split_bf_prior,
        sum(hr) OVER(PARTITION BY pitcher,stand ORDER BY game_date,game_pk ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) pitcher_split_hr_prior
      FROM pitcher_split_game
    ), league_day AS (
      SELECT game_date,count(*) pa,sum(CASE WHEN events='home_run' THEN 1 ELSE 0 END) hr FROM pa GROUP BY game_date
    ), league_roll AS (
      SELECT game_date,
        sum(pa) OVER(ORDER BY game_date ROWS BETWEEN 730 PRECEDING AND 1 PRECEDING) league_pa_prior,
        sum(hr) OVER(ORDER BY game_date ROWS BETWEEN 730 PRECEDING AND 1 PRECEDING) league_hr_prior
      FROM league_day
    ), pa_enriched AS (
      SELECT p.game_pk,p.game_date,p.at_bat_number,p.batter,p.pitcher,p.stand,p.p_throws,p.batting_team,p.pitching_team,
             CASE WHEN p.events='home_run' THEN 1 ELSE 0 END label_hr,
             br.lineup_slot,
             pr.pitcher_order=1 AS is_starter_pitcher,
             lr.league_hr_prior*1.0/NULLIF(lr.league_pa_prior,0) league_hr_pa_raw,lr.league_pa_prior,
             br.batter_pa_prior,br.batter_hr_prior,br.batter_bbe_prior,br.batter_barrel_prior,br.batter_hardhit_prior,
             br.batter_ev_sum_prior,br.batter_ev_n_prior,br.batter_fb_prior,br.batter_bbtype_n_prior,br.batter_xslg_sum_prior,br.batter_xslg_n_prior,
             br.batter_pa_recent,br.batter_hr_recent,
             bsr.batter_split_pa_prior,bsr.batter_split_hr_prior,
             pr.pitcher_bf_prior,pr.pitcher_hr_prior,pr.pitcher_bbe_prior,pr.pitcher_barrel_prior,pr.pitcher_hardhit_prior,
             pr.pitcher_ev_sum_prior,pr.pitcher_ev_n_prior,pr.pitcher_xslg_sum_prior,pr.pitcher_xslg_n_prior,
             pr.pitcher_bf_recent,pr.pitcher_hr_recent,
             psr.pitcher_split_bf_prior,psr.pitcher_split_hr_prior
      FROM pa p
      JOIN batter_roll br ON br.game_pk=p.game_pk AND br.batter=p.batter
      JOIN pitcher_roll pr ON pr.game_pk=p.game_pk AND pr.pitcher=p.pitcher AND pr.pitching_team=p.pitching_team
      LEFT JOIN batter_split_roll bsr ON bsr.game_pk=p.game_pk AND bsr.batter=p.batter AND bsr.p_throws=p.p_throws
      LEFT JOIN pitcher_split_roll psr ON psr.game_pk=p.game_pk AND psr.pitcher=p.pitcher AND psr.stand=p.stand
      LEFT JOIN league_roll lr ON lr.game_date=p.game_date
      WHERE br.lineup_slot<=9
    )
    SELECT * FROM pa_enriched
    ) TO '{out}' (FORMAT PARQUET,COMPRESSION ZSTD)
    """
    con.execute(sql);con.close();return output_path
