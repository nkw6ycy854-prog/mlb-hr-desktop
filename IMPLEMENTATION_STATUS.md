# Implementation Status

Status date: 2026-08-17

## What is implemented

The source implementation now covers the locked desktop architecture end to end:

- PySide6/Qt Widgets application structure with HOY / HISTORIAL / AJUSTES.
- SQLite operational database, migrations, prediction revisions, odds snapshots, model/user ledgers, combination settlement, post-lock invalidation and audit events.
- Parquet + DuckDB analytical store for historical Statcast queries and derived evidence.
- MLB, Statcast, NOAA and odds provider adapters with normalized source responses, bounded HTTP behavior and provenance/freshness handling.
- Optional AUTO_FREE AI reviewer adapters (Groq -> Gemini -> OpenRouter -> Ollama when configured). AI review occurs only after deterministic probability generation and before the market layer; it cannot alter HR probability.
- Confirmed-lineup/confirmed-starter integrity gates and started-game exclusion.
- Batter/pitcher history, hierarchical shrinkage/reliability, expected PA, starter exposure, bullpen mixture structure, park/weather structure, split/similar/BvP/profile-change hooks.
- Deterministic per-PA probability engine, full-game PA integration, calibration adapter, uncertainty distribution, OOD/stability/confidence and local model critic.
- Quality gates separating model classification from market action.
- FanDuel odds as a strict post-prediction layer; manual odds are disabled for unqualified UI candidates.
- 2-Man / 3-Man / long-shot combination engine with no forced third leg.
- Official-MLB deterministic postgame reconciliation, result versioning, suspension/postponement handling, PA/starter/bullpen exposure tracking and prospective P/L settlement.
- Offline training CLI: Statcast bootstrap, leakage-controlled training table, walk-forward 2022/2023/2024 validation, baselines, calibration selection, ablation, stable threshold procedure, candidate freeze, one-shot locked 2025 holdout and final release review.
- Native build scripts, bundled runtime resources/model staging, artifact-level `--self-test`, and native smoke-report tooling for macOS and Windows.
- Pinned Python/dependency configuration and pyside6-deploy/Nuitka spec.

## Validation performed in the current execution environment

Passed:

- `python -m compileall -q src training scripts`
- `python -m training.cli --help`
- `pytest -q` -> **17 tests passed**
- editable source-package import was previously verified with build isolation disabled.

The automated tests currently cover, among other invariants:

- HR probability math and American-odds math.
- Development package is not release-ready.
- SQLite revisions and latest-pregame behavior.
- Confirmed scratch/starter invalidation.
- Odds change market outputs without changing model probability.
- Postponed games do not become misses.
- PBP/box HR reconciliation behavior.
- Deterministic inference/uncertainty.
- Unvalidated package cannot emit real recommendations.
- Combinations do not force legs.
- PA distribution support.
- Threshold selection does not optimize sportsbook ROI.
- AUTO_FREE AI fallback does not mutate the probability payload.
- Initial candidate does not double-count an unvalidated Matchup Score gate.
- Bundled migrations and bundled model manifest resolve through package resources for standalone builds.

## What has NOT been truthfully completed here

### 1. Historical Statcast validation has not been run

This container cannot currently download the full 2019-2025 Statcast history because its Python/container network environment cannot resolve/install/fetch the required external data/dependencies reliably. Therefore this execution has **not** run:

- the full 6+ season bootstrap,
- the real 2022/2023/2024 walk-forward metrics,
- feature ablation on the complete dataset,
- final calibration selection from real folds,
- final #2 numerical quality thresholds,
- the single official locked 2025 holdout.

The included development model remains `release_ready=false`, and the application intentionally blocks real recommendations from it.

### 2. Native `.app` and `.exe` have not been built in this Linux environment

The Technical Lock requires official artifacts to be built and tested natively on their target operating systems. This execution environment is Linux, so it cannot honestly certify:

- macOS 13+ ARM64 `.app`,
- Windows 10/11 x64 `.exe`,
- native Keychain/Credential Locker behavior,
- final native GUI smoke checks.

The repository contains the native build scripts and smoke-report tooling required to finish those hard release gates on the correct machines.

### 3. MODEL V1.0 is not yet validated or proven profitable

No `V1.0 READY` claim is made. No profitability guarantee is made. The source is designed so that the final release flag cannot be promoted solely because the software runs; predictive and native release gates must also pass.

## Candidate-model discipline

The first reconstructable historical candidate intentionally begins with a smaller core feature set whose pre-game history can be generated consistently from the Statcast cache. Advanced architecture modules are implemented as structures/hooks, but they are not allowed to re-enter a frozen candidate merely because they exist. Ablation/out-of-sample evidence decides whether Zone, Similar Pitchers, BvP, detailed park/weather, advanced bullpen effects and related modules survive into the actual V1 package.

The current Matchup Score is not used as an independent candidate gate until it has independent validation; otherwise it would double-count probability strength.

## Next release sequence

1. Run the Statcast bootstrap on a network-capable development machine.
2. Build the chronological training table.
3. Run walk-forward validation/ablation/calibration.
4. Freeze the candidate and its thresholds/config/hash.
5. Run the 2025 locked holdout once.
6. If predictive holdout passes, build/test native macOS and Windows artifacts.
7. Run `finalize-release` only when both native hard reports pass.

Until step 7 succeeds, the safe status is **SOURCE IMPLEMENTED / V1 RELEASE NOT YET VALIDATED**.
