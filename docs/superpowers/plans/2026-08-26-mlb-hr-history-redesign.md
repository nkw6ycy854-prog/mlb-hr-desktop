# MLB HR HISTORIAL Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build separate Jugadores and Combinaciones history views with game times, combinable filters, row details, and summaries recalculated from the current filtered set.

**Architecture:** Add a read-only history service that converts SQLite rows into UI-facing records and applies filters without modifying stored evidence. Keep SQL storage methods simple; filtering and summary math live in the service for deterministic tests.

**Tech Stack:** Python 3.13, SQLite, zoneinfo, PySide6, pytest.

**Spec:** `docs/superpowers/specs/2026-08-26-mlb-hr-ui-redesign-design.md`

## Global Constraints

- Historical records are immutable evidence; UI filtering never rewrites predictions or settlements.
- Display timezone comes from `app_state["timezone_name"]`, defaulting to the local system timezone identifier when usable, otherwise `UTC`.
- Player status uses the same practical mapping as HOY.
- Period filter uses `game_time` when available, otherwise `created_at`.

---

### Task 1: Expose complete player and combination history rows

**Files:**
- Modify: `src/mlb_hr/storage/sqlite.py`
- Modify: `tests/test_storage.py`

**Interfaces:**
- `history_prediction_rows(limit: int = 2000) -> list[sqlite3.Row]`
- `history_combination_rows(limit: int = 1000) -> list[sqlite3.Row]`
- `prediction_rows_by_ids(ids: list[str]) -> dict[str, sqlite3.Row]`

- [ ] **Step 1: Write failing storage tests**

Player query must expose:
`game_time`, `classification`, `final_probability`, `reference_stake`, `odds_at_prediction`, settlement result, and paper P/L amount.

Combination query must expose:
`filter_status`, active combination settlement fields, legs JSON, estimated odds, created time.

- [ ] **Step 2: Verify RED**

- [ ] **Step 3: Implement SQL**

For player rows extend the current join with:
```sql
LEFT JOIN paper_bankroll_events pe
  ON pe.prediction_id=p.prediction_id
 AND pe.event_type IN ('WIN','LOSS')
```

For combinations:
```sql
SELECT c.*, cs.status combination_status, cs.won, cs.profit_loss
FROM combinations c
LEFT JOIN combination_settlements cs
  ON cs.combination_id=c.combination_id AND cs.active=1
ORDER BY c.created_at DESC
LIMIT ?
```

- [ ] **Step 4: Verify**

```bash
pytest tests/test_storage.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/mlb_hr/storage/sqlite.py tests/test_storage.py
git commit -m "feat: expose history read models from sqlite"
```

---

### Task 2: Add deterministic history filtering and summary service

**Files:**
- Create: `src/mlb_hr/services/history.py`
- Create: `tests/test_history_service.py`

**Interfaces:**
```python
@dataclass(frozen=True)
class HistoryFilter:
    period: str = "ALL"        # TODAY | 7D | 30D | ALL
    status: str = "ALL"        # ALL | RECOMMENDED | WATCH | NO_FILTER
    result: str = "ALL"        # ALL | HR | NO_HR | PENDING
```

Produce:
- `player_records(filter, now) -> list[PlayerHistoryRecord]`
- `combination_records(filter, now) -> list[CombinationHistoryRecord]`
- `summarize_players(records) -> dict`
- `summarize_combinations(records) -> dict`

- [ ] **Step 1: Write failing filter tests**

Test combinations such as:
```python
HistoryFilter(period="30D", status="RECOMMENDED", result="HR")
```
and assert only matching rows remain.

Test game-time formatting input stays timezone-aware and no DB mutations occur.

- [ ] **Step 2: Verify RED**

- [ ] **Step 3: Implement records + filters**

Map classification:
- PRIMARY/SECONDARY -> RECOMMENDED
- WATCH -> WATCH
- NO_BET -> NO_FILTER

Map player result:
- actual_hr_binary == 1 -> HR
- actual_hr_binary == 0 -> NO_HR
- otherwise -> PENDING

For combination status:
- `filter_status=QUALIFIED` -> RECOMMENDED
- `FALLBACK` -> NO_FILTER
- settled won=1 -> HR-equivalent `WIN`
- settled won=0 -> `LOSS`
- absent -> PENDING

Calculate player summary:
```python
resolved = [r for r in records if r.result in {"HR", "NO_HR"}]
hits = sum(r.result == "HR" for r in resolved)
pnl = sum(r.pnl or 0 for r in records)
staked = sum(r.reference_stake for r in resolved if r.odds_at_prediction is not None)
```
`hit_rate = hits / len(resolved)` and `roi = pnl/staked` when denominators are nonzero.

- [ ] **Step 4: Verify**

```bash
pytest tests/test_history_service.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/mlb_hr/services/history.py tests/test_history_service.py
git commit -m "feat: add filtered history read service"
```

---

### Task 3: Build Jugadores / Combinaciones internal views and filters

**Files:**
- Rewrite: `src/mlb_hr/ui/history.py`
- Create: `tests/ui/test_history.py`

**Interfaces:**
- `HistoryWidget.mode_stack`
- `HistoryWidget.players_btn`, `combinations_btn`
- period buttons: TODAY, 7D, 30D, ALL
- status combo: Todos / Recomendado / Vigilar / No cumple filtro
- result combo: Todos / HR / No HR / Pendiente

- [ ] **Step 1: Write failing UI tests**

Assert:
- defaults to Jugadores;
- clicking Combinaciones changes stack;
- selecting 30D + Recomendado + HR constructs the expected `HistoryFilter`;
- player table headers exactly include `Fecha`, `Hora`, `Jugador`, `HR%`, `Estado`, `Cuota`, `Resultado`.

- [ ] **Step 2: Verify RED**

- [ ] **Step 3: Implement**

Use a top segmented `QButtonGroup` for mode and period.
Use compact `QComboBox` values for state/result to avoid layout collisions.
Connect every filter change to `refresh()`.

- [ ] **Step 4: Verify**

```bash
pytest tests/ui/test_history.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/mlb_hr/ui/history.py tests/ui/test_history.py
git commit -m "feat: redesign history with separate filtered views"
```

---

### Task 4: Add local game time, row detail, and dynamic summaries

**Files:**
- Modify: `src/mlb_hr/ui/history.py`
- Modify: `src/mlb_hr/ui/presentation.py`
- Extend: `tests/ui/test_history.py`
- Extend: `tests/ui/test_presentation.py`

- [ ] **Step 1: Write failing timezone/detail tests**

With timezone `America/Santo_Domingo`, assert a known UTC game time renders at the expected local clock time.
For combination rows assert `Inicio` equals the earliest leg game time and detail lists each leg with individual game time.

- [ ] **Step 2: Verify RED**

- [ ] **Step 3: Implement timezone helper**

```python
from zoneinfo import ZoneInfo

def format_local_time(dt, timezone_name: str) -> str:
    if dt is None:
        return "—"
    return dt.astimezone(ZoneInfo(timezone_name)).strftime("%-I:%M %p")
```

On Windows, avoid platform-specific `%-I`; use a portable helper that strips a leading zero from `%I:%M %p`.

Render summary cards from the filtered service results only.

- [ ] **Step 4: Verify**

```bash
pytest tests/ui/test_history.py tests/ui/test_presentation.py -v
pytest -q
```

- [ ] **Step 5: Commit**

```bash
git add src/mlb_hr/ui/history.py src/mlb_hr/ui/presentation.py tests/ui/test_history.py tests/ui/test_presentation.py
git commit -m "feat: add game times and dynamic history summaries"
```
