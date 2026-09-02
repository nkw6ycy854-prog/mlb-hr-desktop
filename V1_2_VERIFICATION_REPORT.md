# V1_2_VERIFICATION_REPORT — MLB HR Desktop V1.2.0

Full implementation of the approved V1.2.0 plan (9 phases) plus native
verification on both platforms from one shared RC_SHA.

## RC_SHA

```
34b34914dad8c34752a31e9720c4579783e1400a
```

(`ef9227f` from V1.1.0 was the base; `2f8cdec` was the first V1.2.0 RC
candidate — superseded by this commit, a CI-only fix discovered during
Windows verification, see "Deviations" below. Both macOS and Windows were
built/verified from this exact final commit.)

## Versions (frozen constraints — unchanged)

| | |
|---|---|
| APP VERSION | `1.2.0` |
| MODEL VERSION | `V1.0.0` (unchanged) |
| MODEL HASH | `4f3296dcbe4fb932a6ebb7e0cabde9c5b33234be2ec1da07f29d10e7b50975ab` (unchanged) |

## Predictive regression — MANDATORY GATE — PASS, zero tolerance

Two independent guards (`tests/test_v1_2_predictive_regression.py`), both green throughout every phase:

1. **Deterministic fixture**: `AnalysisService._rank_key`, `presentation.practical_status()`, and `CombinationEngine.build()` — the real, unmodified functions — run against a fixed golden input, asserting exact HR%/ranking/classification/confidence/practical_status/eligible/combination legs. Established once at the start of Phase 1, never edited since.
2. **Frozen-file guard**: `git diff --stat` against the `v1.1.0` tag for the entire frozen predictive core (`model/`, `calibration/`, `features/`, `uncertainty/`, `quality_gates/`, `integrity/`, `combinations/engine.py`, `odds/market.py`, `postgame/engine.py`, `domain/enums.py`, `domain/models.py`, `domain/math.py`, `services/analysis.py`, `resources/bundled_model/`, `model_packages/V1.0.0/`) — confirmed **empty diff** at RC_SHA. `analysis.py` was never touched.

## Test results

| | |
|---|---|
| Full suite | **354 tests, PASS** |
| Predictive regression guard | **PASS** (0 diff) |
| Rollback test (real `v1.1.0` code via `git worktree`, subprocess) | **PASS** |
| `scripts/ui_smoke.py` | **PASS** (all 12 checks) |
| SELF-TEST (source, frozen model staged) | **PASS** — `app_version=1.2.0`, `bundled_model_version=V1.0.0`, hash exact match, `statcast_runtime_available=true` (1164 parquet, local cache) |

New V1.2.0 test coverage (112 tests in dedicated new files, plus updates to existing suites for the new sidebar/page structure):

| File | Tests | Covers |
|---|---|---|
| `tests/test_canonical_combinations.py` | 9 | canonical_key/slate_scope_key formula, supersession, cross-slate isolation, backfill idempotency |
| `tests/test_favorites.py` | 15 | CRUD, real DELETE, save→remove→save, results-with-settlement join, operational_status reconciliation |
| `tests/test_settlement_status_persistence.py` | 2 | Centro de Estado's "Último settlement" persistence |
| `tests/test_status_center.py` | 8 | 7-component aggregation, conservative global state |
| `tests/test_v1_2_predictive_regression.py` | 5 | the mandatory gate itself |
| `tests/test_v1_2_rollback.py` | 1 | real V1.1.0 code vs V1.2.0-migrated DB |
| `tests/test_visual_state*.py` | 15 | approved visual_state mapping + icons/tooltips |
| `tests/ui/test_combinations_page.py` | 11 | COMBINACIONES page, focus restoration |
| `tests/ui/test_components_v1_2.py` | 6 | DetailSidePanel, FeedbackButton |
| `tests/ui/test_games_page.py` | 13 | POR PARTIDOS page, batting order, EXPANDIR/COLAPSAR |
| `tests/ui/test_history_favorites.py` | 6 | HISTORIAL ★ FAVORITOS tab |
| `tests/ui/test_status_center_panel.py` | 3 | Centro de Estado panel |
| `tests/ui/test_today_v1_2.py` | 15 | HOY dashboard/filters/search/favorites |
| `tests/ui/test_v1_2_responsive.py` | 3 | new pages at the 4 established breakpoints |

## Migration applied

`005_favorites_and_canonical_combinations.sql` — additive, backward-compatible, non-destructive. New `favorites` table (`UNIQUE(player_id, game_pk)`, immutable snapshot columns, no soft-delete column); 4 new bookkeeping columns on `combinations` (`canonical_key`, `slate_scope_key`, `is_canonical`, `superseded_by`). `SCHEMA_VERSION` 4→5. Backfill runs as an idempotent Python post-step inside `SQLiteStore.migrate()` (too complex for raw SQL — needs a `predictions.game_time` join), verified against real pre-V1.2.0 data via the existing v3-origin migration test.

**Rollback**: verified for real, not assumed — a DB migrated by V1.2.0's current code, opened by the actual `v1.1.0` tag's own `storage/sqlite.py` (via `git worktree` + a genuinely separate subprocess): `migrate()` is a safe no-op (v1.1.0 only knows migrations 1-4, sees them all already applied), all real read/write methods keep working, zero data loss, V1.2.0's own data (favorites, canonical bookkeeping) survives untouched.

## macOS native verification — PASS

- Build: `MLB_HR_MODEL_PACKAGE=model_packages/V1.0.0 scripts/build_macos.sh` from RC_SHA.
- Re-signed with `com.apple.security.cs.disable-library-validation` (a known, already-established requirement for this build pipeline on this machine — without it the self-test binary is killed at load time by macOS Library Validation; not a V1.2.0-specific issue).
- `native_smoke.py --require-runtime-data`: `app_version=1.2.0`, `model_version=V1.0.0`, hash exact match, `statcast_runtime_available=true` (1164 parquet), self-test PASS, `passed: true`.
- **Manual checklist**: not yet confirmed by you on this real machine — see "Pending" below.

## Windows Native Gate — PASS

| | |
|---|---|
| Run | [33674109855](https://github.com/nkw6ycy854-prog/mlb-hr-desktop/actions/runs/33674109855) |
| `headSha` | `34b34914dad8c34752a31e9720c4579783e1400a` (exact RC_SHA match) |
| Conclusion | **success** |

`full-release-manifest.json`: `app_version=1.2.0`, `model_version=V1.0.0`, hash exact match, `release_commit` exact match, `self_test_pass=true`, `statcast_runtime_available=true`, `statcast_parquet_count=2` (CI fixture-sized, same shape already accepted for V1.1.0).

## Deviations / findings during this phase

1. **CI bug found and fixed** (workflow-config only, no application code): the first RC_SHA candidate (`2f8cdec`) failed Windows CI's `pytest -q` step — `git diff --stat v1.1.0 ...` and `git worktree add ... v1.1.0` both failed with "bad revision"/"invalid reference". Root cause: `actions/checkout@v6`'s default shallow clone doesn't fetch tags at all. Confirmed by reproducing the identical failure locally with `git clone --depth=1 --no-tags`, and confirming `fetch-depth: 0` + `fetch-tags: true` resolves it. Fixed in `.github/workflows/windows-native.yml`, which produced the final RC_SHA (`34b3491`) that both platforms were actually built/verified from. The app itself was never affected — my local macOS build process doesn't run the full test suite, only Windows CI's own `pytest -q` step hit this.
2. **"Última actualización" has no DESACTUALIZADO staleness indicator.** No existing "whole-slate last-refresh staleness" threshold was found anywhere in V1.1.0 (only a narrower, unrelated per-odds-quote freshness threshold exists via `CONFIG.odds_warning`/`odds_fresh`) — the plan explicitly forbids inventing a new threshold, so this specific sub-requirement was left undone rather than guessed at.
3. **REPROGRAMADO (rescheduled game) auto-detection is not implemented.** No reliable signal exists in currently-available data to distinguish "this favorite's game_pk was reassigned by MLB" from "this game simply isn't in today's schedule" (the normal case for every already-resolved favorite) — implementing a heuristic risked false positives on every historical favorite. POSTPONED/CANCELLED *are* correctly detected from real `GameState` signals.
4. **Current-vs-snapshot dual display (section 22) is partial.** HOY's favorite button correctly reflects live saved/not-saved state, and HISTORIAL's ★ FAVORITOS detail shows the immutable SNAPSHOT AL GUARDAR plus RESULTADO FINAL — but a live side-by-side ACTUAL vs SNAPSHOT block inside the HOY detail panel itself (for a still-in-slate favorited player) was not built, given time constraints across the full 9-phase scope.

## Final `git status --short`

```
?? .mlb_hr_runtime_fix_backup_20260821_200017/
?? .release_tmp_windows/
?? .windows_release_backup_20260823_162743.tar.gz
?? MLB_HR_V1_1_Claude_Plan_Pack.zip
?? MLB_HR_V1_1_Claude_Plan_Pack/
?? PATCH_NOTES.md
?? WINDOWS_RELEASE_NOTES.txt
?? build.bak-release-20260827_105418/
?? model_packages/V1.0.0/
?? model_packages/release_review.json
?? release_artifacts/
?? release_windows_v1/
```

No tracked-file drift. Untracked entries are pre-existing local artifacts from earlier in the engagement, untouched by this phase.

## Status

**`release_ready = true`** for the implementation and both native gates.

**Pending before a public release**: your manual confirmation of the macOS UI checklist above (the one verification step in this entire plan that requires human hands, consistent with every prior native-verification phase in this engagement). No tag was created, no GitHub Release was published — matching the plan's own scope (native verification only, release closure was never requested as part of this execution).
