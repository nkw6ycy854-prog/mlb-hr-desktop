# MLB HR — Rediseño de interfaz V1.0.1

**Fecha:** 2026-08-26  
**Estado:** Diseño aprobado por secciones; pendiente de revisión final del usuario antes del plan de implementación.

## Objetivo
Reorganizar la interfaz de MLB HR para que sea más limpia, profesional, estable y consistente en macOS y Windows, sin modificar la lógica predictiva del modelo V1.0.0, su calibración, thresholds ni holdout.

## Enfoque aprobado
Mantener PySide6 y la lógica existente, pero reemplazar la estructura visual actual por una ventana principal con:
- barra lateral fija;
- `QStackedWidget` para HOY, HISTORIAL y AJUSTES;
- `QScrollArea` por pantalla;
- layouts adaptables para evitar solapamientos al redimensionar;
- feedback visible para todas las acciones.

No se migrará a QML/Qt Quick en esta fase.

## Navegación global
Barra lateral fija con:
- Hoy
- Historial
- Ajustes

Zona inferior de estado:
- Modelo
- Datos
- Versión

El contenido principal cambia mediante `QStackedWidget`. La barra lateral nunca debe superponerse con el contenido.

## Pantalla HOY
### Encabezado
- Título `HOY`.
- Botón `ACTUALIZAR`.
- Estado del modelo.
- Estado de datos.
- Conteo `X/Y juegos listos`.
- Hora de última actualización.

`ACTUALIZAR` se deshabilita durante el proceso y muestra feedback de progreso y resultado.

### Tabla principal
Mostrar Top 15 por defecto y un botón `VER TODOS`.

Columnas:
`# | Jugador | HR% | Clasificación | Confianza | Mejor cuota | FanDuel | Estado`

Valores prácticos de `Estado`:
- `RECOMENDADO`
- `VIGILAR`
- `NO CUMPLE FILTRO`

Si no existen PRIMARY/SECONDARY, la tabla no queda vacía: muestra los mejores jugadores analizados como `VIGILAR` o `NO CUMPLE FILTRO`.

### Detalle compacto del jugador
Al seleccionar una fila se actualiza un panel compacto con:
- jugador;
- juego y hora;
- HR%;
- clasificación;
- confianza;
- mejor cuota;
- FanDuel;
- motivos principales;
- riesgo principal.

No mostrar métricas avanzadas como Barrel%, xSLG, ISO o EV en esta tarjeta principal.

`COPIAR PICK` debe cambiar temporalmente a `COPIADO ✓`.

### Cuotas
Mostrar solo:
- mejor cuota disponible entre sportsbooks USA reportados por la fuente;
- FanDuel como referencia.

Si FanDuel es la mejor cuota, no duplicarlo. Ocultar sportsbooks sin mercado HR válido. Las cuotas siguen siendo post-modelo y no modifican probabilidad, clasificación ni ranking.

### Combinaciones
Mostrar siempre, cuando existan suficientes jugadores analizados:
- BEST 2-MAN
- BEST 3-MAN
- LONG-SHOT 2-MAN
- LONG-SHOT 3-MAN

Estados visuales:
- `✅ CUMPLE FILTRO / RECOMENDADA` si la combinación completa supera el criterio oficial.
- `⚠ NO CUMPLE FILTRO / ALTO RIESGO` si requiere WATCH o NO_BET para completarse.

Mostrar la clasificación individual de cada jugador dentro de la combinación. Nunca presentar una combinación de respaldo como recomendación oficial.

Layout: 2×2 cuando haya espacio; flujo vertical con scroll en ventanas pequeñas.

## Pantalla HISTORIAL
Dos vistas internas:
- `Jugadores`
- `Combinaciones`

### Filtros combinables
Período:
- Hoy
- 7 días
- 30 días
- Todo

Estado:
- Todos
- Recomendado
- Vigilar
- No cumple filtro

Resultado:
- Todos
- HR
- No HR
- Pendiente

### Tabla Jugadores
Columnas:
`Fecha | Hora | Jugador | HR% | Estado | Cuota | Resultado`

La hora se muestra en la zona horaria configurada en AJUSTES.

### Tabla Combinaciones
Columnas:
`Fecha | Inicio | Tipo | Selecciones | Filtro | Cuota | Resultado | P/L`

`Inicio` corresponde a la hora del primer juego de la combinación. El detalle muestra cada pierna con su juego y hora individual.

### Resumen dinámico
Recalcular según filtros:
- picks analizados;
- recomendados;
- aciertos;
- hit rate;
- ganancia/pérdida;
- ROI.

No añadir gráficos en esta fase.

## Pantalla AJUSTES
Cuatro secciones:

### General
- apuesta base;
- zona horaria;
- preferencias de interfaz.

### Cuotas
- The Odds API;
- FanDuel como referencia;
- mejor cuota automática;
- sportsbooks USA disponibles;
- botón `PROBAR CONEXIÓN`.

### IA
- provider;
- API key;
- activar/desactivar revisión IA;
- botón `PROBAR IA`.

### Sistema
- estado Statcast;
- modelo cargado;
- datos runtime;
- versión;
- último self-test;
- `ABRIR CARPETA DE DATOS`;
- `EJECUTAR SELF-TEST`.

`GUARDAR` debe confirmar exactamente qué cambió y si algo requiere reinicio. Las API keys se muestran ocultas. Ningún control deshabilitado debe parecer roto: debe explicar por qué no está disponible.

## Health check automático
Al iniciar la aplicación ejecutar un chequeo ligero de 2–5 segundos sobre:
- modelo V1.0.0;
- Statcast;
- base de datos;
- MLB Provider;
- estado de cuotas/API.

Si todo está bien, entrar normalmente a HOY. Si falla un componente crítico, mostrar un error explícito con `ABRIR AJUSTES` y `REINTENTAR`; nunca dejar una tabla vacía sin explicación.

El self-test completo permanece manual en AJUSTES.

## Reglas de funcionalidad
- Todos los botones deben tener una acción comprobable.
- Toda acción debe dar feedback visible de éxito, progreso, error o indisponibilidad.
- Ningún botón debe parecer roto por estar deshabilitado sin explicación.
- Las pantallas deben soportar redimensionamiento sin superposición.
- macOS y Windows deben compartir la misma estructura funcional.
- No tocar el modelo predictivo V1.0.0 durante esta fase.

## Manejo de errores
- Errores de providers: mostrar mensaje legible y permitir reintento.
- Falta de Statcast/modelo/DB: bloquear solo la función afectada y explicar la causa.
- Fallo de odds: las predicciones siguen visibles; mostrar `SIN CUOTA` o la referencia disponible.
- Fallo de IA: mantener análisis determinista y avisar de forma no intrusiva.

## Estrategia de pruebas
Antes de considerar la interfaz terminada:
1. tests unitarios de navegación y estados;
2. tests de botones y feedback;
3. tests de filtros de HISTORIAL;
4. tests de `Top 15 / Ver todos`;
5. tests de combinaciones recomendadas vs respaldo;
6. tests de health check;
7. pruebas de resize para impedir solapamientos;
8. smoke tests nativos macOS y Windows.

## Fuera de alcance de esta fase
- Reentrenar el modelo.
- Cambiar calibración, thresholds o holdout.
- Migrar a QML/Qt Quick.
- Añadir gráficos al historial.

## Criterio de aceptación
La fase UI se considera terminada únicamente cuando:
- HOY, HISTORIAL y AJUSTES funcionan sin controles muertos;
- no hay solapamientos en tamaños soportados;
- el health check detecta fallos críticos de runtime;
- las tablas muestran estados claros y no quedan vacías sin explicación;
- todas las pruebas relevantes pasan en código fuente;
- los smoke tests nativos pasan en macOS y Windows.
