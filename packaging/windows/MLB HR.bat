@echo off
setlocal
cd /d "%~dp0"
set "MLB_HR_DATA_DIR=%~dp0runtime_data"

dir /s /b "%MLB_HR_DATA_DIR%\statcast\statcast_*.parquet" >nul 2>&1
if errorlevel 1 (
  echo.
  echo MLB HR no encuentra los datos historicos Statcast.
  echo Esperado: %MLB_HR_DATA_DIR%\statcast
  echo.
  echo Usa el paquete FULL o coloca la carpeta statcast dentro de runtime_data.
  echo.
  pause
  exit /b 2
)

start "MLB HR" "%~dp0app.exe"
endlocal
