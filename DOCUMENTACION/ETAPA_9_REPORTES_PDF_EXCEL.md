# Etapa 9 - Reportes administrativos PDF y Excel

## Objetivo

Agregar reportes descargables para administradores de SIAB / CoopBingo sin
modificar la estructura de PostgreSQL ni guardar cambios al generar archivos.

Todos los reportes son administrativos y usan `admin_required`.

## Dependencias usadas

Se agregaron a `.venv` y `requirements.txt`:

- `openpyxl==3.1.5` para archivos Excel `.xlsx`.
- `reportlab==5.0.0` para archivos PDF.
- `et-xmlfile==2.0.0`, dependencia de `openpyxl`.
- `charset-normalizer==3.4.7`, dependencia de `reportlab`.

No se usa LibreOffice, navegador, Docker, Redis, Celery ni servicios externos
para generar reportes.

## Reportes implementados

### 1. Reporte PDF de partida

Ruta:

```text
/partidas/<idpartidabingo>/reporte/pdf/
```

Archivo:

```text
reporte_partida_<idpartidabingo>.pdf
```

Incluye:

- encabezado SIAB;
- fecha y hora de generacion;
- datos del Bingo;
- datos de la partida;
- cantidad de bolas extraidas y restantes;
- ultima bola;
- listado de bolas extraidas en orden;
- estado de desempate;
- balota mayor de desempate cuando existe;
- ganador y carton ganador solo si la partida esta finalizada.

Si la partida no esta finalizada, el reporte indica:

```text
La partida aún no está finalizada.
```

No inventa ganador.

### 2. Excel de cartones de una partida

Ruta:

```text
/partidas/<idpartidabingo>/cartones/excel/
```

Archivo:

```text
cartones_partida_<idpartidabingo>.xlsx
```

Hoja:

```text
Cartones
```

Columnas:

- ID de cartón;
- Código de cartón;
- Jugador;
- Estado del cartón;
- Fecha de compra;
- Precio pagado;
- Índice de victoria;
- ID de partida;
- Nombre de ronda;
- Estado de partida.

Resumen final:

- total de cartones;
- total recaudado;
- cartones vendidos;
- cartones anulados;
- cartones disponibles.

### 3. Excel resumen de Bingo

Ruta:

```text
/bingos/<idbingo>/resumen/excel/
```

Archivo:

```text
resumen_bingo_<idbingo>.xlsx
```

Hoja:

```text
Resumen de partidas
```

Columnas:

- ID de Bingo;
- Título del Bingo;
- ID de partida;
- Ronda;
- Estado de partida;
- Fecha programada;
- Hora de inicio;
- Hora de finalización;
- Total de cartones;
- Recaudación total;
- Cantidad de bolas extraídas;
- Ganador;
- Hubo desempate;
- Balota mayor de desempate.

Resumen global:

- total de partidas;
- partidas finalizadas;
- partidas en curso;
- total de cartones;
- recaudación total;
- total de partidas con desempate.

## Datos excluidos por seguridad

Los reportes no incluyen:

- contraseñas;
- hashes;
- datos de `auth_user`;
- correos de jugadores;
- `idbingadores` crudo;
- JSON interno;
- tiros individuales de desempate;
- datos privados de cartones ajenos innecesarios;
- controles administrativos o acciones operativas.

## Implementación

La lógica de generación vive en:

```text
apps/bingos/reportes.py
```

Ese módulo:

- construye datos seguros de reporte de partida;
- genera PDF con ReportLab;
- genera Excel con openpyxl;
- calcula totales en memoria;
- da formato monetario y de fecha;
- genera nombres seguros de archivo;
- reutiliza funciones existentes de bolas y estados.

Las vistas en `apps/bingos/views.py` solo recuperan datos en modo lectura,
llaman al generador y devuelven un `HttpResponse` con `Content-Disposition:
attachment`.

## Interfaz administrativa

En el detalle de una partida:

- `Descargar reporte PDF`;
- `Exportar cartones`.

En el detalle de un Bingo:

- `Exportar resumen`.

Los botones solo aparecen en templates administrativos ya protegidos. No se
agregaron botones en sala publica, tablero publico, consulta publica de carton
ni `Mis cartones`.

## Protección

Todas las rutas nuevas usan `admin_required`:

- visitante anonimo: redirigido a login;
- usuario autenticado no staff: 403;
- jugador autenticado: 403;
- staff o superusuario: descarga permitida.

Generar un reporte no ejecuta `save()`, `update()`, `delete()` ni crea datos.

## Validación y pruebas

Se agregaron pruebas en `apps/bingos/tests.py` para:

- acceso anonimo, usuario normal, jugador, staff y superusuario;
- `Content-Type` de PDF y Excel;
- `Content-Disposition` con `attachment`;
- nombres de archivo con el ID esperado;
- firma `%PDF`;
- apertura real de Excel con `openpyxl.load_workbook`;
- hojas `Cartones` y `Resumen de partidas`;
- encabezados obligatorios;
- totales y recaudación;
- ausencia de columnas privadas;
- no llamar `save()` al generar reportes;
- no cambiar estado, bolas, ganador ni cartones;
- ganador en partida finalizada;
- mensaje para partida no finalizada;
- desempate resumido sin exponer `idbingadores`.

## Limitaciones actuales

Los reportes se generan de forma síncrona durante la petición HTTP. Esto es
suficiente para volúmenes pequeños o medianos.

Para reportes muy grandes, una etapa futura podría integrar Celery para generar
archivos en segundo plano, guardar el resultado en almacenamiento controlado y
notificar al administrador cuando la descarga esté lista. Esa integración no se
implementa en esta etapa.
