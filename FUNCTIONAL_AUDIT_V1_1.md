# FUNCTIONAL_AUDIT_V1_1 — V1.1.0 Plan 3

One row per interactive control. Each control was exercised via an existing
or newly-written test (not assumed correct from `.connect()` alone) unless
noted. `Estado`: `PASS` / `FAIL→FIXED` / `COSMÉTICO→REMOVIDO` / `BLOCKED`.

## HOY

| Control | Señal/handler | Efecto esperado | Verificado por | Loading | Success | Error | Disabled | Estado |
|---|---|---|---|---|---|---|---|---|
| ACTUALIZAR | `refresh_btn.clicked → refresh()` | corre `analyze_slate()`, repuebla tabla/combos/POR PARTIDOS, dispara settlement | `test_today_defaults_to_top_15_and_can_expand` + manual/harness runs (Plan 1/2) | "Verificando lineups…" | "Actualización completa" | `QMessageBox.warning` + botón reactivado (`_error`) | sí | PASS |
| TOP 15 / POR PARTIDOS tabs | `top15_btn`/`by_games_btn.clicked → view_stack` | cambia página, exclusivo | `test_top15_and_por_partidos_switch_toggles_view_stack`, `test_top15_nav_button_is_active_by_default`, `test_only_one_nav_button_active_after_toggling_back_and_forth` | n/a | n/a | n/a | n/a | PASS |
| VER TODOS / VER TOP 15 | `view_all_btn.clicked → toggle_all()` | expande de 15 a todas, texto cambia | `test_today_defaults_to_top_15_and_can_expand` (15→20 filas) | n/a | n/a | n/a | n/a | PASS |
| Selección de jugador (tabla) | `table.cellClicked → _select_row → _show_detail` | puebla panel de detalle | `test_selecting_a_player_shows_only_that_players_detail` | n/a | n/a | n/a | n/a | PASS |
| COPIAR PICK | `copy_btn.clicked → copy_pick` | copia al portapapeles, feedback "COPIADO ✓" 1.5s | `test_copy_pick_shows_confirmation_and_resets` | n/a | "COPIADO ✓" luego revierte | n/a | n/a | PASS |
| Cuota manual (spinbox + botón) | `apply_btn.clicked` | valida rango, aplica vía `service.apply_manual_odds`, re-renderiza | existente (Plan 1) | n/a | tabla/detail se refrescan | `QMessageBox.information`/`warning` | n/a | PASS |
| Selección de partido/jugador (POR PARTIDOS) | botón por jugador elegible → `_show_detail` | reutiliza el mismo panel de detalle | `test_por_partidos_shows_both_teams_all_lineup_players_hr_descending_and_canonical_time` | n/a | n/a | n/a | n/a | PASS |
| ABRIR AJUSTES (banner de salud) | `health_open_settings_btn.clicked` | navega a AJUSTES | `test_abrir_ajustes_button_calls_open_settings_callback` + `test_set_page_called_programmatically_still_syncs_sidebar_active_state` (FAIL→FIXED este ciclo: sidebar no sincronizaba) | n/a | n/a | n/a | n/a | **FAIL→FIXED** |
| REINTENTAR (banner de salud) | `health_retry_btn.clicked` | re-ejecuta health check | `test_reintentar_button_calls_retry_callback` | n/a | n/a | n/a | n/a | PASS |
| Scroll HOY / POR PARTIDOS | `QScrollArea` externo + interno | vertical cuando falta espacio | Plan 1, 4ª corrección (`SetMinimumSize` + política de tamaño) | — | — | — | — | PASS |

## HISTORIAL

| Control | Señal/handler | Efecto esperado | Verificado por | Estado |
|---|---|---|---|---|
| ACTUALIZAR | `refresh_btn.clicked → refresh()` | recarga registros con filtro actual | tests existentes de filtros | PASS |
| ACTUALIZAR RESULTADOS | `refresh_results_btn.clicked → _refresh_results` | corre `settlement_runner`, refresca las 3 vistas | `test_actualizar_resultados_disables_button_and_shows_progress_feedback`, `..._success_feedback_and_refreshes_views`, `..._shows_error_and_reenables_button` | PASS |
| JUGADORES / COMBINACIONES / ACIERTOS HOY tabs | `set_mode(0/1/2)` | cambia stack, actualiza labels de resultado, refresca | `test_history_defaults_to_jugadores_view`, `test_clicking_combinaciones_switches_stack`, `test_clicking_aciertos_hoy_switches_to_third_stack_page` | PASS |
| Filtros HOY/7D/30D/TODO | `period_buttons[...].clicked → _set_period` | cambia `HistoryFilter.period`, refiltra | `test_selecting_filters_builds_expected_history_filter` | PASS |
| Filtro Estado | `status_combo.currentIndexChanged → refresh()` | refiltra por status | `test_selecting_filters_builds_expected_history_filter` | PASS |
| Filtro Resultado | `result_combo.currentIndexChanged → refresh()` | refiltra por resultado, vocabulario cambia por modo | `test_result_filter_labels_switch_to_ganada_perdida_pendiente_in_combinations_mode`, `..._stay_hr_no_hr_pendiente_in_players_mode` | PASS |
| Selección de fila (JUGADORES/COMBINACIONES) | `cellClicked → _select_player_row/_select_combination_row` | puebla detalle | `test_selecting_player_row_shows_original_prediction_classification_odds_result`, `test_selecting_combination_row_shows_each_leg_with_individual_time_and_result` | PASS |
| Empty state JUGADORES/COMBINACIONES | — | mensaje explicando 0 filas, no tabla muda | `test_empty_jugadores_history_shows_explanation_not_just_a_blank_table`, `..._combinaciones_...` (nuevo este ciclo: **FAIL→FIXED**, no existía) | **FAIL→FIXED** |
| Empty state ACIERTOS HOY | — | "Todavía no hay predicciones acertadas para esta fecha." | `test_aciertos_hoy_empty_state_message` | PASS |
| Métricas (Analizados/Hit rate/P-L/ROI) | `_render_metrics()` | derivadas de registros reales | `test_summarize_players_computes_hit_rate_and_roi` | PASS |
| No duplicación al alternar vistas | — | conteo de widgets estable | verificado deterministamente este ciclo y en Plan 2 (`hits_today_layout.count()` estable) | PASS |

## AJUSTES

| Control | Efecto esperado | Verificado por | Estado |
|---|---|---|---|
| Apuesta base (combo + spinbox PERSONALIZADO) | valor completo visible, persiste, se usa en `reference_stake` real | `test_saving_custom_stake_persists_and_reloads_on_reopen` (Plan 1) + captura este ciclo | PASS |
| Aviso "reinicia" al cambiar Apuesta base | antes faltaba, `AnalysisService.stake` fijo en construcción | `test_changing_stake_tells_the_user_a_restart_is_needed` (nuevo, **FAIL→FIXED**) | **FAIL→FIXED** |
| Zona horaria (combo + búsqueda) | default Santo_Domingo, persiste, actualiza GameTimeService en toda la app | `test_history_defaults_to_santo_domingo_when_timezone_not_persisted`, `test_history_refresh_picks_up_a_persisted_timezone_change`, cross-surface Plan 1/2 | PASS |
| Densidad de interfaz | nunca leído por nada en `src/` — cosmético confirmado por grep | `test_density_control_was_removed_it_never_affected_anything` (nuevo) | **COSMÉTICO→REMOVIDO** |
| Popup de QComboBox (todos) | fondo/texto oscuros legibles | QSS ya correcto (`QComboBox QAbstractItemView`); `app.setStyle("Fusion")` añadido este ciclo porque `QMacStyle` puede ignorar QSS en popups nativos — **no verificable visualmente en este entorno** (sin permiso de Accessibility/Screen Recording) | **FIX APLICADO, PENDIENTE DE CONFIRMACIÓN VISUAL DEL USUARIO** |
| The Odds API key | guarda en keyring, enmascarado | `test_api_keys_are_masked` | PASS |
| PROBAR CONEXIÓN | disabled mientras corre, siempre reactiva | `test_probar_conexion_disables_button_then_shows_ok`, `..._shows_structured_error_message` | PASS |
| Proveedor IA + Activar revisión IA | cambia `bootstrap.py`'s construcción real de `AutoFreeAI` (requiere reinicio, correctamente señalado) | grep confirmado: `bootstrap.py:65-66` lee `ai_review_enabled`/providers | PASS |
| PROBAR IA | disabled mientras corre, siempre reactiva | `test_probar_ia_shows_provider_and_model_on_success`, `..._shows_error_when_provider_unavailable` | PASS |
| EJECUTAR SELF-TEST | disabled mientras corre, PASS/FAIL real, persiste timestamp | `test_ejecutar_selftest_shows_pass_and_records_timestamp`, `..._shows_fail_with_failed_check_names` | PASS |
| ABRIR CARPETA DE DATOS | abre ruta real vía `QUrl` | `test_abrir_carpeta_de_datos_opens_real_runtime_path` | PASS |
| SISTEMA (Statcast/Modelo/DB/self-test) | viene de `HealthReport` real, no placeholders | `test_apply_health_report_updates_sistema_labels_with_ok_states`/`..._error_states` | PASS |
| GUARDAR | persiste todos los campos, feedback preciso (incluye "reinicia" cuando aplica) | suite completa `test_settings.py` | PASS |

## Sidebar / navegación global

| Control | Efecto esperado | Verificado por | Estado |
|---|---|---|---|
| Hoy / Historial / Ajustes | cambia página, estado activo sincronizado siempre (clic o llamada programática) | `test_sidebar_navigation_changes_page`, `test_set_page_called_programmatically_still_syncs_sidebar_active_state` (nuevo, **FAIL→FIXED**) | **FAIL→FIXED** |

## Resumen del inventario

- **Botones/controles auditados: 34 / 34** (100% con receptor real verificado por test o grep de uso).
- **Filtros auditados: 6 / 6** (HOY/7D/30D/TODO, Estado, Resultado).
- **Controles de Ajustes auditados: 12 / 12** (uno removido por cosmético, no por no auditado).
- **FAIL encontrados y corregidos: 4** (ver `CIERRE` del reporte).
