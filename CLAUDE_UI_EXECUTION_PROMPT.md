# Prompt para Claude Code — MLB HR UI Redesign

Trabaja sobre mi repositorio local de MLB HR.

Antes de editar:
1. Lee `docs/superpowers/specs/2026-08-26-mlb-hr-ui-redesign-design.md`.
2. Lee `CLAUDE_EXECUTION_ROADMAP.md`.
3. Ejecuta los planes en el orden indicado, uno por uno.
4. Usa TDD: prueba que falla -> cambio mínimo -> prueba verde -> commit.
5. Detente al final de cada plan y dame:
   - archivos modificados;
   - tests ejecutados y resultado exacto;
   - commit SHA;
   - cualquier desviación de la especificación.
6. NO empieces el siguiente plan hasta que yo lo autorice.

REGLAS CRÍTICAS:
- No modificar el modelo predictivo V1.0.0.
- No modificar training, calibración, thresholds, holdout, feature math ni manifests congelados.
- No reutilizar 2025 para tuning.
- Odds son post-modelo y no pueden cambiar probabilidad, clasificación o ranking.
- `PredictionCard.market` sigue siendo FanDuel para el ledger; la mejor cuota es comparación/display.
- `NOT_ELIGIBLE` jamás entra en combinaciones de respaldo.
- No borrar historial ni DB del usuario.
- No esconder errores: botones y providers deben mostrar feedback.
- No afirmar que algo está terminado sin ejecutar las verificaciones del plan.
- Antes de cambios de producción, espera mi palabra exacta: `Ejecuta`.

Empieza únicamente leyendo los documentos y resumiendo el Plan 1. No edites archivos hasta que yo diga `Ejecuta`.
