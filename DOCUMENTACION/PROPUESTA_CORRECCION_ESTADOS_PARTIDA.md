# Propuesta de correccion de estados de Partidabingo

Fecha de diagnostico: 2026-06-27.

## Alcance

Este documento prepara la correccion consistente de `partidabingo.estadopartida`.
No se ejecutaron cambios sobre PostgreSQL, no se borraron datos, no se crearon
tablas y no se generaron migraciones.

## Estado actual de la tabla

Tabla: `public.partidabingo`.

Columna relevante:

- `estadopartida`: `character varying(20)`, `NOT NULL`, sin default.

Restriccion CHECK actual:

```sql
chk_partidabingo_estadopartida
CHECK (
    estadopartida IN ('En Juego', 'Verificando', 'Desempate', 'Finalizada')
)
```

Valores existentes encontrados en este entorno al diagnosticar:

| estadopartida | cantidad |
| --- | ---: |
| Finalizada | 2 |

No se encontraron valores fuera de la restriccion actual.

## Estados requeridos por la aplicacion

La aplicacion SIAB / CoopBingo necesita manejar estos estados reales:

- `Programada`
- `En espera`
- `En curso`
- `Pausada`
- `Desempate`
- `Finalizada`
- `Cancelada`

## Por que el mapeo temporal no es correcto

El mapeo temporal usado como compatibilidad:

- `Programada -> Verificando`
- `En espera -> Verificando`
- `En curso -> En Juego`

no es correcto a largo plazo porque pierde informacion funcional:

- `Programada` y `En espera` terminan guardadas como `Verificando`, aunque representan momentos distintos.
- `En curso` se guarda como `En Juego`, mezclando vocabulario antiguo y nuevo.
- `Pausada` y `Cancelada` no tienen equivalente persistible bajo la CHECK actual.
- La consola puede calcular transiciones con estados nuevos, pero PostgreSQL rechaza los valores que no estan en la restriccion.
- Las pruebas con `save()` simulado no detectan la restriccion real de la base.
- Guardar estados en campos ajenos como `bolascantadas`, `ultimabola` o JSON improvisado seria incorrecto porque `estadopartida` es el campo natural del estado.

## Impacto funcional actual

Mientras la CHECK antigua siga activa:

- Crear una partida como `Programada` falla si Django intenta guardar el valor real.
- Iniciar una partida hacia `En curso` falla si se guarda el valor real.
- Pausar una partida hacia `Pausada` falla siempre.
- Cancelar una partida hacia `Cancelada` falla siempre.
- La interfaz puede mostrar estados normalizados, pero la persistencia queda incompleta.

## Plan de migracion de datos antiguos

Antes de instalar la nueva CHECK, los valores antiguos deben transformarse a los
estados reales:

- `En Juego -> En curso`
- `Verificando -> En espera`
- `Desempate -> Desempate`
- `Finalizada -> Finalizada`

Despues de actualizar los datos, la CHECK debe permitir exactamente:

- `Programada`
- `En espera`
- `En curso`
- `Pausada`
- `Desempate`
- `Finalizada`
- `Cancelada`

Cambiar solo una restriccion CHECK no borra registros, no agrega columnas, no
elimina columnas y no crea tablas. El cambio propuesto modifica la regla de
validacion de valores permitidos y actualiza valores textuales existentes en la
misma columna.

## Riesgos

- Si existen procesos escribiendo partidas durante el cambio, pueden fallar por
la ventana de transaccion o por bloqueo de la tabla.
- Si hay valores inesperados no detectados, la nueva CHECK fallara al crearse.
- Revertir despues de confirmar la migracion puede ser con perdida de
informacion, porque varios estados nuevos no existen en el vocabulario antiguo.
- Si el codigo Django se despliega antes de ejecutar SQL, las acciones que
requieren estados nuevos deben quedar bloqueadas o mostrar un mensaje claro.

## Plan de reversión

Antes de confirmar la transaccion:

- Ejecutar `ROLLBACK;` en lugar de `COMMIT;`.

Despues de confirmar:

- Se puede reinstalar la CHECK antigua y mapear valores nuevos a valores legacy,
pero es una reversión con perdida de informacion:
  - `En curso -> En Juego`
  - `En espera -> Verificando`
  - `Programada -> Verificando`
  - `Pausada -> En Juego`
  - `Cancelada -> Finalizada` o una decision manual operativa

Por esa razon se recomienda respaldar el resultado de:

```sql
SELECT idpartidabingo, estadopartida
FROM partidabingo
ORDER BY idpartidabingo;
```

antes de ejecutar la migracion.

## Validaciones necesarias

Antes:

- Confirmar el nombre real de la CHECK:
  `chk_partidabingo_estadopartida`.
- Confirmar distribucion de valores actuales.
- Confirmar que no hay valores fuera del conjunto legacy.

Durante:

- Ejecutar el script dentro de una transaccion explicita.
- Actualizar valores legacy antes de crear la nueva CHECK.

Despues:

- Confirmar que solo existen estados nuevos permitidos.
- Confirmar que la CHECK nueva contiene exactamente los siete estados reales.
- Confirmar que Django detecta los siete estados como persistibles.
- Probar en Django:
  - crear partida `Programada`;
  - iniciar hacia `En curso`;
  - pausar hacia `Pausada`;
  - reanudar hacia `En curso`;
  - finalizar hacia `Finalizada`;
  - cancelar hacia `Cancelada` cuando se habilite la accion de cancelacion.

Comando de verificacion no destructivo posterior al SQL:

```bash
python manage.py shell -c "from apps.bingos.views import _base_datos_permite_estado_partida; estados=['Programada','En espera','En curso','Pausada','Desempate','Finalizada','Cancelada']; print({estado: _base_datos_permite_estado_partida(estado) for estado in estados})"
```

El resultado esperado es que todos los estados devuelvan `True`.

Comprobacion SQL posterior:

```sql
SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid = 'partidabingo'::regclass
  AND conname = 'chk_partidabingo_estadopartida';

SELECT estadopartida, COUNT(*)
FROM partidabingo
GROUP BY estadopartida
ORDER BY estadopartida;
```

Prueba funcional posterior:

1. Crear una partida con estado `Programada`.
2. Abrir la consola.
3. Iniciar la partida y confirmar `En curso`.
4. Pausar y confirmar `Pausada`.
5. Reanudar y confirmar `En curso`.
6. Finalizar y confirmar `Finalizada`.

## Archivos relacionados en Django

- `apps/bingos/models.py`: `Partidabingo.estadopartida` es `CharField(max_length=20)`, sin `choices`, `blank` ni `null`.
- `apps/bingos/services.py`: centraliza estados y transiciones.
- `apps/bingos/forms.py`: formulario de partida.
- `apps/bingos/views.py`: consola del operador y guardado.
- `templates/bingos/consola_operador.html`: botones y estado visual.
- `templates/bingos/partidas_lista.html`, `templates/bingos/partida_detalle.html`, `templates/bingos/detalle.html`: visualizacion de estados.

## SQL preparado

El script revisable queda en:

```text
DATABASE/actualizar_estados_partidabingo.sql
```

No debe ejecutarse automaticamente. Debe revisarlo y ejecutarlo manualmente el
administrador de base de datos cuando apruebe la correccion.

## Estado del codigo mientras el SQL no se aplique

El codigo queda preparado para persistir los siete estados reales. Mientras la
CHECK antigua siga activa, la consola bloquea las acciones cuyo estado destino
no sea aceptado por PostgreSQL y muestra un mensaje indicando que debe aplicarse
`DATABASE/actualizar_estados_partidabingo.sql`.

La compatibilidad con estados antiguos queda solo para lectura y visualizacion:

- `En Juego` se muestra e interpreta como `En curso`.
- `Verificando` se muestra e interpreta como `En espera`.

No se guardan estados en campos alternos ni se mantiene el mapeo temporal de
persistencia.
