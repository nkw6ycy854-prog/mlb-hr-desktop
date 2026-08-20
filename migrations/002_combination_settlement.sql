PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS combination_settlements (
    combination_settlement_id INTEGER PRIMARY KEY AUTOINCREMENT,
    combination_id TEXT NOT NULL REFERENCES combinations(combination_id),
    result_version INTEGER NOT NULL,
    status TEXT NOT NULL,
    won INTEGER,
    void_leg_count INTEGER NOT NULL DEFAULT 0,
    profit_loss REAL,
    fetched_at TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    UNIQUE(combination_id, result_version)
);
CREATE INDEX IF NOT EXISTS idx_combo_settlement_active ON combination_settlements(combination_id,active);
