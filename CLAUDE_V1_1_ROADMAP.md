# MLB HR Desktop V1.1.0 — Claude Code Execution Roadmap

> Execute one plan at a time. TDD for behavior changes. Stop after each plan for human review.

**Spec:** `docs/superpowers/specs/2026-08-30-mlb-hr-v1-1-design.md`

## Preflight hard gate

Before editing V1.1.0, confirm the branch already contains the verified V1.0.1 Windows Statcast/runtime-data hotfix. The Windows release gate must require real runtime Statcast. If this prerequisite is not true, STOP.

## Frozen predictive contract

- MODEL VERSION: `V1.0.0`
- MODEL HASH: `4f3296dcbe4fb932a6ebb7e0cabde9c5b33234be2ec1da07f29d10e7b50975ab`
- Do not edit training, calibration, thresholds, holdout, feature math, probability, classification, or ranking.
- Odds stay post-model.
- `NOT_ELIGIBLE` never becomes a pick to satisfy UI requirements.

## Execution order

1. `2026-08-30-mlb-hr-v1-1-time-and-game-view.md`
2. `2026-08-30-mlb-hr-v1-1-accuracy-and-settlement.md`
3. `2026-08-30-mlb-hr-v1-1-functional-audit.md`
4. `2026-08-30-mlb-hr-v1-1-native-verification.md`

Do not start the next plan until the previous plan is reviewed and approved.
