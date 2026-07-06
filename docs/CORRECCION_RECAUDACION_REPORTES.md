# Corrección de Recaudación Duplicada en Reportes Excel

Fecha: 2026-07-05
Fase: 2B — corrección de reportes, sin cambios de PostgreSQL

## 1. Problema corregido: $15 versus $45

Un cartón maestro pertenece a un Bingo y tiene un único precio registrado en
`Carton.preciopagado`. Cada fila de `CartonPartidaBingo` representa solo la
participación de ese cartón en una ronda; no contiene precio ni constituye una
venta adicional.

El código anterior recorría las participaciones de cada ronda y sumaba
`preciopagado` del cartón maestro por cada una. Si tres cartones de $5 cada uno
participaban en tres rondas, el resumen mostraba:

| Ronda | Cálculo antiguo | Valor mostrado |
|---|---:|---:|
| Ronda 1 | 3 participaciones × $5 | $15 |
| Ronda 2 | 3 participaciones × $5 | $15 |
| Ronda 3 | 3 participaciones × $5 | $15 |
| **Suma aparente** | | **$45** |
| **Recaudación registrada correcta** | 3 maestros × $5 | **$15** |

## 2. Cartón maestro versus participación

| Concepto | Entidad | Tiene precio | Representa venta |
|---|---|---|---|
| Cartón maestro | `Carton` con `idbingo` y `idpartida IS NULL` | Sí: `preciopagado` | Sí: una sola compra |
| Participación | `CartonPartidaBingo` | No | No: solo derecho de juego |

Un cartón maestro se compra una vez para todo el Bingo. Las participaciones
solo registran el resultado de ese cartón en cada ronda. Sumar dinero desde
participaciones equivale a cobrar varias veces la misma compra.

## 3. Fuente de datos de la recaudación

La recaudación registrada se calcula exclusivamente desde cartones maestros
únicos, utilizando la nueva función `calcular_recaudacion_registrada()` en
`apps/bingos/reportes.py`.

La función:

- recibe cartones maestros o diccionarios de resumen;
- deduplica explícitamente por `idcarton` o `pk`;
- ignora precios `NULL`;
- no recorre participaciones para sumar dinero;
- mantiene la política histórica actual de elegibilidad;
- no filtra retroactivamente por `Vendido`, `Confirmado` o `Pagado`;
- devuelve un `Decimal` coherente con el código actual.

## 4. Cómo se deduplican cartones

```python
vistos = set()
total = Decimal("0.00")
for item in cartones_o_resumenes:
    pk = item.get("idcarton") or item.get("pk")  # dict o modelo
    if pk in vistos:
        continue          # ya contabilizado
    vistos.add(pk)
    precio = item.get("precio_pagado")
    if precio in (None, ""):
        continue          # no incrementa el total
    total += Decimal(str(precio))
```

Un cartón que aparece más de una vez (por ejemplo, al pasar por varias rondas)
solo suma su precio la primera vez.

## 5. Cambios al Excel de ronda

| Elemento | Antes | Después |
|---|---|---|
| Encabezado de columna de precio | "Precio pagado" | "Importe registrado del cartón" |
| "Total recaudado" en resumen | Sumaba precios de todas las filas | **Eliminado** |
| Subtotal monetario | Presente | **Eliminado** |
| Nota operativa | No existía | **Agregada**: "Este reporte es operativo por ronda y no representa la liquidación general del Bingo." |
| Información operativa | Participantes, estado, ganadores, patrón, premio | **Conservada** |
| Conteos (total, vendidos, anulados, disponibles) | Presentes | **Conservados** |

## 6. Cambios al Excel resumen del Bingo

| Elemento | Antes | Después |
|---|---|---|
| Columna "Recaudación total" por ronda | Presente; repetía precio por participación | **Eliminada** |
| Cifra monetaria por ronda | Presente | **Eliminada** (sin reemplazo monetario por ronda) |
| Sección financiera global | "Recaudación total" en el resumen final | **Renombrada** a "Recaudación registrada" |
| Cálculo de la cifra global | `sum()` sobre resúmenes de maestros | `calcular_recaudacion_registrada()` sobre maestros únicos |
| Métricas operativas por ronda | Participantes, patrón, estado, ganadores, premio | **Conservadas** |
| Nota sobre recaudación | No existía | **Agregada**: "La recaudación registrada se calcula una sola vez por cartón maestro. Las participaciones por ronda no representan ventas adicionales." |
| Nota sobre gastos | No existía | **Agregada**: "Gastos adicionales: no registrados en el sistema." |
| Utilidad bruta/neta | No existía | No calculada (no se agregó) |
| Descuento automático de premios | No existía | No implementado |

## 7. Límites financieros actuales

- `Carton.preciopagado` no equivale a dinero cobrado; no existe confirmación
  de pago.
- No hay entidad de venta/pago de cartón, solo un precio registrado.
- No hay fuente de gastos de Bingo; el reporte lo indica explícitamente.
- No se calcula utilidad bruta ni utilidad neta.
- Los premios programados (`Partidabingo.valorefectivo`) no se descuentan
  automáticamente.
- `Pago` pertenece a préstamos/deudas y no se reutiliza para cartones.

## 8. Pruebas realizadas

### Pruebas nuevas (RecaudacionRegistradaDuplicacionTests)

| # | Prueba | Resultado |
|---:|---|---|
| 1 | Un cartón maestro de $5 con tres participaciones aporta $5 | ✓ |
| 2 | Tres cartones maestros de $5 con tres rondas producen $15, no $45 | ✓ |
| 3 | El Excel de ronda no contiene "Total recaudado" | ✓ |
| 4 | El Excel de ronda contiene la nota operativa | ✓ |
| 5 | El Excel resumen no muestra columna monetaria repetida por ronda | ✓ |
| 6 | El Excel resumen muestra "Recaudación registrada" una sola vez | ✓ |
| 7 | Un cartón de otro Bingo no afecta el total | ✓ |
| 8 | Un precio NULL no rompe el cálculo ni incrementa el total | ✓ |
| 9 | Varias participaciones del mismo cartón no multiplican su importe | ✓ |
| 10 | Los reportes existentes sin riesgo continúan funcionando | ✓ |
| 11 | Nota de gastos adicionales presente en resumen | ✓ |
| 12 | Nota de recaudación por cartón maestro presente en resumen | ✓ |

### Pruebas existentes actualizadas

| Prueba | Cambio |
|---|---|
| `test_excel_cartones_contiene_headers_resumen_y_no_privados` | Espera "Importe registrado del cartón" y no "Total recaudado" |
| `test_excel_resumen_bingo_contiene_headers_resumen_y_no_privados` | Espera "Recaudación registrada" y no "Recaudación total" |
| `test_excel_resumen_muestra_inventario_unico_y_rondas` | Verifica que no existe columna "Recaudación total" por ronda |

### Ejecución completa

| Comando | Resultado |
|---|---|
| `.venv/bin/python manage.py check` | `System check identified no issues (0 silenced)` |
| Pruebas de reportes (35 tests) | 35 aprobadas |
| Suite completa (303 tests) | 303 aprobadas, 0 fallos |
| `git diff --check` | Sin errores de espacios |

## 9. Archivos modificados

| Archivo | Tipo de cambio |
|---|---|
| `apps/bingos/reportes.py` | Función nueva, corrección de dos generadores Excel |
| `apps/bingos/tests.py` | Importación nueva, 3 pruebas actualizadas, 12 pruebas nuevas |
| `docs/CORRECCION_RECAUDACION_REPORTES.md` | Documento nuevo |

No se modificó `apps/bingos/views.py`, plantillas ni otros archivos.

## 10. Pendientes posteriores

1. Definir qué estados de cartón representan una venta válida para filtrar la
   recaudación registrada (`Vendido`, `Disponible`, `Cerrado`, etc.).
2. Crear una entidad propia de venta/cobro de cartón con método, referencia y
   confirmación, si el negocio lo exige.
3. Decidir si los premios programados deben descontarse para mostrar utilidad
   bruta, y si necesitan un registro de entrega/pago.
4. Crear un soporte de gastos de Bingo antes de ofrecer utilidad neta.
5. Revisar las consultas SQL de diagnóstico en `DATABASE/` que todavía suman
   recaudación histórica por `carton.idpartida`.
6. Separar la pantalla de liquidación de los reportes operativos por ronda.
7. Decidir el tratamiento de cartones históricos por partida en reportes
   financieros.
8. Evaluar si se necesita un reporte PDF de liquidación general del Bingo.

## 11. Cambios de PostgreSQL realizados

Ninguno. No se modificaron modelos, migraciones, tablas, columnas, índices ni
restricciones. La base real `bingo` no fue consultada ni alterada.
