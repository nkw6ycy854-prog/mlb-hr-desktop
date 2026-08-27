#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

BUNDLED_MODEL="src/mlb_hr/resources/bundled_model/model_manifest.json"
BACKUP_MODEL="$(mktemp "${TMPDIR:-/tmp}/mlbhr-bundled-model.XXXXXX")"
cp "$BUNDLED_MODEL" "$BACKUP_MODEL"
restore_bundled_model() {
  cp "$BACKUP_MODEL" "$BUNDLED_MODEL"
  rm -f "$BACKUP_MODEL"
}
trap restore_bundled_model EXIT

if [[ -n "${MLB_HR_MODEL_PACKAGE:-}" ]]; then
  python3.13 scripts/stage_model.py --model-dir "$MLB_HR_MODEL_PACKAGE"
else
  echo "WARNING: MLB_HR_MODEL_PACKAGE is not set; building with the currently staged bundled model (development by default)."
fi
python3.13 -m pip install -e '.[build]'
# --force answers pyside6-deploy's interactive "install into a non-venv interpreter?"
# prompt non-interactively (this project intentionally builds against the Framework
# python, not .venv, per pysidedeploy.spec's python_path — see git history). Without
# --force, pyside6-deploy blocks on stdin and fails with EOFError in CI/non-TTY runs.
pyside6-deploy -c pysidedeploy.spec --force
printf '\nBuild complete. Run the artifact self-test on this Mac. For an operational runtime, require Statcast too:\n'
printf 'python3.13 scripts/native_smoke.py --artifact /path/to/MLBHR.app --expected-model-hash <HASH> --require-runtime-data --output build_reports/macos.json\n'
