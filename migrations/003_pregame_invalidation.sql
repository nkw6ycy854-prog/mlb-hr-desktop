ALTER TABLE predictions ADD COLUMN pregame_valid INTEGER NOT NULL DEFAULT 1;
ALTER TABLE predictions ADD COLUMN invalidation_reason TEXT;
CREATE INDEX IF NOT EXISTS idx_predictions_latest_valid ON predictions(game_pk,is_latest_pregame,pregame_valid);
