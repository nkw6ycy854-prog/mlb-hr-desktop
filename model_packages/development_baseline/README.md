# Development baseline — NOT a release model

`DEV-BASELINE-0.1` exists only to exercise application code paths before historical validation is run.

- `release_ready = false`
- coefficients/thresholds are not validated for wagering
- the Quality Gate intentionally prevents real recommendations from this package
- do not rename or promote this directory to V1.0

A release model must be created by the training pipeline, pass the locked 2025 holdout, pass native macOS/Windows checks, and be finalized through `training.cli finalize-release`.
