#!/bin/bash
set -euo pipefail

cd "${1:-.}"
ROOT="$PWD"
STATCAST_SRC="$ROOT/data/statcast"
WORKFLOW="Windows Native Gate"
BRANCH="$(git branch --show-current)"
OUT_NAME="MLB-HR-Windows-V1.0.1-FULL.zip"
OUT_DIR="$HOME/Desktop"
OUT="$OUT_DIR/$OUT_NAME"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

if [[ -z "$BRANCH" ]]; then
  echo "ERROR: no pude determinar la rama Git actual."
  exit 1
fi

for cmd in git gh python3 unzip zip rsync; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "ERROR: falta $cmd"; exit 1; }
done

gh auth status >/dev/null 2>&1 || {
  echo "ERROR: GitHub CLI no tiene una sesion activa. Ejecuta gh auth login primero."
  exit 1
}

[[ -d "$STATCAST_SRC" ]] || {
  echo "ERROR: no existe $STATCAST_SRC"
  exit 1
}

STATCAST_COUNT=$(find "$STATCAST_SRC" -type f -name 'statcast_*.parquet' | wc -l | tr -d ' ')
if [[ "$STATCAST_COUNT" -eq 0 ]]; then
  echo "ERROR: data/statcast no contiene Parquet."
  exit 1
fi

APP_VERSION=$(PYTHONPATH="$ROOT/src" python3 -c "import mlb_hr; print(mlb_hr.__version__)")
MODEL_HASH=$(grep -m1 'EXPECTED_MODEL_HASH:' "$ROOT/.github/workflows/windows-native.yml" | sed -E 's/.*EXPECTED_MODEL_HASH:[[:space:]]*//')
MODEL_PACKAGE_DIR=$(grep -m1 'MODEL_PACKAGE_DIR:' "$ROOT/.github/workflows/windows-native.yml" | sed -E 's/.*MODEL_PACKAGE_DIR:[[:space:]]*//')
MODEL_VERSION=$(basename "$MODEL_PACKAGE_DIR")

[[ -n "$APP_VERSION" ]] || { echo "ERROR: no pude leer mlb_hr.__version__."; exit 1; }
[[ -n "$MODEL_HASH" ]] || { echo "ERROR: no pude leer EXPECTED_MODEL_HASH del workflow."; exit 1; }
[[ -n "$MODEL_VERSION" ]] || { echo "ERROR: no pude leer MODEL_PACKAGE_DIR del workflow."; exit 1; }

echo "Statcast local: $STATCAST_COUNT archivos"
echo "Rama: $BRANCH"
echo "App version: $APP_VERSION"
echo "Model version: $MODEL_VERSION (hash $MODEL_HASH)"

echo
echo "Ejecutando tests del source actual..."
PYTHONPATH=src python3 -m pytest -q

echo
echo "Publicando SOLO los archivos del release Windows..."
git add \
  src/mlb_hr/__init__.py \
  pyproject.toml \
  src/mlb_hr/storage/paths.py \
  src/mlb_hr/selftest.py \
  src/mlb_hr/services/analysis.py \
  src/mlb_hr/ui/today.py \
  scripts/native_smoke.py \
  scripts/create_windows_full_release.sh \
  scripts/windows_full_package.py \
  packaging/windows \
  tests/fixtures/statcast_ci_fixture \
  .github/workflows/windows-native.yml \
  tests/test_runtime_paths.py \
  tests/test_selftest_runtime_data.py \
  tests/test_analysis_runtime_data.py \
  tests/test_windows_portable_release.py \
  tests/test_windows_full_package.py

if ! git diff --cached --quiet; then
  git commit -m "Build Windows V1.0.1 portable runtime release"
fi

git push origin "$BRANCH"
RELEASE_COMMIT="$(git rev-parse HEAD)"

echo
echo "Lanzando build nativo Windows en GitHub Actions..."
gh workflow run "$WORKFLOW" --ref "$BRANCH"
sleep 8

RUN_ID=$(gh run list \
  --workflow "$WORKFLOW" \
  --branch "$BRANCH" \
  --event workflow_dispatch \
  --limit 1 \
  --json databaseId \
  --jq '.[0].databaseId')

if [[ -z "$RUN_ID" || "$RUN_ID" == "null" ]]; then
  echo "ERROR: no pude localizar el workflow recién lanzado."
  exit 1
fi

echo "Windows Run ID: $RUN_ID"
gh run watch "$RUN_ID" --exit-status

echo
echo "Descargando build Windows..."
mkdir -p "$TMP/download"
gh run download "$RUN_ID" -n "MLB-HR-Windows-Native" -D "$TMP/download"

APP_ZIP="$TMP/download/MLB-HR-Windows-App.zip"
[[ -f "$APP_ZIP" ]] || {
  echo "ERROR: el artifact no contiene MLB-HR-Windows-App.zip"
  find "$TMP/download" -maxdepth 2 -type f -print
  exit 1
}

mkdir -p "$TMP/full"
unzip -q "$APP_ZIP" -d "$TMP/full"

[[ -f "$TMP/full/app.exe" ]] || { echo "ERROR: app.exe no existe en el artifact."; exit 1; }
[[ -f "$TMP/full/MLB HR.bat" ]] || { echo "ERROR: falta MLB HR.bat."; exit 1; }
[[ -f "$TMP/full/SELF TEST.bat" ]] || { echo "ERROR: falta SELF TEST.bat."; exit 1; }

if [[ -f "$TMP/download/windows.json" ]]; then
  cp "$TMP/download/windows.json" "$TMP/windows-native-smoke.json"
fi

cat > "$TMP/full/RELEASE-INFO.txt" <<EOF
MLB HR Windows portable V$APP_VERSION
Predictive model: $MODEL_VERSION
Expected model hash: $MODEL_HASH
GitHub Actions run: $RUN_ID
Release commit: $RELEASE_COMMIT
Statcast parquet files bundled: $STATCAST_COUNT

Abrir: MLB HR.bat
Verificar: SELF TEST.bat

Ver RELEASE-MANIFEST.json (dentro de este paquete) para el reporte
estructurado firmado por el self-test --require-runtime-data.
EOF

echo
echo "Ensamblando paquete FULL con Statcast real y verificando self-test..."
mkdir -p "$OUT_DIR"
rm -f "$OUT"

PYTHONPATH="$ROOT/src" python3 "$ROOT/scripts/windows_full_package.py" build \
  --bundle-dir "$TMP/full" \
  --statcast-src "$STATCAST_SRC" \
  --output-zip "$OUT" \
  --manifest-path "$TMP/full-release-manifest.json" \
  --app-version "$APP_VERSION" \
  --model-version "$MODEL_VERSION" \
  --model-hash "$MODEL_HASH" \
  --release-commit "$RELEASE_COMMIT" \
  --self-test-cmd '["python3", "-m", "mlb_hr.selftest", "--require-runtime-data"]'

echo
echo "Validando el ZIP FULL generado (byte a byte, no solo el script)..."
PYTHONPATH="$ROOT/src" python3 "$ROOT/scripts/windows_full_package.py" validate --zip "$OUT"

MANIFEST_JSON="$(cat "$TMP/full-release-manifest.json")"
BUNDLED_COUNT="$(PYTHONPATH="$ROOT/src" python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['statcast_parquet_count'])" "$TMP/full-release-manifest.json")"

SHA=$(shasum -a 256 "$OUT" | awk '{print $1}')
SIZE=$(du -h "$OUT" | awk '{print $1}')

echo
echo "=========================================="
echo "WINDOWS FULL RELEASE = CREATED"
echo "Archivo: $OUT"
echo "Tamano:  $SIZE"
echo "SHA256:  $SHA"
echo "Statcast: $BUNDLED_COUNT archivos"
echo "Run ID:   $RUN_ID"
echo "App version: $APP_VERSION"
echo "Model version: $MODEL_VERSION"
echo "Model hash: $MODEL_HASH"
echo "Release commit: $RELEASE_COMMIT"
echo "=========================================="
echo "$MANIFEST_JSON"
echo "=========================================="
echo
echo "En Windows: descomprimir TODO y abrir 'SELF TEST.bat' primero."
