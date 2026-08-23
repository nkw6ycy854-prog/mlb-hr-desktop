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

echo "Statcast local: $STATCAST_COUNT archivos"
echo "Rama: $BRANCH"

echo
echo "Ejecutando tests del source actual..."
PYTHONPATH=src python3 -m pytest -q

echo
echo "Publicando SOLO los archivos del release Windows..."
git add \
  src/mlb_hr/storage/paths.py \
  src/mlb_hr/selftest.py \
  src/mlb_hr/services/analysis.py \
  src/mlb_hr/ui/today.py \
  scripts/native_smoke.py \
  scripts/create_windows_full_release.sh \
  packaging/windows \
  .github/workflows/windows-native.yml \
  tests/test_runtime_paths.py \
  tests/test_selftest_runtime_data.py \
  tests/test_analysis_runtime_data.py \
  tests/test_windows_portable_release.py

if ! git diff --cached --quiet; then
  git commit -m "Build Windows V1.0.1 portable runtime release"
fi

git push origin "$BRANCH"

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

mkdir -p "$TMP/full/runtime_data/statcast"
echo "Integrando Statcast al paquete FULL..."
rsync -a "$STATCAST_SRC"/ "$TMP/full/runtime_data/statcast"/

BUNDLED_COUNT=$(find "$TMP/full/runtime_data/statcast" -type f -name 'statcast_*.parquet' | wc -l | tr -d ' ')
if [[ "$BUNDLED_COUNT" -ne "$STATCAST_COUNT" ]]; then
  echo "ERROR: copia Statcast incompleta ($BUNDLED_COUNT/$STATCAST_COUNT)."
  exit 1
fi

if [[ -f "$TMP/download/windows.json" ]]; then
  cp "$TMP/download/windows.json" "$TMP/full/windows-native-smoke.json"
fi

cat > "$TMP/full/RELEASE-INFO.txt" <<EOF
MLB HR Windows portable V1.0.1
Predictive model: V1.0.0
Expected model hash: 4f3296dcbe4fb932a6ebb7e0cabde9c5b33234be2ec1da07f29d10e7b50975ab
GitHub Actions run: $RUN_ID
Statcast parquet files bundled: $BUNDLED_COUNT

Abrir: MLB HR.bat
Verificar: SELF TEST.bat
EOF

mkdir -p "$OUT_DIR"
rm -f "$OUT"
(
  cd "$TMP/full"
  COPYFILE_DISABLE=1 zip -qr "$OUT" . -x '*.DS_Store' '__MACOSX/*'
)

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
echo "=========================================="
echo
echo "En Windows: descomprimir TODO y abrir 'SELF TEST.bat' primero."
