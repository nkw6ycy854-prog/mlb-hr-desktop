# MLB HR UI Redesign — Claude Code Execution Roadmap

> **For agentic workers:** REQUIRED: execute one plan at a time. Do not merge phases. Use TDD for every behavior change and stop after each plan for review.

**Goal:** Deliver the approved MLB HR desktop UI redesign without changing the predictive model V1.0.0, calibration, thresholds, holdout, feature math, or model package hash.

**Architecture:** Keep PySide6 and the existing service/domain layers. Replace the tabbed UI with a sidebar + `QStackedWidget`, add responsive reusable UI components, then implement combination fallback, multi-book best odds, history filters, settings/health checks, and finally native macOS/Windows verification.

**Tech Stack:** Python 3.13, PySide6 6.11.1, SQLite, DuckDB, The Odds API, pytest.

**Spec:** `docs/superpowers/specs/2026-08-26-mlb-hr-ui-redesign-design.md`

## Non-negotiable constraints

- MODEL VERSION remains `V1.0.0`.
- Do not edit training code, calibration, thresholds, holdout logic, frozen manifests, or predictive feature math.
- Odds remain post-model and MUST NOT alter probability, classification, or ranking.
- FanDuel remains the reference market used by the existing model ledger unless a later explicitly approved design changes that accounting rule.
- Invalid / `NOT_ELIGIBLE` predictions are never used to fabricate picks or combinations.
- macOS and Windows must share the same source behavior.
- Every button must have visible progress, success, error, or unavailable feedback.
- No completion claim without fresh test/build evidence.

## Execution order

1. `2026-08-26-mlb-hr-ui-foundation-today.md`
2. `2026-08-26-mlb-hr-combination-fallback.md`
3. `2026-08-26-mlb-hr-best-odds.md`
4. `2026-08-26-mlb-hr-history-redesign.md`
5. `2026-08-26-mlb-hr-settings-health.md`
6. `2026-08-26-mlb-hr-native-verification.md`

Each plan must end green before starting the next. Commit after every task exactly as the plan says. If a plan exposes an architectural mismatch, stop and report it instead of stacking speculative fixes.
