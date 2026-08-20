PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_state (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS provider_health (
    provider TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    checked_at TEXT NOT NULL,
    latency_ms REAL,
    error_code TEXT,
    message TEXT
);

CREATE TABLE IF NOT EXISTS snapshots (
    snapshot_id TEXT PRIMARY KEY,
    game_pk INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    lineup_json TEXT NOT NULL,
    starter_json TEXT NOT NULL,
    weather_json TEXT,
    source_timestamps_json TEXT NOT NULL,
    feature_vector_json TEXT NOT NULL,
    model_package_hash TEXT NOT NULL,
    deterministic_seed INTEGER NOT NULL,
    UNIQUE(game_pk, created_at, model_package_hash)
);

CREATE TABLE IF NOT EXISTS predictions (
    prediction_id TEXT PRIMARY KEY,
    series_key TEXT NOT NULL,
    snapshot_id TEXT NOT NULL REFERENCES snapshots(snapshot_id),
    game_pk INTEGER NOT NULL,
    player_id INTEGER NOT NULL,
    player_name TEXT NOT NULL,
    pitcher_id INTEGER NOT NULL,
    pitcher_name TEXT NOT NULL,
    team_name TEXT NOT NULL,
    opponent_name TEXT NOT NULL,
    game_time TEXT,
    raw_probability REAL NOT NULL,
    final_probability REAL NOT NULL,
    matchup_score REAL NOT NULL,
    reliability REAL NOT NULL,
    confidence_score REAL NOT NULL,
    confidence_label TEXT NOT NULL,
    p10 REAL NOT NULL,
    p50 REAL NOT NULL,
    p90 REAL NOT NULL,
    classification TEXT NOT NULL,
    user_action TEXT NOT NULL,
    critic TEXT NOT NULL,
    integrity TEXT NOT NULL,
    reasons_json TEXT NOT NULL,
    main_risk TEXT,
    warnings_json TEXT NOT NULL,
    model_version TEXT NOT NULL,
    feature_version TEXT NOT NULL,
    calibration_version TEXT NOT NULL,
    quality_gate_version TEXT NOT NULL,
    model_health TEXT NOT NULL,
    tracked INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    pregame_locked INTEGER NOT NULL DEFAULT 0,
    is_latest_pregame INTEGER NOT NULL DEFAULT 1,
    superseded_by TEXT
);

CREATE INDEX IF NOT EXISTS idx_predictions_game ON predictions(game_pk);
CREATE INDEX IF NOT EXISTS idx_predictions_series ON predictions(series_key,is_latest_pregame);
CREATE INDEX IF NOT EXISTS idx_predictions_player ON predictions(player_id);
CREATE INDEX IF NOT EXISTS idx_predictions_created ON predictions(created_at);

CREATE TABLE IF NOT EXISTS prediction_revisions (
    revision_id INTEGER PRIMARY KEY AUTOINCREMENT,
    prediction_id TEXT NOT NULL REFERENCES predictions(prediction_id),
    revision_number INTEGER NOT NULL,
    recorded_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    UNIQUE(prediction_id, revision_number)
);

CREATE TABLE IF NOT EXISTS odds_snapshots (
    odds_id INTEGER PRIMARY KEY AUTOINCREMENT,
    prediction_id TEXT REFERENCES predictions(prediction_id),
    game_pk INTEGER NOT NULL,
    player_id INTEGER NOT NULL,
    bookmaker TEXT NOT NULL,
    market TEXT NOT NULL,
    american_odds INTEGER,
    decimal_odds REAL,
    implied_probability REAL,
    source_last_update TEXT,
    fetched_at TEXT NOT NULL,
    freshness TEXT NOT NULL,
    source TEXT NOT NULL,
    point REAL,
    is_odds_at_prediction INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_odds_lookup ON odds_snapshots(game_pk, player_id, fetched_at);

CREATE TABLE IF NOT EXISTS model_ledger (
    prediction_id TEXT PRIMARY KEY REFERENCES predictions(prediction_id),
    reference_stake REAL NOT NULL,
    odds_at_prediction INTEGER,
    decimal_odds_at_prediction REAL,
    implied_probability_at_prediction REAL,
    edge_pp_at_prediction REAL,
    user_bet INTEGER NOT NULL DEFAULT 0,
    recorded_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_bet_ledger (
    user_bet_id INTEGER PRIMARY KEY AUTOINCREMENT,
    prediction_id TEXT NOT NULL REFERENCES predictions(prediction_id),
    stake REAL NOT NULL,
    actual_odds INTEGER,
    recorded_at TEXT NOT NULL,
    note TEXT
);

CREATE TABLE IF NOT EXISTS combinations (
    combination_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    created_at TEXT NOT NULL,
    legs_json TEXT NOT NULL,
    model_probability_proxy REAL NOT NULL,
    robustness REAL NOT NULL,
    actual_parlay_odds INTEGER,
    estimated_decimal_odds REAL,
    warnings_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settlements (
    settlement_id INTEGER PRIMARY KEY AUTOINCREMENT,
    prediction_id TEXT NOT NULL REFERENCES predictions(prediction_id),
    result_version INTEGER NOT NULL,
    status TEXT NOT NULL,
    actual_hr_count INTEGER,
    actual_hr_binary INTEGER,
    actual_pa INTEGER,
    actual_pa_vs_starter INTEGER,
    actual_pa_vs_bullpen INTEGER,
    appearance_status TEXT NOT NULL,
    verified_pbp INTEGER NOT NULL DEFAULT 0,
    verified_box INTEGER NOT NULL DEFAULT 0,
    result_source TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    change_reason TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    UNIQUE(prediction_id, result_version)
);

CREATE TABLE IF NOT EXISTS paper_bankroll_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    prediction_id TEXT REFERENCES predictions(prediction_id),
    combination_id TEXT REFERENCES combinations(combination_id),
    amount REAL NOT NULL,
    event_type TEXT NOT NULL,
    balance_after REAL NOT NULL,
    recorded_at TEXT NOT NULL,
    note TEXT
);

CREATE TABLE IF NOT EXISTS audit_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at TEXT NOT NULL,
    run_id TEXT,
    snapshot_id TEXT,
    prediction_id TEXT,
    game_pk INTEGER,
    module TEXT NOT NULL,
    severity TEXT NOT NULL,
    event_code TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pending_jobs (
    job_id TEXT PRIMARY KEY,
    job_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    state TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(job_type, entity_id, state)
);
