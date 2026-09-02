@echo off
setlocal
cd /d "%~dp0"

dir /s /b "%~dp0runtime_data\statcast\statcast_*.parquet" >nul 2>&1
if errorlevel 1 (
  echo.
  echo MLB HR no encuentra los datos historicos Statcast.
  echo Esperado: %~dp0runtime_data\statcast
  echo.
  echo Usa el paquete FULL o coloca la carpeta statcast dentro de runtime_data.
  echo.
  pause
  exit /b 2
)

start "MLB HR" "%~dp0app.exe"
endlocal
