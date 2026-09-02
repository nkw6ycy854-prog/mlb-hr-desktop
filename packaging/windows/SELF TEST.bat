@echo off
setlocal
cd /d "%~dp0"

echo Ejecutando self-test de MLB HR con datos Statcast obligatorios...
echo.
"%~dp0app.exe" --self-test --require-runtime-data
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" (
  echo WINDOWS_RUNTIME_SELF_TEST = PASS
) else (
  echo WINDOWS_RUNTIME_SELF_TEST = FAIL
)
echo.
pause
exit /b %RC%
