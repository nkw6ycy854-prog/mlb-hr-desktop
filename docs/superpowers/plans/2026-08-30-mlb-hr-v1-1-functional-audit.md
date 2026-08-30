# MLB HR V1.1.0 Functional Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove every visible interactive control has real behavior, feedback and coverage, and eliminate unexplained empty screens.

**Architecture:** Build an explicit UI control inventory test around existing widgets. Fix only failures discovered by the inventory or targeted manual audit; no unrelated refactors.

**Tech Stack:** PySide6, QtTest, pytest, Markdown audit report.

**Spec:** `docs/superpowers/specs/2026-08-30-mlb-hr-v1-1-design.md`

## Global Constraints

- No predictive/model changes.
- Do not hide dead controls to pass the audit.
- Every audited control ends `PASS` or `BLOCKED`; release requires zero `BLOCKED`.
- No empty content area without a reason string/action where appropriate.

---

### Task 1: Create machine-readable control inventory

**Files:**
- Create: `tests/ui/control_inventory.py`
- Create: `tests/ui/test_control_inventory.py`
- Modify: `src/mlb_hr/ui/today.py`
- Modify: `src/mlb_hr/ui/history.py`
- Modify: `src/mlb_hr/ui/settings.py`
- Modify: `src/mlb_hr/ui/main_window.py`

**Interfaces:**
```python
@dataclass(frozen=True)
class ControlContract:
    screen: str
    object_name: str
    control_type: str
    expected_handler: str
    requires_loading: bool
    requires_feedback: bool
```

Inventory minimum:
- HOY: update, top15, por-partidos, ver-todos, copy-pick;
- HISTORIAL: jugadores, combinaciones, aciertos-hoy, period/state/result filters, actualizar-resultados;
- AJUSTES: stake preset, custom stake, timezone, density, save, odds test, AI test/toggle, open-data, self-test;
- health retry/open settings when visible.

- [ ] **Step 1: Write inventory with stable objectName values**

If an audited control has no `objectName`, add one in production UI.

- [ ] **Step 2: Write failing existence/handler tests**

Instantiate each screen and assert the control exists and its expected callable/interaction is wired. Prefer QSignalSpy/click behavior over unreliable binding-level receiver counts.

- [ ] **Step 3: Run RED**

```bash
QT_QPA_PLATFORM=offscreen pytest tests/ui/test_control_inventory.py -v
```

- [ ] **Step 4: Fix only missing names/connections**

Do not redesign unrelated UI.

- [ ] **Step 5: Run GREEN**

```bash
QT_QPA_PLATFORM=offscreen pytest tests/ui/test_control_inventory.py -v
```

- [ ] **Step 6: Commit**

```bash
git add tests/ui/control_inventory.py tests/ui/test_control_inventory.py src/mlb_hr/ui/today.py src/mlb_hr/ui/history.py src/mlb_hr/ui/settings.py src/mlb_hr/ui/main_window.py
git commit -m "test: inventory all interactive controls"
```

---

### Task 2: Verify loading/feedback for async actions

**Files:**
- Create: `tests/ui/test_action_feedback.py`
- Modify relevant UI files only where tests expose a failure.

Actions:
- ACTUALIZAR;
- ACTUALIZAR RESULTADOS;
- PROBAR CONEXIÓN;
- PROBAR IA;
- SELF-TEST;
- health REINTENTAR.

- [ ] **Step 1: Parameterized lifecycle tests**

For each action, assert:
```python
action.trigger()
assert control.isEnabled() is False
assert loading_phrase in feedback.text()
fake_worker.finish_success(...)
assert control.isEnabled() is True
assert success_phrase in feedback.text()
```

Failure path:
```python
fake_worker.finish_error("boom")
assert control.isEnabled() is True
assert "boom" in feedback.text()
```

- [ ] **Step 2: Run tests**

```bash
QT_QPA_PLATFORM=offscreen pytest tests/ui/test_action_feedback.py -v
```

- [ ] **Step 3: Fix lifecycle failures with existing worker/signals pattern**

Never leave a control disabled after error.

- [ ] **Step 4: Verify**

```bash
QT_QPA_PLATFORM=offscreen pytest tests/ui/test_action_feedback.py -v
pytest -q
```

- [ ] **Step 5: Commit**

```bash
git add tests/ui/test_action_feedback.py src/mlb_hr/ui
git commit -m "fix: enforce action feedback lifecycle"
```

---

### Task 3: Audit empty states

**Files:**
- Create: `tests/ui/test_empty_states.py`
- Modify relevant UI files only for failing cases.

Required scenarios:
- HOY no schedule;
- HOY waiting lineups;
- HOY no pregame;
- HOY runtime unavailable;
- POR PARTIDOS provider error;
- HISTORIAL no records;
- ACIERTOS HOY no hits;
- CUOTAS no quote/API not configured.

- [ ] **Step 1: Write one fixture/test per state**

Each must assert a non-empty explanatory label and no unexplained blank table/container.

- [ ] **Step 2: Run/fix**

```bash
QT_QPA_PLATFORM=offscreen pytest tests/ui/test_empty_states.py -v
```

- [ ] **Step 3: Commit**

```bash
git add tests/ui/test_empty_states.py src/mlb_hr/ui
git commit -m "fix: explain every empty UI state"
```

---

### Task 4: Audit synchronous controls and persistence

**Files:**
- Create: `tests/ui/test_sync_controls.py`
- Modify: `src/mlb_hr/ui/settings.py`
- Modify: `src/mlb_hr/ui/history.py`
- Modify: `src/mlb_hr/ui/today.py`

Must test:
- TOP 15 / POR PARTIDOS;
- VER TODOS;
- COPIAR PICK feedback;
- history mode switches;
- period/state/result filters;
- stake preset;
- custom stake;
- timezone save;
- density save;
- AI review toggle save;
- GUARDAR confirmation.

- [ ] **Step 1: Write direct interaction tests**

Example timezone persistence:
```python
settings.timezone.setCurrentText("America/Santo_Domingo")
settings.save()
assert store.get_state("timezone_name") == "America/Santo_Domingo"
```

Then refresh Today/History and assert canonical time equality.

- [ ] **Step 2: Run/fix**

```bash
QT_QPA_PLATFORM=offscreen pytest tests/ui/test_sync_controls.py -v
pytest -q
```

- [ ] **Step 3: Commit**

```bash
git add tests/ui/test_sync_controls.py src/mlb_hr/ui/settings.py src/mlb_hr/ui/history.py src/mlb_hr/ui/today.py
git commit -m "test: verify synchronous UI controls"
```

---

### Task 5: Generate functional audit matrix

**Files:**
- Create: `FUNCTIONAL_AUDIT_V1_1.md`
- Create: `scripts/generate_functional_audit.py`
- Create: `tests/ui/test_functional_audit_report.py`

Report columns:
`Pantalla | Control | Signal/handler | Efecto | Loading | Feedback | Test | Estado`

- [ ] **Step 1: Generate report from inventory**

Every control must map to automated test evidence. Generator exits non-zero if any state is `UNKNOWN` or `BLOCKED`.

- [ ] **Step 2: Report contract test**

```python
text = Path("FUNCTIONAL_AUDIT_V1_1.md").read_text()
assert "| BLOCKED |" not in text
assert "| UNKNOWN |" not in text
for contract in CONTROL_INVENTORY:
    assert contract.object_name in text
```

- [ ] **Step 3: Generate and verify**

```bash
python3 scripts/generate_functional_audit.py
QT_QPA_PLATFORM=offscreen pytest tests/ui/test_functional_audit_report.py -v
QT_QPA_PLATFORM=offscreen pytest tests/ui -v
pytest -q
```

- [ ] **Step 4: Commit**

```bash
git add FUNCTIONAL_AUDIT_V1_1.md scripts/generate_functional_audit.py tests/ui/test_functional_audit_report.py
git commit -m "docs: certify v1.1 functional controls"
```

## Plan 3 acceptance gate

Require zero `BLOCKED`, zero `UNKNOWN`, all UI tests green and full suite green. Stop and report before Plan 4.
