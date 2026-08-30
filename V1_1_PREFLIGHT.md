# V1.1.0 Plan 1 — Preflight Report

## 1. V1.0.1 prerequisite

- `git rev-parse HEAD` at preflight time: `87c16d127fca4b72d8350cff545352879fcba0dc`
  (`fix: hotfix v1.0.1 - regression gate + hardened CI for missing Statcast`), already on `origin/main`.
- `pyproject.toml` / `src/mlb_hr/__init__.py`: app version `1.0.1`.
- `.github/workflows/windows-native.yml` requires `--require-runtime-data` /
  `statcast_runtime_available=true` via a dedicated FULL-package assembly + gate step
  before a run can pass.
- Last Windows Native Gate run on `87c16d1`: run `33256007902`, `conclusion: success`,
  including the new "Assemble and gate Windows FULL package" step.
- `pytest -q` on that commit: 168 passed, exit 0.

Prerequisite satisfied. V1.1.0 work begins on top of it.

## 2. Frozen model verification

- Dev-baseline resource used by local tests/self-test (`src/mlb_hr/resources/bundled_model/model_manifest.json`):
  `model_version=DEV-BASELINE-0.1` — intentionally not the release model; unaffected by this plan.
- Release model package (`model_packages/V1.0.0/model_manifest.json`), the one staged into native builds:
  - `model_version`: `V1.0.0`
  - `package_hash`: `4f3296dcbe4fb932a6ebb7e0cabde9c5b33234be2ec1da07f29d10e7b50975ab`
  - Matches the frozen hash required by the V1.1 spec and roadmap exactly.
- `git status --short` over `training/`, `holdout/`, `src/mlb_hr/calibration/`, `data/training/`: clean, no drift.

## 3. Symbol map (plan → repo)

| Plan symbol | Real location |
|---|---|
| `TodayWidget` | `src/mlb_hr/ui/today.py:19` |
| `HistoryWidget` | `src/mlb_hr/ui/history.py:38` |
| `SettingsWidget` | `src/mlb_hr/ui/settings.py:54` |
| `SlateResult` | `src/mlb_hr/domain/models.py:292` |
| `PredictionCard` | `src/mlb_hr/domain/models.py:262` |
| `AnalysisService.analyze_slate` | `src/mlb_hr/services/analysis.py:74` |
| `timezone_name` (persisted) | `store.get_state("timezone_name", ...)` in `settings.py`/`history.py` |
| existing time formatting | `format_local_time(dt, timezone_name)` in `src/mlb_hr/ui/presentation.py:55` |
| `GameState` | `src/mlb_hr/domain/enums.py:77-81` (`PREGAME`/`LIVE`/`FINAL`) |
| `ModelClassification` | `src/mlb_hr/domain/enums.py:13-18` (includes `NOT_ELIGIBLE`) |
| raw per-game lineup/roster data | `GameContext` — `src/mlb_hr/domain/models.py:83-100` (`away_lineup`/`home_lineup`, `away_starter`/`home_starter`, `state`, `game_time`) |

## 4. Mismatches found (approved resolutions from the user)

1. **Doc paths**: plan docs shipped inside `MLB_HR_V1_1_Claude_Plan_Pack/`, not at the
   root paths the roadmap references. Resolved by copying into
   `docs/superpowers/specs/`, `docs/superpowers/plans/`, and `CLAUDE_V1_1_ROADMAP.md`
   at repo root (this commit). The pack directory stays untracked.
2. **`SlateResult` had no per-game raw context.** `analyze_slate()` builds a rich
   `hydrated: list[GameContext]` list internally but never returned it — only
   post-pipeline aggregates (`cards`, counts) survived. Resolved per user's explicit
   direction: add an additive `game_contexts: tuple[GameContext, ...] = ()` field to
   `SlateResult`, populated from the existing `hydrated` list, with zero changes to
   probability/classification/ranking/integrity/exclusion logic.
3. **Timezone bug in `today.py`**: `p.game_time.astimezone()` (no explicit zone) uses
   OS-local time instead of the configured `timezone_name`, inconsistent with
   `history.py`'s correct use of `format_local_time`. Resolved via `GameTimeService`
   in this plan.

## 5. Model verification snapshot (frozen)

```
MODEL VERSION: V1.0.0
MODEL HASH: 4f3296dcbe4fb932a6ebb7e0cabde9c5b33234be2ec1da07f29d10e7b50975ab
```
