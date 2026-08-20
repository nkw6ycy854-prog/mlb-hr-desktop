$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
if ($env:MLB_HR_MODEL_PACKAGE) {
  py -3.13 scripts/stage_model.py --model-dir $env:MLB_HR_MODEL_PACKAGE
} else {
  Write-Warning "MLB_HR_MODEL_PACKAGE is not set; building with the currently staged bundled model (development by default)."
}
py -3.13 -m pip install -e ".[build]"
pyside6-deploy -c pysidedeploy.spec
Write-Host "Build complete. Run the artifact self-test on this Windows machine. For a reviewed package, pass its package_hash:"
Write-Host "py -3.13 scripts/native_smoke.py --artifact path\to\MLBHR.exe --expected-model-hash HASH --output build_reports\windows.json"
