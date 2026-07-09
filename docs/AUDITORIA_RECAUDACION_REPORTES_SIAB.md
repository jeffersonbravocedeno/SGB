# Auditoría de Recaudación y Reportes de SIAB

Fecha: 2026-07-05  
Fase: 2A — auditoría estática, sin cambios funcionales ni consultas a PostgreSQL

Esta auditoría revisó el código Python, rutas, plantillas, pruebas y scripts SQL
versionados del repositorio. Tomó como contrato los cuatro documentos indicados
para esta fase. No se consultó ninguna base de datos y no se extrapolaron datos
de `bingo_ensayo_hibridos` hacia la base real `bingo`.

## 1. Regla financiera de SIAB

Un `Carton` maestro representa una sola adquisición dentro de un `Bingo`. Su
importe registrado está en `Carton.preciopagado`. Cada fila de
`CartonPartidaBingo` representa únicamente el derecho y resultado de ese mismo
cartón en una ronda; no contiene precio, pago ni una venta adicional.

Por tanto:

- la recaudación registrada de un Bingo debe partir de cartones físicos únicos,
  identificados por `idcarton`, y no de filas de participación;
- una participación no agrega ingresos;
- el precio de un maestro no debe volver a sumarse por cada ronda;
- los reportes por ronda pueden contar participantes y mostrar resultados, pero
  no deben actuar como liquidación general;
- los premios monetarios son conceptos de la ronda o del Bingo, no del número
  de participaciones;
- `preciopagado` permite calcular importe registrado, pero no demuestra que el
  dinero haya sido cobrado porque no existe confirmación de pago de cartón.

Ejemplo: un maestro de `$5,00` con tres participaciones aporta `$5,00` a la
recaudación registrada. Las tres filas de participación no convierten ese
importe en `$15,00`.

## 2. Fuentes monetarias reales encontradas

| Entidad y campo | Significado comprobado | Uso actual | Límite financiero |
|---|---|---|---|
| `Bingo.preciocarton` | Precio de lista del cartón | Formularios, listados, detalle y PDF | No es necesariamente el valor finalmente registrado en el cartón |
| `Carton.preciopagado` | Importe registrado una vez en el cartón | Venta, listados y Excel | Admite `NULL`; no tiene método, referencia ni confirmación de cobro |
| `Partidabingo.valorefectivo` | Premio monetario programado de una ronda | Formularios y pantallas de Bingo, ronda, tablero y desempate | No registra entrega o pago efectivo del premio |
| `Partidabingo.premiomaterial` | Descripción del premio material de una ronda | Pantallas y formulario | No tiene valoración monetaria |
| `Bingo.premiomayor` | Premio mayor programado del Bingo | Listados, detalle y PDF | No indica pago ni aclara si es adicional a `valorefectivo` de alguna ronda |
| `Bingo.descripcionpremios` | Descripción libre de premios | Detalle y formulario | No es una fuente numérica |
| `Configuracion.Regalo.valorregalo` | Valor de un regalo asociado a aportes | Catálogo de configuración | No es un gasto ni premio de Bingo según las relaciones actuales |
| `Ahorro.montoahorro` | Ahorro de un socio relacionado con un Bingo | Módulo Finanzas | No representa venta de cartón, recaudación ni gasto del Bingo |
| `Pago.montopagado` | Pago modelado para un préstamo | Módulo Finanzas | No debe reutilizarse para cartones; el contrato físico auditado además difiere del modelo Django |
| Campos monetarios de `Prestamo` | Solicitud, total y saldo de préstamo | Módulo Finanzas | Son ajenos a la liquidación de Bingo |

No existe una tabla o modelo de venta/cobro de cartón, pago de premio o gasto de
Bingo. `Aportesemanal` tiene método y referencia de ingreso, pero no tiene un
campo de importe y no se usa para recaudar cartones.

La estructura de `CartonPartidaBingo` no contiene ningún campo monetario. Esto
es correcto: una participación no tiene precio propio.

## 3. Inventario de cálculos existentes

Las categorías de riesgo usadas son: **correcto**, **revisar**, **riesgo de
duplicación** e **incorrecto confirmado**.

| Archivo | Función / vista | Pantalla o reporte | Fuente de datos | Métrica | Riesgo | Hallazgo |
|---|---|---|---|---|---|---|
| `apps/bingos/services.py` | `crear_carton_maestro_para_bingo()` | Venta por Bingo | Cartón maestro | Importe registrado | correcto | Crea un solo `Carton` con un precio y luego participaciones sin importe |
| `apps/bingos/views.py` | `bingo_carton_nuevo()` | “Vender cartón para todo el Bingo” | Formulario y `Bingo.preciocarton` inicial | Valor informativo / venta | revisar | El precio de lista solo es valor inicial; cualquier precio positivo enviado por el formulario puede guardarse y no hay confirmación de cobro |
| `apps/bingos/services.py` | `crear_y_asignar_carton()` | Ruta heredada por partida | Un nuevo `Carton` por llamada | Importe registrado | riesgo de duplicación | No multiplica participaciones, pero repetir el flujo por ronda crea cartones y precios físicos distintos para un concepto que podría ser una sola compra |
| `apps/bingos/views.py` | `bingo_resumen_excel()` | `/bingos/<id>/resumen/excel/` | `Carton.objects.filter(idbingo=bingo)` y participaciones en consulta separada | Fuente para inventario y recaudación | revisar | La consulta directa de cartones evita duplicación por JOIN, pero no filtra vendidos, anulados ni cobros confirmados |
| `apps/bingos/reportes.py` | `construir_resumenes_cartones_bingo()` | Hoja “Cartones del Bingo” | Cartones directos, agrupados por `idcarton` | Inventario único y conteos de rondas | correcto | Omite duplicados de entrada por PK y mantiene una fila por cartón; las participaciones solo alimentan conteos y estados |
| `apps/bingos/reportes.py` | `construir_resumenes_cartones_bingo()` | Hoja “Cartones del Bingo” | Participaciones por cartón | Rondas ganadas, pendientes y activas | correcto | Cuenta estados por participación sin usar esos conteos como multiplicador monetario |
| `apps/bingos/reportes.py` | `_fila_reporte_partida()` | Reportes de ronda | Participación → cartón maestro | Valor informativo `precio_pagado` | riesgo de duplicación | Copia el mismo precio del maestro en cada ronda en la que participa; no suma por sí sola, pero alimenta los subtotales incorrectos |
| `apps/bingos/reportes.py` | `generar_excel_cartones_partida()` | `/partidas/<id>/cartones/excel/` | Filas históricas y participaciones de una ronda | “Total recaudado” | incorrecto confirmado | Suma `fila["precio_pagado"]` para cada participante y presenta el resultado como recaudación; el mismo maestro vuelve a aparecer con su precio en otros Excel de ronda |
| `apps/bingos/reportes.py` | `generar_excel_cartones_partida()` | Excel de ronda | Filas de la ronda | Total, vendidos, anulados y disponibles | revisar | Los conteos son operativos, pero el subtotal monetario incluye todas las filas con precio sin limitarse a una política de venta/pago |
| `apps/bingos/reportes.py` | `generar_excel_resumen_bingo()` — `total_recaudado` | Resumen final de la hoja “Resumen de partidas” | `resumenes_maestros` únicos | Recaudación global registrada | revisar | Deduplica correctamente por cartón, pero suma todo cartón recibido sin filtrar estado de venta ni pago confirmado |
| `apps/bingos/reportes.py` | `generar_excel_resumen_bingo()` — `recaudacion` dentro del bucle de partidas | Columna “Recaudación total” por ronda | Filas de participación de cada ronda | Recaudación por ronda | incorrecto confirmado | Repite el precio del maestro en cada ronda; sumar la columna multiplica la recaudación por el número de participaciones |
| `apps/bingos/reportes.py` | `generar_excel_resumen_bingo()` | Hoja “Cartones del Bingo” | `resumenes_maestros` | Precio e inventario | correcto | Exporta una sola fila monetaria por cartón, aunque el significado continúa siendo importe registrado, no cobro confirmado |
| `apps/bingos/reportes.py` | `generar_pdf_reporte_partida()` | `/partidas/<id>/reporte/pdf/` | Bingo, ronda y participantes | Precio de lista, premio y resultado informativos | correcto | No suma `preciopagado` ni presenta recaudación o utilidad; el precio mostrado es el precio de lista del Bingo |
| `apps/bingos/views.py` | `partida_reporte_pdf()`, `partida_cartones_excel()` y `_consultar_participaciones_reporte()` | Exportaciones de ronda | Históricos por `idpartida` y participaciones únicas | Fuente operativa por ronda | correcto | Mantiene separadas las consultas y valida coherencia; la duplicación monetaria ocurre después, en el generador Excel |
| `apps/bingos/views.py` | `bingo_detalle()` | Detalle administrativo del Bingo | `Carton.idpartida__idbingo` | Listado informativo de precios | revisar | No suma importes, pero omite maestros con `idpartida=NULL`; la pantalla no puede considerarse inventario financiero completo |
| `apps/bingos/views.py` | `cartones_lista()` | Listado general de cartones | Filas físicas de `Carton` | Conteo y precio informativo | correcto | Cada fila física se muestra una vez y no se agregan importes; el conteo no equivale a cartones vendidos |
| `apps/jugadores/views.py` | `_detalle_context()` | Detalle del jugador | Cartones directos con participaciones precargadas | Precio informativo | correcto | Muestra el precio una vez por cartón y el número de rondas por separado |
| `config/views.py` | `home()` / `safe_count(Carton)` | Dashboard principal | Tabla `carton` | “Total de cartones” | revisar | No usa participaciones y no duplica maestros por ronda, pero cuenta todos los estados, todos los Bingos y cartones históricos; no es indicador de ventas |
| `apps/finanzas/views.py` | `dashboard()` | Dashboard de Finanzas | Préstamos, pagos de préstamo, ahorros y aportes | Conteos | correcto | No calcula ingresos, recaudación, premios ni utilidad de Bingo |
| `apps/finanzas/views.py` | listas y detalle de préstamo | Finanzas | `Pago`, `Prestamo`, `Ahorro`, `Aportesemanal` | Valores informativos y conteos | correcto | No se unen con participaciones ni alimentan reportes de Bingo; `Ahorro.idbingo` solo contextualiza el ahorro |
| `DATABASE/00_PREFLIGHT_CARTONES_HIBRIDOS.sql` | consulta 18, `recaudacion_actual` | Diagnóstico SQL manual, no runtime | Cartones históricos unidos por `carton.idpartida` | Recaudación histórica por Bingo | revisar | Suma cada cartón físico una vez y no duplica por participación, pero omite maestros con `idpartida=NULL`; quedó desactualizada para liquidación híbrida |
| `DATABASE/03_VALIDACION_CARTONES_HIBRIDOS.sql` | consulta 3 | Validación SQL propuesta, no runtime | Tabla `carton` directa | Recaudación vendida y suma total histórica | revisar | La suma de vendidos no duplica por participación; la suma total incluye cualquier estado y ambas son globales, no liquidación de un Bingo concreto |
| `apps/bingos/tests.py` | `ReportesAdministrativosTests` | Contrato automatizado de Excel | Datos simulados de una sola ronda | Totales monetarios actuales | riesgo de duplicación | Exige “Total recaudado” en el Excel de ronda y “Recaudación total” por ronda; los escenarios de una sola ronda no revelan multiplicación |
| `apps/bingos/tests.py` | `ReportesHibridosTests` | Contrato híbrido | Un maestro en dos rondas | Inventario y participaciones | revisar | Comprueba que el maestro aparece una sola vez en inventario y en ambas rondas, pero no verifica los importes de esas dos filas ni el total global |

No se encontraron `Sum`, `Count`, `annotate`, `distinct` o `aggregate` del ORM
para calcular recaudación de Bingo. Los dos cálculos monetarios problemáticos
se realizan en Python dentro de `apps/bingos/reportes.py`, después de construir
filas desde participaciones.

Tampoco se encontraron cálculos financieros en JavaScript. El código de tiempo
real solo actualiza estado de juego, bolas y progreso del cartón.

## 4. Cálculos correctos

Son correctos respecto de la regla de no multiplicar por participación:

1. `crear_carton_maestro_para_bingo()` registra el precio únicamente en el
   maestro y crea participaciones sin importe.
2. `construir_resumenes_cartones_bingo()` deduplica por `carton.pk` y produce
   una sola fila de inventario por cartón.
3. La hoja “Cartones del Bingo” exporta el precio una vez por cartón y mantiene
   los conteos de rondas como dimensiones separadas.
4. El `total_recaudado` final de `generar_excel_resumen_bingo()` parte de esos
   resúmenes únicos, por lo que las participaciones no multiplican el importe.
5. Los conteos de participaciones por ronda y estados de participación no se
   usan como multiplicadores monetarios.
6. El PDF de ronda no calcula recaudación ni utilidad. Presenta precio de lista,
   premio mayor, participantes y resultado como datos informativos.
7. Los listados HTML de Bingo, rondas, cartones y jugadores muestran valores de
   cada objeto, pero no suman precios.
8. Los dashboards solo cuentan registros y no calculan ingresos.
9. Los SQL de diagnóstico que suman precios lo hacen directamente desde
   `carton`, nunca desde `carton_partida_bingo`.

La corrección de deduplicación no convierte automáticamente el total global en
“dinero cobrado”. Sigue faltando una política de estados y una confirmación de
pago. La denominación técnicamente defendible hoy es **recaudación registrada**
o **importe registrado en cartones elegibles**.

## 5. Riesgos de duplicación

### 5.1 Columna monetaria por ronda en el resumen del Bingo

`generar_excel_resumen_bingo()` recorre cada ronda, construye una fila por
participación y suma nuevamente `Carton.preciopagado`. La columna resultante se
llama “Recaudación total”, aunque es una repetición del valor de los cartones
que participan en esa ronda.

Con tres maestros de `$5,00` y tres rondas:

| Fila del Excel | Cálculo actual | Valor mostrado |
|---|---:|---:|
| Ronda 1 | 3 participaciones × `$5,00` | `$15,00` |
| Ronda 2 | 3 participaciones × `$5,00` | `$15,00` |
| Ronda 3 | 3 participaciones × `$5,00` | `$15,00` |
| Suma aparente de la columna | `$15,00` × 3 rondas | **`$45,00`** |
| Recaudación registrada correcta | 3 maestros × `$5,00` | **`$15,00`** |

El resumen final del mismo archivo mostraría `$15,00`, pero coexistiría con
filas que suman `$45,00`. Es una contradicción interna y el riesgo prioritario.

### 5.2 Subtotal del Excel de una ronda

`generar_excel_cartones_partida()` suma el precio de cada fila y lo etiqueta
“Total recaudado”. Dentro de una sola ronda la UNIQUE cartón+ronda evita repetir
al mismo maestro, pero el mismo subtotal se vuelve a generar en cada ronda.
Combinar o comparar esos archivos multiplica el ingreso. Además, el cálculo no
exige estado `Vendido` ni confirmación de cobro.

El reporte de ronda debe limitarse a operación: participantes, estados,
ganadores, patrón/índice y premio de la ronda. No debe ofrecer un subtotal que
pueda reutilizarse como liquidación general.

### 5.3 Elegibilidad del total global

El total global deduplica, pero suma todos los cartones recibidos por el
generador. No filtra `estadocarton`, jugador, anulación ni pago confirmado.
Esto no es duplicación por participación, pero puede sobrestimar la recaudación
si un cartón disponible, cerrado o anulado conserva un precio.

Antes de corregirlo debe decidirse qué registros históricos cuentan. La regla
usada en la Fase 1 para operación fue maestro, jugador asignado y estado
`Vendido`; no debe aplicarse retroactivamente a liquidación histórica sin una
decisión expresa.

### 5.4 Flujo heredado por partida

La ruta heredada crea una fila física de `Carton` y un precio por ronda. Si el
administrador la usa tres veces para representar un único derecho de juego,
incluso un cálculo correcto por PK contará tres ventas. Este riesgo no nace de
un JOIN ni de las participaciones: nace de haber registrado tres cartones.

### 5.5 Cobertura de pruebas insuficiente

Las pruebas actuales validan el subtotal de una sola ronda y el total global de
un Bingo de una ronda. La prueba híbrida confirma que un maestro aparece en dos
rondas, pero no verifica que solo aporte su precio una vez. Por eso la suite
actual puede aprobar aunque las filas por ronda multipliquen la recaudación.

## 6. Reportes PDF y Excel

| Reporte | Ruta | Contenido actual | Evaluación financiera | Corrección conceptual |
|---|---|---|---|---|
| PDF de ronda | `/partidas/<id>/reporte/pdf/` | Datos del Bingo y ronda, bolas, participantes y ganador | Sin riesgo de duplicación: no suma precios | Mantenerlo como reporte operativo; si se agrega premio de ronda, mostrarlo una vez y no calcular liquidación |
| Excel de cartones de ronda | `/partidas/<id>/cartones/excel/` | Históricos, participaciones, precio por fila, estados y “Total recaudado” | Incorrecto confirmado como fuente de recaudación | Eliminar el subtotal monetario; mantener conteos y resultados. Si se conserva el precio individual, marcarlo como informativo y no liquidable |
| Excel resumen de Bingo | `/bingos/<id>/resumen/excel/` | Resumen por rondas e inventario único | Mixto: total final deduplicado; columna por ronda incorrecta | Usar una única sección financiera basada en cartones únicos y retirar “Recaudación total” de las filas de ronda |

Los accesos a estos archivos están en `templates/bingos/detalle.html` y
`templates/bingos/partida_detalle.html`. No existe una pantalla separada de
liquidación ni un PDF de liquidación.

Los premios no se descuentan en ninguno de los reportes actuales. El PDF
muestra `Bingo.premiomayor`, y las pantallas muestran
`Partidabingo.valorefectivo`, pero no hay cálculo de premio pagado, utilidad
bruta o utilidad neta.

## 7. Dashboard administrativo

El dashboard principal (`config/views.py::home`) muestra un conteo global de
filas de `Carton`. No consulta participaciones y, por tanto, no multiplica un
maestro por sus rondas. Sin embargo, “Total de cartones” incluye todos los
estados, todos los Bingos y cartones históricos; no debe interpretarse como
“cartones vendidos”.

El dashboard de Finanzas muestra conteos de préstamos activos, pagos de
préstamo pendientes, ahorros y aportes atrasados. No muestra ingresos, ventas,
recaudación, premios o utilidad de Bingo.

No se encontró otro dashboard o indicador monetario relacionado con Bingo.

## 8. Modelo financiero disponible

| Concepto | ¿Puede calcularse hoy? | Alcance defendible |
|---|---|---|
| Cartones registrados | Sí | Conteo de filas físicas únicas de `Carton` por Bingo |
| Cartones vendidos | Parcialmente | Puede filtrarse por estado `Vendido`, pero falta política histórica y confirmación de cobro |
| Recaudación registrada | Sí, con condición | Suma de `Carton.preciopagado` una vez por cartón elegible del Bingo; no es prueba de dinero cobrado |
| Recaudación efectivamente cobrada | No | No existe estado, transacción, método ni confirmación de pago del cartón |
| Premio programado por ronda | Sí | `Partidabingo.valorefectivo`, una vez por ronda |
| Premio material | Solo descriptivo | No tiene valor monetario registrado |
| Premio monetario efectivamente pagado | No | No existe registro de entrega/pago; ganador y finalización no demuestran desembolso |
| Premio mayor programado | Sí | `Bingo.premiomayor`, pero falta definir si es adicional o corresponde a una ronda |
| Utilidad bruta | No de forma contable | Solo podría estimarse tras definir ingresos elegibles y qué premios programados/otorgados deben descontarse |
| Gastos | No | No existe fuente de gastos de Bingo |
| Utilidad neta | No | Faltan gastos y estados de cobro/pago |

Mientras no exista una fuente física de gastos, cualquier reporte debe decir:

> Gastos adicionales: no registrados en el sistema.

No debe mostrarse utilidad neta. Tampoco debe restarse automáticamente
`Bingo.premiomayor` y todos los `Partidabingo.valorefectivo` sin decidir si son
premios diferentes y cuáles fueron realmente otorgados.

## 9. Propuesta de corrección por prioridad

### Correcciones obligatorias

1. Crear un único cálculo puro de recaudación registrada desde cartones únicos
   del Bingo, nunca desde participaciones.
2. Eliminar la columna “Recaudación total” de las filas por ronda de
   `generar_excel_resumen_bingo()` o reemplazarla por una métrica no monetaria.
3. Eliminar “Total recaudado” de `generar_excel_cartones_partida()`.
4. Mantener una sola sección financiera del Bingo con una fila por cartón y un
   total global deduplicado.
5. Agregar pruebas con varias rondas que hagan visible la diferencia `$15` vs.
   `$45`.
6. Denominar el total “recaudación registrada” mientras no haya pago confirmado.

### Correcciones recomendables

1. Definir explícitamente qué estados de cartón entran al total.
2. Decidir cómo se incluyen cartones históricos por partida sin convertirlos
   ni duplicarlos.
3. Añadir una nota visible en los reportes de ronda: “Este reporte no es una
   liquidación general del Bingo”.
4. Distinguir en el dashboard “cartones registrados” de “cartones vendidos”.
5. Revisar `DATABASE/00_PREFLIGHT_CARTONES_HIBRIDOS.sql` antes de volver a usar
   su consulta histórica de recaudación; actualmente no contempla maestros.

### Mejoras futuras

1. Diseñar, si el negocio lo exige, una entidad propia de venta/cobro de cartón
   con método, referencia, confirmación y anulación.
2. Diseñar el registro de pago/entrega de premios.
3. Diseñar gastos de Bingo antes de ofrecer utilidad neta.
4. Crear una pantalla de liquidación separada de los reportes operativos por
   ronda.

### Cambios que requieren aprobación de PostgreSQL

La corrección inmediata de los Excel no requiere cambios de esquema. Sí
requieren autorización separada y ensayo previo:

- una tabla o columnas para venta/pago confirmado de cartones;
- una tabla de gastos de Bingo;
- una entidad de pago o entrega de premios;
- nuevos `CHECK` de estados o importes;
- cualquier backfill o cambio del tratamiento histórico.

`Pago` no debe reutilizarse: corresponde a préstamos/deudas y su contrato físico
auditado no coincide con el modelo Django actual.

## 10. Plan de pruebas para la siguiente fase

Las pruebas deben seguir el estilo actual de `SimpleTestCase`, con objetos y
consultas simuladas, sin conectar a `bingo` ni a la base de ensayo.

1. **Un maestro, tres rondas:** un cartón de `$5,00` con tres participaciones
   aporta exactamente `$5,00` al total global.
2. **Tres maestros, tres rondas:** tres cartones de `$5,00` producen `$15,00`,
   nunca `$45,00`.
3. **Reporte por ronda no liquida:** el Excel de una ronda no contiene “Total
   recaudado” ni expone un subtotal reutilizable como liquidación general.
4. **Aislamiento entre Bingos:** un cartón y sus participaciones de otro Bingo
   no afectan conteo ni recaudación.
5. **Premio por ronda:** cada `Partidabingo.valorefectivo` elegible se considera
   como máximo una vez, aunque existan múltiples ganadores o participaciones.
   El criterio “elegible/pagado” debe aprobarse antes de implementar el descuento.
6. **Sin gastos:** el reporte indica “Gastos adicionales: no registrados en el
   sistema.” y no calcula utilidad neta.
7. **Fuente correcta por formato:** el PDF de ronda permanece operativo y sin
   recaudación; el Excel de ronda usa participaciones para conteos/resultados;
   el Excel global usa cartones únicos para importes.
8. **Participación repetida en entrada:** el constructor rechaza dos
   participaciones del mismo cartón y ronda sin alterar el total.
9. **Estados no vendibles:** disponible, anulado, cerrado, precio nulo y precio
   cero se prueban por separado según la política que autorice el usuario.
10. **Históricos:** un cartón histórico físico se cuenta como máximo una vez y
    no se expande artificialmente a otras rondas.
11. **Coherencia interna del libro:** la única cifra global de recaudación
    coincide con la suma de las filas únicas de “Cartones del Bingo”.
12. **Regresión de rutas y permisos:** las tres descargas siguen resolviendo y
    continúan restringidas a administración.

No debe escribirse una prueba que asuma que `preciopagado` equivale a pago
confirmado o que invente gastos inexistentes.

## 11. Siguiente cambio de código recomendado

El primer cambio real debe concentrarse en
`apps/bingos/reportes.py::generar_excel_resumen_bingo()` y sus pruebas:

1. introducir un cálculo único sobre cartones deduplicados;
2. fijar con pruebas el escenario de tres maestros y tres rondas;
3. retirar la cifra monetaria de cada fila de ronda;
4. conservar la sección de inventario como fuente de conciliación.

Es el cambio prioritario porque el mismo archivo entrega hoy un total global
correctamente deduplicado y, al mismo tiempo, tres o más subtotales de ronda que
repiten los mismos importes. Después debe corregirse
`generar_excel_cartones_partida()` para eliminar su subtotal monetario.

Archivos previstos para la siguiente fase, sin autorizar todavía su edición:

- `apps/bingos/reportes.py`;
- `apps/bingos/tests.py`;
- `apps/bingos/views.py`, solo si se centraliza allí el filtro de cartones
  elegibles;
- `templates/bingos/detalle.html` y
  `templates/bingos/partida_detalle.html`, únicamente para aclarar el propósito
  operativo de las exportaciones.

No se recomienda empezar por modelos ni SQL. El esquema físico actual ya
permite evitar la duplicación consultando cartones únicos.
