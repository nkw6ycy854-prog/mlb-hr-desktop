# MLB HR Native UI Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:verification-before-completion. Do not claim the UI release is complete from source tests alone.

**Goal:** Prove the redesigned UI works in source mode and native macOS/Windows builds without runtime-data regressions or widget collisions.

**Architecture:** Add a source UI smoke script plus native self-test assertions, then build each target through the existing native build paths. Preserve model V1.0.0 and require runtime Statcast availability.

**Tech Stack:** pytest, PySide6 offscreen, Nuitka/PySide deployment, GitHub Actions Windows runner.

**Spec:** `docs/superpowers/specs/2026-08-26-mlb-hr-ui-redesign-design.md`

## Global Constraints

- Do not rebuild/retrain model.
- Native build must load model V1.0.0.
- Runtime Statcast must be detected.
- No Windows success claim until GitHub Windows Native Gate is green.
- No macOS success claim until local native smoke exits 0.

---

### Task 1: Add source UI smoke test

**Files:**
- Create: `scripts/ui_smoke.py`
- Create: `tests/ui/test_ui_smoke_contract.py`

- [ ] **Step 1: Write failing contract test**

Assert `scripts/ui_smoke.py` creates QApplication offscreen, instantiates MainWindow with a temporary store/fake service, navigates all three pages, resizes at 1180×760 and 820×700, and exits nonzero on exception.

- [ ] **Step 2: Verify RED**

- [ ] **Step 3: Implement smoke script**

The script must print JSON with:
```json
{
  "sidebar_navigation": true,
  "today_render": true,
  "history_render": true,
  "settings_render": true,
  "resize_large": true,
  "resize_compact": true,
  "passed": true
}
```

- [ ] **Step 4: Verify**

```bash
QT_QPA_PLATFORM=offscreen python3 scripts/ui_smoke.py
pytest tests/ui/test_ui_smoke_contract.py -v
```

- [ ] **Step 5: Commit**

```bash
git add scripts/ui_smoke.py tests/ui/test_ui_smoke_contract.py
git commit -m "test: add desktop UI smoke verification"
```

---

### Task 2: Extend native smoke report with UI source contract and runtime health

**Files:**
- Modify: `scripts/native_smoke.py`
- Modify: `src/mlb_hr/selftest.py`
- Extend: `tests/test_selftest_runtime_data.py`

- [ ] **Step 1: Write failing checks**

Require self-test details to expose:
- model version;
- model hash;
- Statcast availability/count;
- SQLite;
- UI import;
- runtime paths.

- [ ] **Step 2: Verify RED**

- [ ] **Step 3: Implement**

Add `ui_import` check by importing `MainWindow`, `TodayWidget`, `HistoryWidget`, `SettingsWidget`.
Keep runtime-data requirement behind existing `--require-runtime-data`.

- [ ] **Step 4: Verify**

```bash
pytest tests/test_selftest_runtime_data.py -v
pytest -q
```

- [ ] **Step 5: Commit**

```bash
git add scripts/native_smoke.py src/mlb_hr/selftest.py tests/test_selftest_runtime_data.py
git commit -m "test: extend native runtime UI checks"
```

---

### Task 3: Run complete source verification

- [ ] **Step 1: Run all UI tests**

```bash
QT_QPA_PLATFORM=offscreen pytest tests/ui -v
```

Expected: 0 failures.

- [ ] **Step 2: Run full suite**

```bash
pytest -q
```

Expected: 0 failures.

- [ ] **Step 3: Run source UI smoke**

```bash
QT_QPA_PLATFORM=offscreen python3 scripts/ui_smoke.py
```

Expected: JSON `"passed": true`.

- [ ] **Step 4: Record results in `UI_VERIFICATION_REPORT.md`**

Include commands, timestamps, pass counts, git commit, model version, and model hash.

- [ ] **Step 5: Commit report**

```bash
git add UI_VERIFICATION_REPORT.md
git commit -m "docs: record UI source verification"
```

---

### Task 4: Build and verify macOS native application

- [ ] **Step 1: Stage approved model**

Use the repository's existing release staging process; verify resulting manifest is model `V1.0.0`.

- [ ] **Step 2: Build**

```bash
rm -rf build
bash scripts/build_macos.sh
```

Expected: exit 0 and `build/MLB HR.app` exists.

- [ ] **Step 3: Native smoke**

```bash
python3 scripts/native_smoke.py \
  --artifact "$PWD/build/MLB HR.app" \
  --expected-model-hash "4f3296dcbe4fb932a6ebb7e0cabde9c5b33234be2ec1da07f29d10e7b50975ab" \
  --require-runtime-data \
  --output build_reports/macos_ui_redesign.json
```

Expected: passed true.

- [ ] **Step 4: Manual resize/button checklist**

Open native app and verify:
- sidebar navigation;
- ACTUALIZAR feedback;
- Top 15 / VER TODOS;
- copy feedback;
- history mode + filters;
- settings save + self-test;
- 1180×760 and compact supported size with no overlap.

Record each as PASS/FAIL in the verification report.

- [ ] **Step 5: Commit only source/report changes, never build artifacts**

---

### Task 5: Build and verify Windows through GitHub Actions

- [ ] **Step 1: Push verified source branch**

Do not use stale release artifacts.

- [ ] **Step 2: Trigger existing `Windows Native Gate` workflow**

Use repository workflow exactly; do not invent a local cross-compile substitute.

- [ ] **Step 3: Confirm workflow green**

Record run ID, commit SHA, model version/hash, smoke result.

- [ ] **Step 4: Download artifact and run Windows SELF TEST**

Require runtime Statcast package in the portable distribution and verify self-test PASS.

- [ ] **Step 5: Final report**

Only after macOS + Windows pass, mark UI release candidate ready. If either fails, keep release status pending and return to the failing plan/task.
