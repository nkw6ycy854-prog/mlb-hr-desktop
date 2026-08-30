# MLB HR Desktop V1.1.0 — Predicciones por partido, horarios, aciertos y auditoría funcional

**Fecha:** 2026-08-30  
**Estado:** Diseño aprobado por el usuario.  
**Target APP VERSION:** `1.1.0`  
**MODEL VERSION:** `V1.0.0` — congelado.

## 1. Objetivo

Mejorar MLB HR Desktop sin alterar el motor predictivo. V1.1.0 añade una segunda forma de visualizar las predicciones agrupadas por partido/equipo, corrige de raíz el manejo de horas, añade un apartado automático de aciertos diarios en HISTORIAL y exige una auditoría funcional completa de todos los controles de la aplicación.

La vista existente `TOP 15 / VER TODOS`, las clasificaciones del modelo, combinaciones, mejor cuota + FanDuel, health check y el resto de V1.0.x permanecen.

## 2. Prerrequisito de rama

V1.1.0 debe comenzar únicamente sobre una rama que ya contenga el hotfix V1.0.1 de Windows Statcast/runtime-data y cuyo Windows Native Gate exija runtime Statcast real.

Si el hotfix V1.0.1 todavía no está fusionado/verificado, el ejecutor debe detenerse antes de editar V1.1.0.

## 3. Restricciones no negociables

- No modificar `MODEL VERSION V1.0.0`.
- Mantener el model hash congelado: `4f3296dcbe4fb932a6ebb7e0cabde9c5b33234be2ec1da07f29d10e7b50975ab`.
- No modificar training, calibration, thresholds, holdout, feature math ni probabilidades históricas.
- Las cuotas siguen siendo post-modelo y no pueden alterar probabilidad, clasificación, score o ranking.
- `NOT_ELIGIBLE` nunca entra en Top 15, combinaciones, hit-rate ni aciertos.
- No usar expected/projected lineups salvo una aprobación futura explícita.
- Un juego solo genera predicciones cuando ambos lineups requeridos por la política vigente están confirmados.
- Los juegos LIVE/FINAL no generan nuevas predicciones pregame.
- No fabricar datos para llenar UI, métricas o historial.
- Settlement y estadísticas históricas deben ser idempotentes.
- macOS y Windows deben compartir el mismo comportamiento.

## 4. Arquitectura aprobada

Se mantiene PySide6 y los servicios existentes. Se añade una capa compartida de presentación/read-models entre dominio/storage y las pantallas.

```text
MODEL V1.0.0 / AnalysisService / SQLite
                  |
                  v
       Shared presentation/read models
       +-----------------------------+
       | GameTimeService             |
       | GamePredictionViewBuilder   |
       | DailyAccuracyService        |
       | Functional UI states        |
       +-----------------------------+
          |                       |
          v                       v
         HOY                  HISTORIAL
   Top 15 / Ver todos       Jugadores
   Por partidos             Combinaciones
   Combinaciones            Aciertos Hoy
```

La nueva capa reorganiza y presenta datos existentes. No recalcula el modelo.

## 5. Fuente única de verdad para horarios

### 5.1 Regla

Toda hora oficial de juego se conserva internamente como `datetime` timezone-aware, preferiblemente UTC. El texto visible se produce únicamente a través de `GameTimeService`.

No se permiten offsets manuales como `+1h`, `-1h`, supuestos de ET ni formateadores independientes por pantalla.

### 5.2 Zona predeterminada

La zona horaria predeterminada de la aplicación será:

`America/Santo_Domingo`

El usuario puede cambiarla desde AJUSTES. El valor persistido sigue siendo `timezone_name`.

### 5.3 Consistencia

Para un mismo `game_pk` y una misma zona configurada, la hora debe ser idéntica en:

- HOY / Top 15;
- HOY / Por partidos;
- detalle del jugador;
- combinaciones;
- HISTORIAL / Jugadores;
- HISTORIAL / Combinaciones;
- ACIERTOS HOY.

Cambiar la zona en AJUSTES debe refrescar las vistas sin reescribir la hora histórica original.

### 5.4 Pruebas obligatorias

Cubrir al menos:

- `America/Santo_Domingo`;
- `America/New_York`;
- fecha de EE. UU. con DST;
- fecha de EE. UU. sin DST;
- igualdad de hora entre varios read-models para un mismo juego;
- timestamp UTC ya timezone-aware;
- rechazo explícito o normalización controlada de datetimes naive según el contrato existente.

## 6. HOY — conservar Top 15 y añadir POR PARTIDOS

### 6.1 Navegación interna

Mantener la experiencia existente y añadir:

`[ TOP 15 ] [ POR PARTIDOS ]`

`TOP 15` conserva:

- Top 15 por defecto;
- `VER TODOS`;
- ranking global por `final_hr_probability`;
- detalle compacto;
- mejor cuota + FanDuel;
- estados prácticos;
- combinaciones existentes.

### 6.2 POR PARTIDOS

Mostrar todo el slate conocido agrupado por partido.

Ejemplo conceptual:

```text
COL @ ATL · 7:15 PM
✅ Ambos lineups confirmados

COLORADO
Hunter Goodman    14.8%  PRIMARY
Mickey Moniak     11.6%  WATCH
Ezequiel Tovar     9.4%  NO_BET

ATLANTA
Matt Olson        16.1%  PRIMARY
Ronald Acuña Jr.  13.2%  SECONDARY
Austin Riley      10.7%  WATCH
```

### 6.3 Orden dentro de cada equipo

Los jugadores de cada equipo se ordenan de mayor a menor HR%.

No se ordenan por batting order.

### 6.4 Todos los jugadores del lineup

Cuando un juego es analizable, la vista debe representar a todos los jugadores del lineup oficial disponible.

- Jugadores con predicción válida: mostrar HR%, clasificación, confianza, mejor cuota/FanDuel y estado.
- Si un jugador del lineup queda `NOT_ELIGIBLE`, puede mostrarse al final del equipo como `NO ELEGIBLE` con HR% `—` y razón conocida.
- Nunca inventar una probabilidad para `NOT_ELIGIBLE`.
- `NOT_ELIGIBLE` no entra en ranking, combinaciones ni estadísticas.

### 6.5 Partidos esperando lineups

No ocultarlos.

```text
NYY @ BOS · 7:05 PM

NYY  ✅ LINEUP CONFIRMADO
BOS  ⏳ ESPERANDO LINEUP

Predicciones disponibles cuando ambos lineups estén confirmados.
```

Un lineup unilateral no convierte al partido en `READY`.

### 6.6 LIVE / FINAL

Mostrar el juego en POR PARTIDOS con su estado, pero no generar nuevas predicciones.

`CHC @ CIN · EN VIVO — Predicciones pregame cerradas.`

Las predicciones pregame que ya existan se consultan desde HISTORIAL.

### 6.7 Empty states

La vista nunca queda vacía sin motivo. Debe diferenciar:

- esperando uno o ambos lineups;
- juego LIVE;
- juego FINAL;
- datos runtime no disponibles;
- análisis aún no ejecutado;
- error de provider.

## 7. HISTORIAL — ACIERTOS HOY

### 7.1 Nueva vista

Añadir una tercera vista interna:

`[ JUGADORES ] [ COMBINACIONES ] [ ACIERTOS HOY ]`

Las vistas actuales no se eliminan.

### 7.2 Objetivo

ACIERTOS HOY debe revisar automáticamente las predicciones pregame registradas, contar cuántas acertaron y mostrar exactamente cuáles fueron.

### 7.3 Jugadores acertados

Un jugador cuenta como acierto cuando:

1. existía una predicción pregame persistida antes del inicio;
2. la predicción era válida y no `NOT_ELIGIBLE`;
3. `final_hr_probability >= 0.05`;
4. el resultado oficial asentado indica al menos un HR.

Mostrar:

- jugador;
- equipo/juego;
- hora usando `GameTimeService`;
- HR% original;
- clasificación/estado original;
- cuota registrada disponible;
- `✅ ACERTADO / HR`.

### 7.4 Población diaria de precisión

Las métricas diarias de jugadores incluyen todas las predicciones pregame válidas con HR% `>= 5.0%`.

```text
Predicciones >=5%: 21
Resueltas:          18
HR acertados:        5
Pendientes:          3
Hit Rate:         27.8%
```

`Hit Rate = aciertos / predicciones resueltas`.

No contar pendientes en el denominador.

### 7.5 Combinaciones acertadas

Una combinación cuenta como `GANADA` únicamente si todas las piernas requeridas dieron HR según el settlement existente.

Mostrar:

- tipo;
- piernas;
- juego/hora de cada pierna;
- filtro `QUALIFIED/FALLBACK`;
- cuota registrada/estimada;
- resultado `✅ GANADA`;
- P/L cuando exista.

Las combinaciones no usan el umbral individual de 5% para su propia métrica; usan las combinaciones realmente persistidas antes de los juegos.

### 7.6 Resumen ACIERTOS HOY

Mostrar al menos:

```text
Jugadores acertados: N
Combinaciones ganadas: M
```

y las listas concretas de ambos grupos.

Si no hay aciertos:

`Todavía no hay predicciones acertadas para esta fecha.`

Si existen pendientes, indicarlo separadamente; nunca convertir pendiente en fallo.

## 8. Settlement automático

### 8.1 Momentos de ejecución

Revisar predicciones pendientes:

1. al abrir la aplicación;
2. al pulsar `ACTUALIZAR`;
3. al pulsar el nuevo botón `ACTUALIZAR RESULTADOS` en HISTORIAL.

### 8.2 Botón ACTUALIZAR RESULTADOS

Debe ejecutar settlement/result refresh sin volver a calcular el slate predictivo completo.

Comportamiento:

- deshabilitar mientras trabaja;
- feedback `Actualizando resultados…`;
- éxito con conteo de registros actualizados;
- error legible;
- refrescar Jugadores, Combinaciones y Aciertos Hoy al terminar.

### 8.3 Idempotencia

Ejecutar settlement repetidamente para el mismo juego/predicción no puede:

- duplicar settlements;
- duplicar P/L;
- duplicar eventos de bankroll;
- duplicar aciertos;
- cambiar un resultado FINAL correctamente asentado sin una política explícita de corrección oficial.

### 8.4 Resultados no fiables

Si MLB todavía no proporciona un resultado final fiable, mantener `PENDIENTE`.

No inferir resultados desde noticias, cuotas u otras señales.

## 9. Auditoría funcional completa

V1.1.0 no se considera terminada hasta auditar cada control interactivo visible.

### 9.1 Inventario mínimo

HOY:
- ACTUALIZAR;
- TOP 15;
- POR PARTIDOS;
- VER TODOS;
- seleccionar jugador;
- COPIAR PICK;
- interacción/detalle de combinaciones.

HISTORIAL:
- Jugadores;
- Combinaciones;
- Aciertos Hoy;
- período;
- estado;
- resultado;
- selección de fila;
- ACTUALIZAR RESULTADOS.

AJUSTES:
- apuesta base presets;
- apuesta personalizada;
- zona horaria;
- densidad/interfaz;
- Odds API;
- PROBAR CONEXIÓN;
- IA provider/key/toggle;
- PROBAR IA;
- GUARDAR;
- ABRIR CARPETA DE DATOS;
- SELF-TEST;
- REINTENTAR/health cuando aplique.

### 9.2 Contrato de cada control

Cada control debe tener:

1. señal/evento conectado;
2. efecto observable;
3. estado disabled/loading si ejecuta trabajo;
4. feedback éxito/error/indisponibilidad;
5. prueba automatizada cuando sea razonable;
6. comportamiento de error definido.

No ocultar un botón muerto para “resolver” la auditoría. Corregir su intención o reportar el bloqueo.

### 9.3 Matriz de auditoría

La entrega final debe producir `FUNCTIONAL_AUDIT_V1_1.md` con una fila por control:

`Pantalla | Control | Signal/handler | Efecto | Loading | Feedback | Test | Estado`

Estado permitido: `PASS` o `BLOCKED` con causa explícita. Cero controles `UNKNOWN`.

## 10. Manejo de estados vacíos

Ninguna pantalla/lista queda vacía sin explicación.

Estados específicos para:

- sin juegos;
- juegos sin lineups;
- no hay pregame;
- no hay historial;
- no hay aciertos hoy;
- no hay cuotas;
- Statcast no disponible;
- provider/API no configurado;
- error de red;
- settlement pendiente.

## 11. Persistencia y compatibilidad

- No reescribir predicciones históricas para cambiar timezone.
- Persistir/usar UTC original para `game_time`.
- Reutilizar registros históricos y settlement existentes.
- Si se requiere una migración de SQLite, debe ser backward-compatible y probada desde la versión de schema actual.
- No borrar DB del usuario.
- Los nuevos read-models son derivados; no deben duplicar información que ya tiene una fuente canónica.

## 12. Estrategia de pruebas

Obligatorio antes de release candidate:

- unit tests de `GameTimeService`;
- tests de agrupación por partido/equipo;
- tests de lineups pendientes/unilaterales;
- tests LIVE/FINAL;
- tests de orden HR% dentro de equipo;
- tests `NOT_ELIGIBLE`;
- tests DailyAccuracy `>=5%`;
- tests de combinaciones ganadas;
- tests de settlement idempotente;
- tests del botón ACTUALIZAR RESULTADOS;
- tests de cambio de timezone y refresco;
- tests de cada control auditado;
- empty-state tests;
- suite completa `pytest -q`;
- UI smoke;
- macOS native smoke;
- Windows Native Gate con runtime Statcast obligatorio.

## 13. Criterios de aceptación

V1.1.0 es aceptable únicamente si:

- Top 15 actual continúa funcionando sin regresiones;
- POR PARTIDOS muestra el slate completo y agrupa correctamente;
- jugadores por equipo están ordenados por HR%;
- no se generan picks con un solo lineup confirmado;
- las horas son consistentes en toda la app;
- `America/Santo_Domingo` es el default;
- ACIERTOS HOY cuenta y enumera aciertos reales;
- las métricas de jugadores usan HR% >=5%;
- settlement es automático e idempotente;
- ACTUALIZAR RESULTADOS funciona;
- la auditoría tiene cero controles muertos/UNKNOWN;
- ninguna pantalla queda vacía sin explicación;
- modelo V1.0.0/hash permanecen intactos;
- macOS y Windows pasan verificación nativa.

## 14. Fuera de alcance

- Reentrenar o recalibrar modelo.
- Cambiar thresholds/clasificaciones.
- Expected/projected lineups.
- Predicciones in-game.
- Nuevas fórmulas de combinaciones.
- Nuevos sportsbooks/providers salvo fixes necesarios para controles existentes.
- Gráficos nuevos en Historial.
- Cambios estéticos no relacionados con funcionalidad/legibilidad.
