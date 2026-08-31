# V1_1_VERIFICATION_REPORT — V1.1.0 Plan 4 (Native Verification)

Source, macOS, and Windows verification of V1.1.0 from one release-candidate
commit, per `docs/superpowers/plans/2026-08-30-mlb-hr-v1-1-native-verification.md`.
This plan does **not** tag or publish a release — it stops here for human approval.

## RC_SHA

```
ef9227f45bc92456866cfee9111cd44f195d4060
```

Commit `ef9227f` — "release: bump APP VERSION to 1.1.0". Both the macOS build
and the Windows Native Gate ran from this exact commit.

## Versions (frozen constraints)

| | Value |
|---|---|
| APP VERSION | `1.1.0` |
| MODEL VERSION | `V1.0.0` (unchanged) |
| MODEL HASH | `4f3296dcbe4fb932a6ebb7e0cabde9c5b33234be2ec1da07f29d10e7b50975ab` (unchanged) |

Confirmed identical on macOS, on Windows, and in source (`mlb_hr.__version__`).
No training/calibration/threshold/holdout/feature/probability/classification/
ranking/integrity-gate/lineup-confirmation/LIVE-FINAL-exclusion code was
touched in this plan.

## Task 1 — Extended source UI smoke

`scripts/ui_smoke.py` now asserts all 9 plan-required content checks
(`today_top15`, `today_by_games`, `canonical_time`, `history_players`,
`history_combinations`, `history_hits_today`, `update_results_control`,
`settings`, `functional_audit`) plus `sidebar_navigation`/`resize_large`/
`resize_compact`, using deterministic fake data (crafted `SlateResult`/
`GameContext` fixtures, a fake store, and an injected fake `settlement_runner`)
— no live network, no real DB.

RED confirmed first (`KeyError: 'today_top15'`), then GREEN.
Commits: [b1d6969](../../commit/b1d6969) (unrelated pre-existing test fixture
fix, see Deviations), [e70770b](../../commit/e70770b) (Task 1 deliverable).

## Task 2 — APP VERSION → 1.1.0

`src/mlb_hr/__init__.py` and `pyproject.toml` bumped `1.0.1` → `1.1.0`.
MODEL VERSION untouched (grep-confirmed only reference remains in
`src/mlb_hr/services/health.py`, unmodified). `pysidedeploy.spec`'s
auto-generated local build drift (icon path, python_path, qt.modules —
same category of drift seen and restored during the V1.0.0 release closure)
was restored via `git restore` before verification/push.

Full suite green (236 tests) before commit. Commit: `ef9227f` = **RC_SHA**.

## Task 3 — Source verification from RC_SHA

All run fresh at `ef9227f` with a clean tracked tree:

| Check | Result |
|---|---|
| `git status --short` (tracked files) | clean |
| `pytest tests/ui -q` | 118 passed |
| `pytest -q` (full suite) | 236 passed |
| `python3 scripts/ui_smoke.py` | `"passed": true` (all 12 keys true) |
| Functional audit | see below |

**Deviation — functional audit script:** Task 3 Step 5 references
`python3 scripts/generate_functional_audit.py`, which does not exist in this
repo and is not assigned to any task's file list in the plan. Rather than
invent an unscoped script, I satisfied the verification intent using the
plan's own shown check against the existing, already-approved
`FUNCTIONAL_AUDIT_V1_1.md` (Plan 3, commit `f702ddd`, closed by you on
2026-08-30).

**Deviation — literal grep false-positive:** the plan's literal
`grep -E "BLOCKED|UNKNOWN" FUNCTIONAL_AUDIT_V1_1.md` matches one line — but
it's the legend defining the vocabulary ("`Estado`: `PASS` / `FAIL→FIXED` /
`COSMÉTICO→REMOVIDO` / `BLOCKED`."), not an actual finding. No table row's
`Estado` cell is `BLOCKED` or `UNKNOWN` anywhere in the document. My
`ui_smoke.py`'s `functional_audit` check excludes that legend line before
matching, and reports `true`.

## Task 4 — macOS native verification

**Build:** `MLB_HR_MODEL_PACKAGE=model_packages/V1.0.0 scripts/build_macos.sh`
from RC_SHA — succeeded, produced `build/MLB HR.app`.

**Blocking issue found and fixed:** the built app's `--self-test` binary was
killed immediately (SIGKILL, zero output) both via `scripts/native_smoke.py`
and run directly, with and without this session's own Bash sandbox disabled
(ruling that out as the cause). Root cause, confirmed by testing a trivial
ad-hoc-signed binary in the same environment (which ran fine, ruling out a
blanket "adhoc binaries are blocked" policy): macOS Library Validation
rejecting the bundle's Qt/Python dylibs at load time because the main
executable's ad-hoc signature lacked the
`com.apple.security.cs.disable-library-validation` entitlement —
a known failure mode for `pyside6-deploy`-built bundles. Fixed by re-signing
with `codesign --force --deep --sign - --entitlements ...` (that entitlement
plus `com.apple.security.cs.allow-unsigned-executable-memory`), with your
explicit approval before running it. This is a local build/signing step, not
a source change — nothing in `src/` was touched.

**Native smoke** (`build_reports/macos.json`), after the re-sign:

| Check | Result |
|---|---|
| `platform_correct` | true |
| `artifact_self_test_pass` | true (`self_test_returncode: 0`) |
| `app_version` | `1.1.0` |
| `bundled_model_version` | `V1.0.0` |
| `bundled_model_hash` | matches frozen hash exactly |
| `statcast_runtime_available` | true (`parquet_count: 1164`, this Mac's own cache) |
| all import/isolation/migration checks | true |
| `passed` | **true** |

**Manual checklist** — confirmed all PASS by you on the running `build/MLB HR.app`:
TOP 15, POR PARTIDOS, players grouped per team, pending-lineup card, correct
DR (Santo Domingo) time, ACIERTOS HOY, ACTUALIZAR RESULTADOS, existing
settings/actions, resize with no overlap.

## Task 5 — Windows Native Gate from same RC_SHA

Pushed RC_SHA to `origin/main`, triggered "Windows Native Gate" on `main`
(with your explicit confirmation before push/trigger).

| | |
|---|---|
| Run | [33355025968](https://github.com/nkw6ycy854-prog/mlb-hr-desktop/actions/runs/33355025968) |
| `headSha` | `ef9227f45bc92456866cfee9111cd44f195d4060` (exact RC_SHA match) |
| Conclusion | **success** |

Artifact (`full-release-manifest.json`, the FULL package with bundled
Statcast runtime data — distinct from the bare `MLB-HR-Windows-App.zip`,
which self-tests without `--require-runtime-data` and correctly shows
`statcast_runtime_available: false` for *that* variant alone):

```json
{
  "app_version": "1.1.0",
  "model_version": "V1.0.0",
  "model_hash": "4f3296dcbe4fb932a6ebb7e0cabde9c5b33234be2ec1da07f29d10e7b50975ab",
  "release_commit": "ef9227f45bc92456866cfee9111cd44f195d4060",
  "self_test_pass": true,
  "statcast_parquet_count": 2,
  "statcast_runtime_available": true
}
```

`release_commit` matches RC_SHA exactly. `statcast_parquet_count: 2` is a
CI-scoped fixture-sized bundle (artifact literally named
`MLB-HR-Windows-FULL-CI-FIXTURE.zip`), not this Mac's full local Statcast
cache — it satisfies the plan's literal bar (`parquet_count > 0`,
`statcast_runtime_available = true`), matching the shape already accepted in
the V1.0.0 Windows Native Gate precedent.

## macOS vs Windows parity

Both built from `ef9227f`. Both report `app_version=1.1.0`,
`model_version=V1.0.0`, identical model hash, `self_test_pass=true`,
Statcast runtime available. Source behavior is identical by construction
(same commit, no platform-specific source branches touched in V1.1.0).

## Final git status

```
$ git status --short
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
?? release_windows_v1/
```

No tracked-file drift. The untracked entries are pre-existing local
artifacts/backups from earlier in the engagement (not created by Plan 4,
not touched by it).

## Deviations summary

1. `scripts/generate_functional_audit.py` (referenced in plan Task 3 Step 5)
   does not exist — verification intent satisfied via the plan's own grep
   check against the existing, approved `FUNCTIONAL_AUDIT_V1_1.md` instead of
   inventing an unscoped script.
2. That literal grep matches the document's legend line (defines the
   `Estado` vocabulary, including the word "BLOCKED") as a false positive —
   `ui_smoke.py`'s `functional_audit` check excludes it; zero actual findings
   are `BLOCKED`/`UNKNOWN`.
3. Found and fixed one pre-existing, unrelated flaky test:
   `tests/ui/test_history.py`'s `_hits_today_store()` fixture computed
   `game_time` as a `datetime.now(utc)`-relative offset, which could land in
   a different Santo Domingo calendar day than `HistoryWidget.refresh()`'s
   own `now()`-derived `local_date` during the daily UTC/local day-boundary
   window — intermittently failing 2 tests depending on wall-clock time.
   Fixed by anchoring the fixture to local noon instead (test-only, no
   `src/` change, its own commit `b1d6969`, separate from Task 1's actual
   deliverable).
4. macOS build artifact needed re-signing with a library-validation-disabling
   entitlement to run at all in this environment (see Task 4) — a local
   packaging/signing step, done with your explicit approval, no source change.

## Status

**Not tagged, not published.** Per the plan, this stops here for your review
and approval before any further action (tagging, GitHub Release, or Plan 5
if one exists).
