# MLB HR V1.1.0 Native Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:verification-before-completion. Do not claim V1.1.0 complete from source tests alone.

**Goal:** Verify V1.1.0 in source, macOS and Windows while proving the frozen model and Windows runtime Statcast contract remain intact.

**Architecture:** Extend smoke coverage for POR PARTIDOS, canonical time, ACIERTOS HOY and control audit, then build both native targets from one release-candidate commit.

**Tech Stack:** pytest, PySide6 offscreen, macOS native build, GitHub Windows Native Gate.

**Spec:** `docs/superpowers/specs/2026-08-30-mlb-hr-v1-1-design.md`

## Global Constraints

- APP target version: `1.1.0`.
- MODEL VERSION: `V1.0.0`.
- MODEL HASH: `4f3296dcbe4fb932a6ebb7e0cabde9c5b33234be2ec1da07f29d10e7b50975ab`.
- Windows MUST require runtime Statcast.
- macOS and Windows artifacts must come from one RC SHA.
- Do not create a public GitHub Release in this plan.

---

### Task 1: Extend source UI smoke

**Files:**
- Modify: `scripts/ui_smoke.py`
- Modify: `tests/ui/test_ui_smoke_contract.py`

Required JSON:
```json
{
  "today_top15": true,
  "today_by_games": true,
  "canonical_time": true,
  "history_players": true,
  "history_combinations": true,
  "history_hits_today": true,
  "update_results_control": true,
  "settings": true,
  "functional_audit": true,
  "resize_large": true,
  "resize_compact": true,
  "passed": true
}
```

- [ ] **Step 1: Add failing smoke contract assertions**
- [ ] **Step 2: Run RED**

```bash
QT_QPA_PLATFORM=offscreen pytest tests/ui/test_ui_smoke_contract.py -v
```

- [ ] **Step 3: Extend smoke using deterministic fake data, no live network**
- [ ] **Step 4: Verify**

```bash
QT_QPA_PLATFORM=offscreen python3 scripts/ui_smoke.py
pytest tests/ui/test_ui_smoke_contract.py -v
```

- [ ] **Step 5: Commit**

```bash
git add scripts/ui_smoke.py tests/ui/test_ui_smoke_contract.py
git commit -m "test: extend smoke coverage for v1.1"
```

---

### Task 2: Set APP VERSION 1.1.0

**Files:**
- Modify: `src/mlb_hr/__init__.py`
- Modify: `pyproject.toml`
- Modify existing build metadata only if proven to derive from app version.

- [ ] **Step 1: Verify frozen model first**
- [ ] **Step 2: Set app version to `1.1.0`; do not touch model version**
- [ ] **Step 3: Verify**

```bash
pytest -q -k "version or model or manifest"
pytest -q
```

- [ ] **Step 4: Commit**

```bash
git add src/mlb_hr/__init__.py pyproject.toml
git diff --name-only
git add -p
git commit -m "release: prepare MLB HR app v1.1.0"
```

Record full SHA as `RC_SHA`.

---

### Task 3: Source verification from RC_SHA

- [ ] **Step 1: Confirm SHA/tree**

```bash
git status --short
git rev-parse HEAD
```

- [ ] **Step 2: UI suite**

```bash
QT_QPA_PLATFORM=offscreen pytest tests/ui -v
```

- [ ] **Step 3: Full suite**

```bash
pytest -q
```

- [ ] **Step 4: UI smoke**

```bash
QT_QPA_PLATFORM=offscreen python3 scripts/ui_smoke.py
```

- [ ] **Step 5: Functional audit**

```bash
python3 scripts/generate_functional_audit.py
grep -E "BLOCKED|UNKNOWN" FUNCTIONAL_AUDIT_V1_1.md && exit 1 || true
```

Record exact output in `V1_1_VERIFICATION_REPORT.md`.

---

### Task 4: macOS native verification

- [ ] **Step 1: Build from RC_SHA with existing verified process**
- [ ] **Step 2: Native smoke with expected hash and `--require-runtime-data`**

Require:
```text
APP VERSION = 1.1.0
MODEL VERSION = V1.0.0
MODEL HASH = frozen hash
Statcast runtime = available
SELF TEST = PASS
```

- [ ] **Step 3: Manual checklist**

Verify:
- TOP 15;
- POR PARTIDOS;
- all players grouped per team;
- pending-lineup card;
- correct DR time;
- ACIERTOS HOY;
- ACTUALIZAR RESULTADOS;
- existing settings/actions;
- resize/no overlap.

Any FAIL blocks release.

---

### Task 5: Windows Native Gate from same RC_SHA

- [ ] **Step 1: Push RC_SHA and confirm workflow tests that SHA**
- [ ] **Step 2: Require FULL artifact**

Gate must assert:
```text
runtime_data/statcast exists
parquet_count > 0
SELF TEST --require-runtime-data = PASS
statcast_runtime_available = true
```

- [ ] **Step 3: Verify app/model versions and model hash**
- [ ] **Step 4: Record workflow run ID/result**

Workflow must be green on exact RC_SHA.

---

### Task 6: Final verification report

**Files:**
- Create/Modify: `V1_1_VERIFICATION_REPORT.md`

Include:
- RC_SHA;
- app version;
- model version/hash;
- source test counts;
- UI smoke;
- functional audit;
- macOS build/native smoke/manual checklist;
- Windows run/result;
- Windows Statcast parquet count/runtime availability;
- final `git status --short`;
- deviations.

Do not tag or publish. Stop for human approval.
