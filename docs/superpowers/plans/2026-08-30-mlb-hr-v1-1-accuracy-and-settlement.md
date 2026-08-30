# MLB HR V1.1.0 Daily Accuracy + Settlement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add ACIERTOS HOY and reliable automatic result settlement without changing the predictive engine.

**Architecture:** Reuse existing settlement/storage evidence as source of truth. Add `DailyAccuracyService` to derive today's accuracy and a thin `SettlementCoordinator` invoked on startup, ACTUALIZAR and ACTUALIZAR RESULTADOS.

**Tech Stack:** Python 3.13, SQLite, PySide6, pytest.

**Spec:** `docs/superpowers/specs/2026-08-30-mlb-hr-v1-1-design.md`

## Global Constraints

- Player accuracy population: stored pregame, valid, not `NOT_ELIGIBLE`, probability `>= 0.05`.
- Pending is not a miss.
- Combination win requires all required legs HR.
- Settlement must be idempotent.
- Use only existing official result/settlement path.
- Never alter historical probability/classification.

---

### Task 1: Map current settlement interfaces

**Files:**
- Read current files found by:
```bash
rg -n "settle|settlement|actual_hr|postgame|bankroll|won|profit_loss" src tests
```
- Create: `V1_1_SETTLEMENT_CONTRACT.md`

- [ ] **Step 1: Record exact symbols**

Document the current:
- final HR result provider;
- prediction settlement entry point;
- combination settlement entry point;
- DB uniqueness/idempotency mechanism;
- history read methods.

- [ ] **Step 2: Run baseline settlement tests**

```bash
pytest -q -k "settle or settlement or postgame or bankroll"
```

- [ ] **Step 3: Commit contract**

```bash
git add V1_1_SETTLEMENT_CONTRACT.md
git commit -m "docs: record settlement contract for v1.1"
```

---

### Task 2: Add DailyAccuracyService

**Files:**
- Create: `src/mlb_hr/services/daily_accuracy.py`
- Create: `tests/test_daily_accuracy.py`
- Modify: `src/mlb_hr/storage/sqlite.py` only if current read methods lack required fields.

**Interfaces:**
```python
@dataclass(frozen=True)
class PlayerAccuracyRecord:
    prediction_id: str
    player_name: str
    game_pk: int
    game_time_utc: datetime
    probability: float
    classification: str
    odds_at_prediction: int | None
    result: str
    pnl: float | None

@dataclass(frozen=True)
class CombinationAccuracyRecord:
    combination_id: str
    kind: str
    legs: tuple
    result: str
    odds: int | None
    pnl: float | None

@dataclass(frozen=True)
class DailyAccuracySummary:
    eligible_predictions: int
    resolved_predictions: int
    player_hits: int
    player_pending: int
    player_hit_rate: float | None
    combo_wins: int
    combo_pending: int

class DailyAccuracyService:
    def for_date(self, local_date: date, timezone_name: str): ...
```

- [ ] **Step 1: Threshold test**

Rows at 4.9%, 5.0%, 12.0% plus NOT_ELIGIBLE. Assert only valid `>=5%` enter the eligible population.

- [ ] **Step 2: Pending denominator test**

With 2 HR, 6 NO_HR and 2 PENDING:
```python
assert summary.resolved_predictions == 8
assert summary.player_hits == 2
assert summary.player_hit_rate == 0.25
assert summary.player_pending == 2
```

- [ ] **Step 3: Pregame-only test**

A prediction whose `created_at >= game_time_utc` must be excluded.

- [ ] **Step 4: Combination result test**

One GANADA, one PERDIDA, one PENDIENTE:
```python
assert summary.combo_wins == 1
assert summary.combo_pending == 1
```

- [ ] **Step 5: Verify RED**

```bash
pytest tests/test_daily_accuracy.py -v
```

- [ ] **Step 6: Implement**

Core player predicate:
```python
valid = (
    row.created_at < row.game_time
    and row.classification != "NOT_ELIGIBLE"
    and row.final_probability >= 0.05
)
```

Use `GameTimeService(timezone_name).localize(game_time).date()` for the requested local day.

- [ ] **Step 7: Verify GREEN**

```bash
pytest tests/test_daily_accuracy.py -v
pytest -q
```

- [ ] **Step 8: Commit**

```bash
git add src/mlb_hr/services/daily_accuracy.py src/mlb_hr/storage/sqlite.py tests/test_daily_accuracy.py
git commit -m "feat: derive daily prediction accuracy"
```

---

### Task 3: Add idempotent SettlementCoordinator

**Files:**
- Create: `src/mlb_hr/services/settlement_coordinator.py`
- Create: `tests/test_settlement_coordinator.py`
- Modify existing settlement/storage implementation only if the new regression test proves a defect.

**Interfaces:**
```python
@dataclass(frozen=True)
class SettlementRunResult:
    checked: int
    updated: int
    still_pending: int
    errors: tuple[str, ...]

class SettlementCoordinator:
    def refresh_pending(self) -> SettlementRunResult: ...
```

- [ ] **Step 1: Repeat-run regression test**

```python
first = coordinator.refresh_pending()
snapshot1 = query_settlement_counts_and_total_pnl(store)
second = coordinator.refresh_pending()
snapshot2 = query_settlement_counts_and_total_pnl(store)

assert snapshot2 == snapshot1
assert second.updated == 0
```

Implement `query_settlement_counts_and_total_pnl` in the test using direct SELECTs.

- [ ] **Step 2: LIVE game test**

Non-final results remain pending and create no LOSS/P&L event.

- [ ] **Step 3: Run test**

If the existing settlement path already satisfies the regression, keep it unchanged and implement only the wrapper.

- [ ] **Step 4: Implement coordinator**

It calls only unresolved official settlement paths and never `analyze_slate()`.

- [ ] **Step 5: Verify**

```bash
pytest tests/test_settlement_coordinator.py -v
pytest -q -k "settle or settlement or postgame or bankroll"
pytest -q
```

- [ ] **Step 6: Commit**

```bash
git add src/mlb_hr/services/settlement_coordinator.py tests/test_settlement_coordinator.py
git diff --name-only
git add -p
git commit -m "feat: coordinate idempotent result settlement"
```

---

### Task 4: Add HISTORIAL → ACIERTOS HOY

**Files:**
- Modify: `src/mlb_hr/ui/history.py`
- Extend: `tests/ui/test_history.py`

**Interfaces:**
- `HistoryWidget.hits_today_btn`
- third `mode_stack` page
- `HistoryWidget.render_hits_today()`

- [ ] **Step 1: View-switch test**

```python
widget.hits_today_btn.click()
assert widget.mode_stack.currentIndex() == 2
```

- [ ] **Step 2: Content test**

Fixture with two player HR hits and one winning combo. Assert:
```text
Jugadores acertados: 2
Combinaciones ganadas: 1
```
and the exact player/combo names are rendered.

- [ ] **Step 3: Empty state test**

Require:
`Todavía no hay predicciones acertadas para esta fecha.`

- [ ] **Step 4: Implement**

Widget consumes `DailyAccuracyService`; it must not reproduce SQL/filter logic. Player/leg times use `GameTimeService`.

- [ ] **Step 5: Verify**

```bash
QT_QPA_PLATFORM=offscreen pytest tests/ui/test_history.py tests/test_daily_accuracy.py -v
pytest -q
```

- [ ] **Step 6: Commit**

```bash
git add src/mlb_hr/ui/history.py tests/ui/test_history.py
git commit -m "feat: show today's correct HR predictions"
```

---

### Task 5: Add ACTUALIZAR RESULTADOS and automatic triggers

**Files:**
- Modify: `src/mlb_hr/ui/history.py`
- Modify: `src/mlb_hr/ui/today.py`
- Modify startup owner: `src/mlb_hr/ui/main_window.py` or `src/mlb_hr/app.py` as mapped in preflight.
- Create: `tests/ui/test_settlement_triggers.py`
- Extend: `tests/ui/test_history.py`
- Extend: `tests/ui/test_today.py`

- [ ] **Step 1: Button lifecycle test**

On click:
```python
assert button.isEnabled() is False
assert "Actualizando resultados" in feedback.text()
```
On success:
```python
assert button.isEnabled() is True
assert "actualizados" in feedback.text().lower()
```
On error the button must re-enable and show the error.

- [ ] **Step 2: Trigger tests**

Verify coordinator runs:
- once on startup after critical health passes;
- after ACTUALIZAR completes;
- on ACTUALIZAR RESULTADOS.

Verify ACTUALIZAR RESULTADOS does not call `analyze_slate()`.

- [ ] **Step 3: Implement with existing FunctionWorker/thread pool**

On finish, refresh Jugadores, Combinaciones and ACIERTOS HOY.

- [ ] **Step 4: Verify**

```bash
QT_QPA_PLATFORM=offscreen pytest tests/ui/test_history.py tests/ui/test_today.py tests/ui/test_settlement_triggers.py -v
pytest -q
```

- [ ] **Step 5: Commit**

```bash
git add src/mlb_hr/ui/history.py src/mlb_hr/ui/today.py src/mlb_hr/ui/main_window.py src/mlb_hr/app.py tests/ui/test_history.py tests/ui/test_today.py tests/ui/test_settlement_triggers.py
git commit -m "feat: refresh official results automatically"
```

## Plan 2 acceptance gate

```bash
pytest tests/test_daily_accuracy.py tests/test_settlement_coordinator.py -v
QT_QPA_PLATFORM=offscreen pytest tests/ui/test_history.py tests/ui/test_settlement_triggers.py -v
pytest -q
```

Stop and report before Plan 3.
