# MLB HR Combination Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Always produce the four combination cards when enough integrity-valid players exist, while clearly distinguishing official combinations from fallback high-risk combinations.

**Architecture:** Extend the combination domain object with an explicit filter status. `CombinationEngine` first tries the existing official PRIMARY/SECONDARY policy; if insufficient, it falls back to the best available `WATCH`/`NO_BET` candidates while excluding `NOT_ELIGIBLE`. Persist the status for history.

**Tech Stack:** Python 3.13, dataclasses, SQLite, pytest.

**Spec:** `docs/superpowers/specs/2026-08-26-mlb-hr-ui-redesign-design.md`

## Global Constraints

- Never use `NOT_ELIGIBLE`.
- Never reclassify a player to make a combination pass.
- PRIMARY/SECONDARY-only combinations are `QUALIFIED`.
- Any combination requiring WATCH or NO_BET is `FALLBACK`.
- BEST 3-MAN retains the official “at least one PRIMARY” rule only for QUALIFIED mode.
- Do not change prediction probabilities or quality-gate thresholds.

---

### Task 1: Add explicit combination filter status to domain model

**Files:**
- Modify: `src/mlb_hr/domain/enums.py`
- Modify: `src/mlb_hr/domain/models.py`
- Modify: `tests/test_gates_combos.py`

- [ ] **Step 1: Write failing enum/model test**

```python
from mlb_hr.domain.enums import CombinationFilterStatus

def test_combination_filter_status_values_are_stable():
    assert CombinationFilterStatus.QUALIFIED.value == "QUALIFIED"
    assert CombinationFilterStatus.FALLBACK.value == "FALLBACK"
```

- [ ] **Step 2: Verify RED**

```bash
pytest tests/test_gates_combos.py::test_combination_filter_status_values_are_stable -v
```

- [ ] **Step 3: Implement**

```python
class CombinationFilterStatus(StrEnum):
    QUALIFIED = "QUALIFIED"
    FALLBACK = "FALLBACK"
```

Add to `Combination` before fields with defaults:
```python
filter_status: CombinationFilterStatus
```

- [ ] **Step 4: Run tests and update every constructor compile error**

```bash
pytest tests/test_gates_combos.py -v
```

Expected: failures only where constructors still need the new field; update them explicitly rather than giving the field a misleading default.

- [ ] **Step 5: Commit**

```bash
git add src/mlb_hr/domain/enums.py src/mlb_hr/domain/models.py tests/test_gates_combos.py
git commit -m "feat: add combination filter status"
```

---

### Task 2: Implement qualified-first, fallback-second combination selection

**Files:**
- Modify: `src/mlb_hr/combinations/engine.py`
- Modify: `tests/test_gates_combos.py`

- [ ] **Step 1: Add failing behavior tests**

Create a small card factory and assert:
```python
def test_best2_falls_back_when_only_watch_and_no_bet_exist():
    cards = [card("A", .16, ModelClassification.WATCH),
             card("B", .14, ModelClassification.NO_BET)]
    combo = {c.kind: c for c in CombinationEngine().build(cards)}["BEST_2_MAN"]
    assert combo.filter_status == CombinationFilterStatus.FALLBACK
    assert {leg.player_name for leg in combo.legs} == {"A", "B"}

def test_qualified_combo_wins_when_enough_qualified_legs_exist():
    cards = [card("A", .18, ModelClassification.PRIMARY),
             card("B", .16, ModelClassification.SECONDARY),
             card("C", .15, ModelClassification.WATCH)]
    combo = {c.kind: c for c in CombinationEngine().build(cards)}["BEST_2_MAN"]
    assert combo.filter_status == CombinationFilterStatus.QUALIFIED
    assert all(leg.classification in {ModelClassification.PRIMARY, ModelClassification.SECONDARY} for leg in combo.legs)

def test_not_eligible_is_never_used_for_fallback():
    cards = [card("A", .15, ModelClassification.WATCH),
             card("X", .30, ModelClassification.NOT_ELIGIBLE)]
    assert "BEST_2_MAN" not in {c.kind for c in CombinationEngine().build(cards)}
```

- [ ] **Step 2: Verify RED**

```bash
pytest tests/test_gates_combos.py -v
```

- [ ] **Step 3: Implement minimal engine policy**

Use two pools:
```python
valid = [c for c in cards if c.prediction.classification != ModelClassification.NOT_ELIGIBLE]
qualified = [c for c in valid if c.prediction.classification in {ModelClassification.PRIMARY, ModelClassification.SECONDARY}]
```

For each kind:
1. attempt official pool;
2. if no result, attempt valid pool;
3. set `filter_status` from the pool used.

Refactor `_best` to accept:
```python
filter_status: CombinationFilterStatus
require_primary: bool
```

Add warning `FALLBACK_UNQUALIFIED_LEGS` for fallback combinations.

- [ ] **Step 4: Verify GREEN**

```bash
pytest tests/test_gates_combos.py -v
pytest -q
```

- [ ] **Step 5: Commit**

```bash
git add src/mlb_hr/combinations/engine.py tests/test_gates_combos.py
git commit -m "feat: build fallback combinations from best valid players"
```

---

### Task 3: Persist combination filter status

**Files:**
- Create: `migrations/004_combination_filter_status.sql`
- Modify: `src/mlb_hr/storage/sqlite.py`
- Modify: `tests/test_storage.py`

- [ ] **Step 1: Write failing migration/persistence test**

```python
def test_combination_filter_status_persists(tmp_path):
    st = SQLiteStore(tmp_path/"db.sqlite", ROOT/"migrations")
    st.migrate()
    combo = make_combo(filter_status=CombinationFilterStatus.FALLBACK)
    st.save_combination(combo)
    with st.connection() as con:
        row = con.execute("SELECT filter_status FROM combinations WHERE combination_id=?", (combo.combination_id,)).fetchone()
    assert row["filter_status"] == "FALLBACK"
```

- [ ] **Step 2: Verify RED**

Expected: no `filter_status` column.

- [ ] **Step 3: Add migration**

```sql
ALTER TABLE combinations ADD COLUMN filter_status TEXT NOT NULL DEFAULT 'QUALIFIED';
```

Update `SCHEMA_VERSION = 4`, `save_combination()` column list and values.

- [ ] **Step 4: Verify**

```bash
pytest tests/test_storage.py -v
pytest -q
```

- [ ] **Step 5: Commit**

```bash
git add migrations/004_combination_filter_status.sql src/mlb_hr/storage/sqlite.py tests/test_storage.py
git commit -m "feat: persist combination filter status"
```

---

### Task 4: Render filter status and leg classifications in HOY

**Files:**
- Modify: `src/mlb_hr/ui/today.py`
- Extend: `tests/ui/test_today.py`

- [ ] **Step 1: Write failing render tests**

Assert the generated card contains:
- `✅ CUMPLE FILTRO` for QUALIFIED
- `⚠ NO CUMPLE FILTRO · ALTO RIESGO` for FALLBACK
- each leg name plus its classification.

- [ ] **Step 2: Verify RED**

- [ ] **Step 3: Implement**

For each combo card:
```python
qualified = combo.filter_status == CombinationFilterStatus.QUALIFIED
status_text = "✅ CUMPLE FILTRO · RECOMENDADA" if qualified else "⚠ NO CUMPLE FILTRO · ALTO RIESGO"
```

Render one line per leg:
```text
Aaron Judge · PRIMARY
Juan Soto · WATCH
```

If fewer than N valid analyzed players exist, show:
`NO HAY SUFICIENTES JUGADORES ANALIZADOS` rather than “no combination solid enough”.

- [ ] **Step 4: Verify**

```bash
pytest tests/ui/test_today.py -v
pytest -q
```

- [ ] **Step 5: Commit**

```bash
git add src/mlb_hr/ui/today.py tests/ui/test_today.py
git commit -m "feat: label qualified and fallback combinations"
```
