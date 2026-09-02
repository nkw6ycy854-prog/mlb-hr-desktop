PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS favorites (
    favorite_id TEXT PRIMARY KEY,
    player_id INTEGER NOT NULL,
    game_pk INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    player_name TEXT NOT NULL,
    team_name TEXT NOT NULL,
    opponent_name TEXT NOT NULL,
    game_time TEXT,
    snapshot_hr_probability REAL,
    snapshot_practical_status TEXT NOT NULL,
    snapshot_classification TEXT NOT NULL,
    snapshot_confidence_label TEXT NOT NULL,
    snapshot_eligible INTEGER NOT NULL,
    snapshot_best_bookmaker TEXT,
    snapshot_best_american_odds INTEGER,
    snapshot_fanduel_american_odds INTEGER,
    source_prediction_id TEXT,
    operational_status TEXT,
    UNIQUE(player_id, game_pk)
);
CREATE INDEX IF NOT EXISTS idx_favorites_created ON favorites(created_at);

ALTER TABLE combinations ADD COLUMN canonical_key TEXT;
ALTER TABLE combinations ADD COLUMN slate_scope_key TEXT;
ALTER TABLE combinations ADD COLUMN is_canonical INTEGER NOT NULL DEFAULT 1;
ALTER TABLE combinations ADD COLUMN superseded_by TEXT;
CREATE INDEX IF NOT EXISTS idx_combinations_slate_scope ON combinations(kind,slate_scope_key,is_canonical);
CREATE INDEX IF NOT EXISTS idx_combinations_canonical_key ON combinations(canonical_key);
