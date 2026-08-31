# V1.1.0 Plan 2 — Settlement Contract (mapped before any change)

Read-only mapping of the settlement system that already exists in the repo,
done before writing `DailyAccuracyService`/`SettlementCoordinator`, per the
plan's Task 1. Nothing in this document changes behavior.

## 1. Final HR result provider

- `MLBProvider.game_feed(game_pk)` (`src/mlb_hr/providers/mlb.py`) fetches the
  raw official MLB live-game feed (play-by-play + box score) for one game.
- `PostgameEngine.evaluate(...)` (`src/mlb_hr/postgame/engine.py`) is the
  deterministic settlement evaluator: it reconciles play-by-play HR count
  against the box score's `homeRuns`/`plateAppearances`, and only produces
  `CONFIRMED_SETTLEMENT`-eligible data (`PROVISIONAL_SETTLEMENT` first, then
  `confirm_unchanged()` promotes to `CONFIRMED_SETTLEMENT` after 24h of an
  unchanged provisional result). PBP/box conflicts produce
  `REVIEW_REQUIRED`, never a guessed result. Non-`FINAL` games produce
  `LIVE`/`WAITING_FOR_GAME`/`POSTPONED`/`SUSPENDED`/`CANCELLED` — never a
  fabricated result.

## 2. Prediction settlement entry point

`SettlementService.reconcile_pending()` (`src/mlb_hr/services/settlement.py`):
1. `store.pending_predictions()` — predictions with `tracked=1` (i.e. not
   `NOT_ELIGIBLE`), `pregame_locked=1`, `is_latest_pregame=1`,
   `pregame_valid=1`, and no active settlement already in a terminal state
   (`CONFIRMED_SETTLEMENT`/`VOID`/`CANCELLED`).
2. For each, fetches the game feed (cached per `game_pk` within one run) and
   calls `PostgameEngine.evaluate(...)`.
3. `store.save_settlement(rec)` — always inserts a new versioned row and
   deactivates the previous one; the row itself is never mutated in place.
4. On `CONFIRMED_SETTLEMENT` with a known `actual_hr_binary`, calls
   `store.apply_paper_settlement(prediction_id, won)` (bankroll ledger).
5. At the end, always calls `self.reconcile_combinations()` — combination
   settlement is already part of this single entry point, not a separate one
   that needs to be called independently.

## 3. Combination settlement entry point

`SettlementService.reconcile_combinations()` (same file, called automatically
by `reconcile_pending()`):
1. `store.pending_combinations()` — combinations with no active settlement in
   a terminal state.
2. Resolves each leg's prediction id from the combination's own `legs_json`
   and looks up `store.leg_settlements(ids)`.
3. A combination is `CONFIRMED_SETTLEMENT` / `won=True` only when **every**
   leg's active settlement is `CONFIRMED_SETTLEMENT` **and**
   `actual_hr_binary==1` for all of them — this is already exactly the "all
   required legs HR" rule this phase must implement; nothing new needed here.
4. Any `VOID`/`CANCELLED`/`POSTPONED` leg makes the whole combination `VOID`.
5. `store.save_combination_settlement(...)` — versioned insert, same pattern
   as predictions.

## 4. DB uniqueness / idempotency mechanism

- `settlements`: `UNIQUE(prediction_id, result_version)`, `active` flag
  (`save_settlement` deactivates the prior active row, then inserts a new
  one — append-only, no row is ever rewritten).
- `combination_settlements`: `UNIQUE(combination_id, result_version)`, same
  active-flag versioning pattern.
- `paper_bankroll_events`: **no unique constraint**, but
  `apply_paper_settlement()` has an explicit existence guard —
  `SELECT 1 ... WHERE prediction_id=? AND event_type IN ('WIN','LOSS')` — and
  returns immediately if a WIN/LOSS event already exists for that
  prediction. A second call is a genuine no-op at the row-write level, not
  just "produces the same computed result."
- `pending_predictions()` / `pending_combinations()` themselves exclude
  anything already in a terminal settlement state, so a second
  `reconcile_pending()` run does not even re-fetch/re-evaluate
  already-`CONFIRMED_SETTLEMENT`/`VOID` rows — idempotency is enforced at
  three independent layers (selection, versioned insert, bankroll guard).
- **Existing gap, not touched by this mapping:** for `PROVISIONAL_SETTLEMENT`
  rows the SELECT does re-include them each run (by design — they're not
  terminal yet), and each run inserts a new settlement version even when
  the underlying result is unchanged (`save_settlement` has no
  "same as before, skip" short-circuit outside the specific 24h
  `confirm_unchanged` path). This does not duplicate P&L or bankroll events
  (those only ever fire once, on the transition to `CONFIRMED_SETTLEMENT`),
  but it does mean `settlements` accumulates a new row per re-run while a
  game is still live/provisional. This is pre-existing behavior, not
  something this phase's idempotency test needs to change — the repeat-run
  regression test (Task 3) targets counts/P&L snapshots, which this
  behavior does not affect.

## 5. History read methods (existing, to be reused — not re-implemented)

- `store.history_prediction_rows()` — `predictions` joined to
  `model_ledger` (stake/odds at prediction) and `settlements`
  (status/actual_hr_binary) and `paper_bankroll_events` (pnl), filtered to
  `is_latest_pregame=1 AND pregame_valid=1`. Returns **every** column of
  `predictions`, including `created_at` and `game_time` — both needed for
  the pregame-only predicate.
- `store.history_combination_rows()` — `combinations` joined to
  `combination_settlements` (status/won/profit_loss).
- `store.prediction_rows_by_ids(ids)` / `store.leg_settlements(ids)` — used
  to resolve each combination leg's own `game_time` and settlement status by
  looking up its `prediction_id` inside `legs_json`.
- `services/history.py::HistoryService.player_records()` /
  `.combination_records()` already implement the exact population rule this
  phase needs: `NOT_ELIGIBLE` rows are excluded
  (`_PLAYER_STATUS_BY_CLASSIFICATION` has no `NOT_ELIGIBLE` key →
  `continue`), `WATCH`/`NO_BET` are **included** (status `WATCH`/`NO_FILTER`),
  `result` is `PENDING`/`HR`/`NO_HR` derived from `actual_hr_binary`, and
  combination legs' `game_time` is already resolved via the
  `prediction_rows_by_ids` lookup described above.

**Decision:** `DailyAccuracyService` will call `HistoryService(store)`
internally (period="ALL", no status/result filter) and apply only the
*additional* filters this phase specifically needs (local-date scoping,
`final_probability >= 0.05`, `created_at < game_time`) on top of the
already-correct population `HistoryService` returns, then map into this
phase's own `PlayerAccuracyRecord`/`CombinationAccuracyRecord`/
`DailyAccuracySummary` dataclasses. This avoids writing new SQL or
duplicating the exclusion logic, per the plan's explicit instruction that the
UI must not reproduce SQL/filter logic — and neither should the new service,
beyond the narrow additions this phase requires.

## 6. Startup / trigger wiring (current state, before Task 5)

- `src/mlb_hr/app.py`: `SettlementService(store).reconcile_pending` already
  runs on startup (non-demo mode only) via
  `QTimer.singleShot(2500, start_settlement_reconcile)` — **a fixed 2.5s
  delay, not explicitly chained to the health check's completion.** The
  health check itself starts at `QTimer.singleShot(50, start_health)`. In
  practice health almost always finishes well before 2.5s, but this is not
  the same as "runs after health OK" the plan asks for — Task 5 will replace
  the fixed timer with a callback chained to `apply_health_report`.
- `TodayWidget.refresh()`/`_loaded()` (`src/mlb_hr/ui/today.py`): no
  settlement call today. The "runs after ACTUALIZAR" trigger does not exist
  yet — new for this phase.
- `HistoryWidget` (`src/mlb_hr/ui/history.py`): no "ACTUALIZAR RESULTADOS"
  button exists yet — new for this phase.

## 7. Data availability check (per the user's stop condition)

All three items the user named as potential gaps are confirmed **present**:

1. **Whether a prediction was made before the game started:**
   `predictions.created_at` and `predictions.game_time` both exist on every
   row (schema `001_initial.sql`). `created_at < game_time` is directly
   computable.
2. **Official result:** `settlements.status='CONFIRMED_SETTLEMENT'` +
   `settlements.actual_hr_binary`, produced only by `PostgameEngine` from the
   real MLB official feed (never inferred).
3. **Original legs of a combination:** `combinations.legs_json`, written
   once at creation by `save_combination()` (`INSERT OR IGNORE`, never
   updated afterward) — the same JSON `HistoryService.combination_records()`
   already parses for the existing COMBINACIONES view.

No schema change is needed for this phase. **Not stopping.**

## 8. Baseline test run (Task 1 Step 2)

```
pytest -q -k "settle or settlement or postgame or bankroll"
```
Result: **6 passed** (`tests/test_postgame.py` x2, `tests/test_storage.py` x3,
`tests/test_history_service.py` x1). This is a thin but currently-green
baseline; Plan 2's new tests add to it without touching these files.
