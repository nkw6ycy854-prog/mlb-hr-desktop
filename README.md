# MLB HR Desktop

Desktop, local-first MLB home-run probability application built from the locked V1 architecture. The repository separates fresh data acquisition, deterministic feature/model inference, uncertainty, quality gates, FanDuel market context, immutable ledgers, postgame reconciliation, and a simple PySide6 UI.

## Release status — important

The repository ships with `model_packages/development_baseline`, which is deliberately marked **`release_ready=false`**. It is a software-development package only. The production quality gate blocks it from becoming a real betting recommendation.

That is intentional. A real `MODEL V1.0` can only be promoted after the historical pipeline completes walk-forward validation, ablation, calibration/threshold selection, the single locked 2025 holdout, and native macOS + Windows release checks. The code never silently turns the development coefficients into a validated model.

## Official V1 technical targets

- CPython 3.13.x, 64-bit
- PySide6 / Qt Widgets desktop UI
- SQLite for mutable operational state and immutable audit revisions
- Parquet + DuckDB for large Statcast history
- macOS 13+ ARM64 and Windows 10/11 x64 native builds
- No paid API required for deterministic prediction/tracking core
- Optional The Odds API key for FanDuel prices; manual American odds fallback
- Optional AI review; probabilities do not require AI

## Development install

```bash
python3.13 -m venv .venv
source .venv/bin/activate                 # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev,build]"
```

Run the application:

```bash
mlb-hr
```

Run the UI with deterministic demo cards instead of live sources:

```bash
MLB_HR_DEMO=1 mlb-hr
```

On Windows PowerShell:

```powershell
$env:MLB_HR_DEMO="1"
mlb-hr
```

## Historical pipeline

The commands intentionally require explicit paths so the locked 2025 data cannot be opened accidentally through hidden defaults.

### 1. Incremental Statcast cache

```bash
python -m training.cli bootstrap-statcast \
  --parquet-dir data/statcast \
  --start 2019-03-20 \
  --end 2025-09-30
```

### 2. Build the leakage-controlled training table

```bash
python -m training.cli build-training-table \
  --parquet-glob 'data/statcast/**/*.parquet' \
  --output data/training/mlb_hr_training.parquet
```

### 3. Walk-forward validation / ablation / calibration selection

```bash
python -m training.cli validate \
  --training-table data/training/mlb_hr_training.parquet \
  --output-dir validation/v1
```

The development folds are fixed as:

- data through 2021 -> validate 2022
- data through 2022 -> validate 2023
- data through 2023 -> validate 2024

### 4. Freeze a candidate before touching 2025

```bash
python -m training.cli freeze-candidate \
  --training-table data/training/mlb_hr_training.parquet \
  --validation-dir validation/v1 \
  --candidate-dir model_packages/V1_candidate
```

This creates a candidate hash and `candidate_lock.json` with the 2025 holdout still unopened.

### 5. One official 2025 holdout run

```bash
python -m training.cli run-holdout-2025 \
  --training-table data/training/mlb_hr_training.parquet \
  --candidate-dir model_packages/V1_candidate \
  --output-dir holdout/v1
```

The command marks the holdout as opened **before** accessing the 2025 test set and refuses a second official run for the same candidate.

### 6. Final release only after native reports exist

```bash
python -m training.cli finalize-release \
  --reviewed-package holdout/v1/V1.0.0_predictive \
  --macos-report build_reports/macos.json \
  --windows-report build_reports/windows.json \
  --output-dir model_packages/V1.0.0
```

A package gets `release_ready=true` only if the predictive holdout passed and both native hard-check reports passed.

## Tests

```bash
pytest -q
python -m compileall -q src training scripts
python -m training.cli --help
```

The suite includes probability math, prediction revision/ledger behavior, no-stale confirmed-scratch invalidation, odds/model separation, deterministic uncertainty, postgame reconciliation, packaged-resource migrations/model loading, quality-gate blocking of unvalidated packages, combination rules, AI fallback isolation, and training-policy invariants.

## Packaging

Official artifacts are built **natively on each target OS**. The model package is staged into the executable resources before packaging. For the pre-release native gate, stage the reviewed predictive package produced by the 2025 holdout.

macOS:

```bash
export MLB_HR_MODEL_PACKAGE=holdout/v1/V1.0.0_predictive
bash scripts/build_macos.sh
python scripts/native_smoke.py \
  --artifact /path/to/MLBHR.app \
  --expected-model-hash <PACKAGE_HASH> \
  --output build_reports/macos.json
```

Windows PowerShell:

```powershell
$env:MLB_HR_MODEL_PACKAGE="holdout\v1\V1.0.0_predictive"
.\scripts\build_windows.ps1
py -3.13 scripts/native_smoke.py `
  --artifact path\to\MLBHR.exe `
  --expected-model-hash PACKAGE_HASH `
  --output build_reports\windows.json
```

`native_smoke.py` launches the **packaged artifact itself** with `--self-test`; it does not merely import the source tree. The report verifies packaged Python/dependencies, bundled migrations, model hash, odds isolation and postgame/runtime imports.

After both pre-release native reports pass, `finalize-release` creates the `release_ready=true` V1.0.0 package. Stage that final package and rebuild the distribution artifacts for delivery.

## Main product invariants

- Confirmed MLB lineup and confirmed starter are hard eligibility requirements.
- Started games are excluded from fresh recommendations unless explicitly requested.
- FanDuel odds are fetched/applied only after predictive qualification and never enter the predictive feature vector.
- Missing critical data never becomes an invented observation.
- Historical features use only information available before the prediction cutoff.
- Production loads a frozen model package and never auto-retrains after wins/losses.
- Pregame predictions, odds, and result revisions are auditable instead of silently overwritten.
- Postgame settlement is deterministic from official MLB game data; AI is not involved.
- The normal UI shows only decision-relevant fields; advanced diagnostics stay internal.

## What the current source does not claim

- It does **not** claim guaranteed accuracy or profit.
- The included development baseline is **not** a validated betting model.
- Advanced architecture modules may be reduced or excluded from V1 if walk-forward ablation does not prove incremental out-of-sample value.
