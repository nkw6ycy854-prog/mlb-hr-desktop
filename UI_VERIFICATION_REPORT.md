# MLB HR UI Redesign — Verification Report

**Date (UTC):** 2026-08-27T00:11:27Z
**Git commit at time of source verification:** `98bd16c047d0342db6a96966694dd8366aea7b9b`
**Model version:** V1.0.0
**Model package hash:** `4f3296dcbe4fb932a6ebb7e0cabde9c5b33234be2ec1da07f29d10e7b50975ab`
**Model release_ready:** True

This report covers the **source verification** stage of the native-verification plan
(`docs/superpowers/plans/2026-08-26-mlb-hr-native-verification.md`, Task 3). Native
macOS and Windows results are appended below once run.

## Source verification

### 1. UI test suite

```
QT_QPA_PLATFORM=offscreen pytest tests/ui -v
```

Result: **60 passed** in 1.31s. 0 failures.

```
tests/ui/test_components.py .                                            [  1%]
tests/ui/test_history.py .............                                   [ 23%]
tests/ui/test_main_window.py .                                           [ 25%]
tests/ui/test_presentation.py ........                                   [ 38%]
tests/ui/test_settings.py ................                               [ 65%]
tests/ui/test_startup_health.py ............                             [ 85%]
tests/ui/test_style_contract.py .                                        [ 86%]
tests/ui/test_today.py .......                                           [ 98%]
tests/ui/test_ui_smoke_contract.py .                                     [100%]
```

### 2. Full source test suite

```
pytest -q
```

Result: **124 passed** in 5.98s. 0 failures.

This includes every model/training/threshold/calibration/holdout/storage/UI test in
the repository — none were modified to make this pass, and none regressed across
Plans 1–6.

### 3. Source UI smoke script

```
QT_QPA_PLATFORM=offscreen python3 scripts/ui_smoke.py
```

Result:

```json
{"sidebar_navigation": true, "today_render": true, "history_render": true, "settings_render": true, "resize_large": true, "resize_compact": true, "passed": true}
```

Exit code: 0.

The script instantiates a real `MainWindow` (sidebar + `QStackedWidget` + HOY/HISTORIAL/AJUSTES)
against a freshly migrated temporary SQLite store, clicks through all three sidebar
destinations, and resizes the window at 1180×760 (large) and 820×700 (compact) —
confirming both sizes report the requested dimensions with no unhandled exception.

## Native verification

Native macOS and Windows results are recorded separately below as each stage
completes, per the plan's requirement that neither platform's PASS be claimed
without direct build/run evidence.

### macOS

_Pending — see Task 4 of the native-verification plan._

### Windows

_Pending — see Task 5 of the native-verification plan. Requires the `Windows Native Gate`
GitHub Actions workflow (`workflow_dispatch`), which requires pushing the verified
commit to a remote branch and triggering the run — both actions require explicit
user confirmation before being performed._
