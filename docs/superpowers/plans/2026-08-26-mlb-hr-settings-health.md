# MLB HR AJUSTES + Startup Health Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild AJUSTES into General/Cuotas/IA/Sistema sections and add a lightweight startup health check that prevents silent empty screens when critical runtime data is missing.

**Architecture:** Keep configuration persistence in SQLite/keyring. Add a testable `HealthService` independent from widgets, run it asynchronously at startup, and expose provider/self-test actions through settings with explicit feedback.

**Tech Stack:** Python 3.13, PySide6, keyring, zoneinfo, SQLite, pytest.

**Spec:** `docs/superpowers/specs/2026-08-26-mlb-hr-ui-redesign-design.md`

## Global Constraints

- Startup health must not block the GUI thread.
- Critical: model package, Statcast, DB.
- MLB provider failure is visible/retryable but does not erase locally available history/settings.
- No API key is a neutral `SIN API`, not a critical failure.
- Full self-test remains manual.

---

### Task 1: Add testable lightweight health service

**Files:**
- Create: `src/mlb_hr/services/health.py`
- Create: `tests/test_health.py`

**Interfaces:**
```python
@dataclass(frozen=True)
class HealthItem:
    key: str
    label: str
    state: str   # OK | WARNING | ERROR | NOT_CONFIGURED
    detail: str

@dataclass(frozen=True)
class HealthReport:
    items: tuple[HealthItem, ...]
    critical_ok: bool
```

`HealthService(service, paths, store).run() -> HealthReport`

- [ ] **Step 1: Write failing tests**

Test:
- missing Statcast -> ERROR and `critical_ok=False`;
- release-ready model + Statcast + DB -> OK;
- no odds provider -> `NOT_CONFIGURED`, not critical;
- DB `SELECT 1` failure -> ERROR.

- [ ] **Step 2: Verify RED**

- [ ] **Step 3: Implement**

Checks:
```python
model_ok = service.package.release_ready and service.package.manifest.model_version == "V1.0.0"
statcast_ok = service.analytics.has_data()
db_ok = store.healthcheck()  # add in Task 2
odds_state = "OK" if service.odds is not None else "NOT_CONFIGURED"
```

Do not perform a long MLB network call in this service. Startup provider availability is updated by the existing first `ACTUALIZAR`; this keeps startup deterministic and fast.

- [ ] **Step 4: Verify**

```bash
pytest tests/test_health.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/mlb_hr/services/health.py tests/test_health.py
git commit -m "feat: add lightweight runtime health service"
```

---

### Task 2: Add DB healthcheck and persisted UI settings

**Files:**
- Modify: `src/mlb_hr/storage/sqlite.py`
- Modify: `tests/test_storage.py`

**Interfaces:**
- `SQLiteStore.healthcheck() -> bool`
- state keys:
  - `default_stake`
  - `timezone_name`
  - `ui_density`
  - `ai_provider`
  - `ai_review_enabled`

- [ ] **Step 1: Write failing DB health test**

```python
assert st.healthcheck() is True
```

- [ ] **Step 2: Verify RED**

- [ ] **Step 3: Implement**

```python
def healthcheck(self) -> bool:
    try:
        with self.connection() as con:
            return con.execute("SELECT 1").fetchone()[0] == 1
    except Exception:
        return False
```

No schema migration is needed for app_state keys.

- [ ] **Step 4: Verify**

```bash
pytest tests/test_storage.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/mlb_hr/storage/sqlite.py tests/test_storage.py
git commit -m "feat: add database health check"
```

---

### Task 3: Rebuild settings sections and save feedback

**Files:**
- Rewrite: `src/mlb_hr/ui/settings.py`
- Create: `tests/ui/test_settings.py`

**Interfaces:**
- General: stake, timezone, UI density.
- Cuotas: Odds API key, FanDuel reference enabled/read-only, best-price enabled/read-only, US books label, PROBAR CONEXIÓN.
- IA: provider selector, API key fields, review enabled, PROBAR IA.
- Sistema: runtime labels + open data folder + self-test.

- [ ] **Step 1: Write failing settings tests**

Assert section titles exist and saving:
```python
widget.stake.setCurrentText("$25")
widget.timezone.setCurrentText("America/Santo_Domingo")
widget.density.setCurrentText("Compacta")
widget.save()
assert store.get_state("default_stake") == 25.0
assert store.get_state("timezone_name") == "America/Santo_Domingo"
assert store.get_state("ui_density") == "compact"
assert "Guardado" in widget.feedback.text()
```

- [ ] **Step 2: Verify RED**

- [ ] **Step 3: Implement section cards**

Use `QFrame#card` with `QFormLayout` inside each section.
Do not rely on modal dialogs for normal success; use persistent inline feedback label.
Keep modal only for exceptional errors.

Use `zoneinfo.available_timezones()` to populate timezone choices and ensure current value remains selectable.

- [ ] **Step 4: Verify**

```bash
pytest tests/ui/test_settings.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/mlb_hr/ui/settings.py tests/ui/test_settings.py
git commit -m "feat: reorganize application settings"
```

---

### Task 4: Add working odds connection test, AI test, data-folder button, and full self-test button

**Files:**
- Modify: `src/mlb_hr/providers/odds.py`
- Modify: `src/mlb_hr/ui/settings.py`
- Modify: `src/mlb_hr/services/bootstrap.py`
- Extend: `tests/ui/test_settings.py`
- Extend: `tests/test_odds_provider.py`

- [ ] **Step 1: Write failing provider test**

Add `OddsProvider.test_connection()` that calls MLB events endpoint and returns `ProviderResult[bool]`.
Fake client test must assert `True` on valid list response and a structured failure on exception.

- [ ] **Step 2: Verify RED**

- [ ] **Step 3: Implement buttons**

- `PROBAR CONEXIÓN`: run provider test in `FunctionWorker`; button disabled while running; feedback `Conexión OK` or error.
- `PROBAR IA`: build the currently selected provider using the entered key/model and execute one minimal review request; show provider/model/error in feedback. Do not alter predictive results.
- `ABRIR CARPETA DE DATOS`: `QDesktopServices.openUrl(QUrl.fromLocalFile(str(paths.data_dir)))`.
- `EJECUTAR SELF-TEST`: run `run_self_test(require_runtime_data=True)` in worker and show PASS/FAIL plus failed check names.

Inject `paths` / service-builder dependencies into `SettingsWidget` rather than discovering global paths inside button handlers.

- [ ] **Step 4: Verify**

```bash
pytest tests/ui/test_settings.py tests/test_odds_provider.py -v
pytest -q
```

- [ ] **Step 5: Commit**

```bash
git add src/mlb_hr/providers/odds.py src/mlb_hr/ui/settings.py src/mlb_hr/services/bootstrap.py tests/ui/test_settings.py tests/test_odds_provider.py
git commit -m "feat: make settings diagnostics actionable"
```

---

### Task 5: Run health check asynchronously at startup and show critical banner

**Files:**
- Modify: `src/mlb_hr/app.py:7-42`
- Modify: `src/mlb_hr/ui/main_window.py`
- Modify: `src/mlb_hr/ui/today.py`
- Create: `tests/ui/test_startup_health.py`

**Interfaces:**
- `MainWindow.apply_health_report(report)`
- `TodayWidget.show_health_failure(report)`
- Buttons: `ABRIR AJUSTES`, `REINTENTAR`

- [ ] **Step 1: Write failing health UI tests**

Given `critical_ok=False`, assert:
- explicit failure banner visible;
- `ABRIR AJUSTES` switches to settings;
- `REINTENTAR` calls supplied retry callback;
- ranking table is not silently presented as empty failure state.

- [ ] **Step 2: Verify RED**

- [ ] **Step 3: Implement startup worker**

In `app.py`, after showing the window:
```python
def start_health():
    worker = FunctionWorker(HealthService(service, paths, store).run)
    window._health_worker = worker
    worker.signals.finished.connect(window.apply_health_report)
    worker.signals.error.connect(window.apply_health_error)
    QThreadPool.globalInstance().start(worker)

QTimer.singleShot(50, start_health)
```

Only trigger automatic `today.refresh()` after critical health passes. If health fails, let user open settings or retry.

- [ ] **Step 4: Verify**

```bash
pytest tests/ui/test_startup_health.py -v
pytest -q
```

- [ ] **Step 5: Commit**

```bash
git add src/mlb_hr/app.py src/mlb_hr/ui/main_window.py src/mlb_hr/ui/today.py src/mlb_hr/services/health.py tests/ui/test_startup_health.py
git commit -m "feat: add startup runtime health gate"
```
