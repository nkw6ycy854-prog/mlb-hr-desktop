MLB HR - Windows portable V1.0.1
Modelo predictivo: V1.0.0 (sin cambios)

USO
1. Descomprime TODO el ZIP en una carpeta normal.
2. No muevas app.exe fuera de esa carpeta.
3. Abre "MLB HR.bat". Ese launcher fija MLB_HR_DATA_DIR al runtime_data incluido.
4. Para verificar la instalación, abre "SELF TEST.bat" y confirma:
   WINDOWS_RUNTIME_SELF_TEST = PASS

IMPORTANTE
- El paquete FULL incluye runtime_data/statcast.
- Si falta esa carpeta, el programa se detiene en vez de analizar sin historial.
- FanDuel/The Odds API sigue siendo post-modelo y no modifica la probabilidad.
