#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ -n "${MLB_HR_MODEL_PACKAGE:-}" ]]; then
  python3.13 scripts/stage_model.py --model-dir "$MLB_HR_MODEL_PACKAGE"
else
  echo "WARNING: MLB_HR_MODEL_PACKAGE is not set; building with the currently staged bundled model (development by default)."
fi
python3.13 -m pip install -e '.[build]'
pyside6-deploy -c pysidedeploy.spec
printf '\nBuild complete. Run the artifact self-test on this Mac. For a reviewed package, pass its package_hash:\n'
printf 'python3.13 scripts/native_smoke.py --artifact /path/to/MLBHR.app --expected-model-hash <HASH> --output build_reports/macos.json\n'
