# Specification Traceability

This map connects the locked design blocks to the source implementation. It is not a claim that every advanced feature survives final ablation; it identifies where each architecture requirement is implemented or enforced.

| Lock / stage | Main implementation areas | Key enforcement |
|---|---|---|
| #1 FanDuel / Odds | `providers/odds.py`, `odds/market.py`, `services/analysis.py` | Odds fetched only for already-qualified model candidates; odds never enter features/inference. |
| #2 NO BET | `quality_gates/engine.py`, training threshold policy | Hard eligibility, probability/confidence/OOD/critic gates; final numbers come from validation. |
| #3 Walk-forward | `training/modeling.py`, `training/pipeline.py` | Fixed chronological 2022/2023/2024 development folds; Brier/calibration/Log Loss; baselines. |
| #4 Economic tracking | `storage/sqlite.py`, `postgame/`, history UI | $10 reference stake model ledger, P/L/ROI/bankroll tracking, user bets separated. |
| #5 Model V1 freeze | `model/package.py`, `training/pipeline.py`, `release_review.py` | Frozen manifest/hash, calibration/threshold config, one-shot holdout, `release_ready`. |
| #6 Similar Pitchers | `storage/analytics.py`, `features/engine.py` | Similar-profile signal supported; candidate inclusion remains ablation-controlled. |
| #7 Zone Split | `storage/analytics.py`, `features/engine.py` | Zone evidence/reliability hooks and strict candidate exclusion when not validated. |
| #8 Rookies / small sample | `features/reliability.py`, `features/engine.py`, training transforms | Hierarchical shrinkage/effective-sample/reliability behavior. |
| #9 Profile Change | `storage/analytics.py`, `features/engine.py` | Profile-change signal structure with reliability; candidate inclusion versioned. |
| #10 Park / Environment | `features/park.py`, `providers/noaa.py`, `services/analysis.py` | Venue/roof/weather separation, neutral degradation, no odds coupling. |
| #11 Expected PA | `features/pa.py`, training PA distributions | PA probability distribution by lineup slot; game HR integrated over PA distribution. |
| #12 Starter Exposure | `features/exposure.py`, `storage/analytics.py` | Starter BF/survival and PA-specific starter exposure. |
| #13 Bullpen | `features/bullpen.py`, `features/engine.py` | Availability-weighted reliever mixture structure; workload affects availability, not arbitrary performance bonus. |
| #14 Uncertainty | `uncertainty/engine.py` | P10/P50/P90, stability, confidence, OOD/component reliability; deterministic scenarios. |
| #15 Quality Gates | `quality_gates/critic.py`, `quality_gates/engine.py` | Critical fail exclusion, local critic, no forced picks, market separated. |
| #16 Postgame | `postgame/engine.py`, `services/settlement.py`, SQLite settlement tables | MLB PBP/box reconciliation, suspension/postponement/void, result versions, no AI. |
| #17 Release Criteria | `training/release_review.py`, `scripts/native_smoke.py`, tests | Predictive holdout + native macOS + native Windows hard checks before release flag. |
| Technical Lock | `pyproject.toml`, `pysidedeploy.spec`, storage/providers/services structure | Python 3.13, PySide6, SQLite, Parquet/DuckDB, keyring, native builds, no auto-training. |
| Interface Lock | `ui/today.py`, `ui/history.py`, `ui/settings.py`, `ui/main_window.py` | HOY/HISTORIAL/AJUSTES; decision-only normal UI; player side panel; simple combinations. |

## Hard invariant tests

The `tests/` directory includes explicit checks for key release invariants such as odds isolation, unvalidated-model blocking, confirmed-scratch invalidation, immutable/latest prediction behavior, postgame edge cases, no forced combination legs, deterministic uncertainty and non-ROI threshold selection.
