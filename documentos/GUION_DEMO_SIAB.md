# Guion de demo - SIAB

Este guion está pensado para presentar el sistema en pantalla de forma ordenada. La idea es avanzar desde la administración general, pasar por socios y finanzas, y cerrar con la operación del Bingo en tiempo real y el cierre financiero.

## 1. Abrir Inicio

**Qué debo hacer en pantalla:** iniciar sesión como usuario administrativo y abrir la ruta de Inicio.

**Qué debo decir:** "Empiezo desde el Inicio porque SIAB no es una pantalla aislada de Bingo. Es un sistema con módulos administrativos conectados: socios, jugadores, Bingos, finanzas y configuración."

**Qué parte técnica estoy defendiendo:** autenticación, separación entre usuario administrativo y jugador, navegación por módulos.

**Pregunta posible del ingeniero:** "¿Cualquier usuario puede entrar al Inicio?"

**Respuesta:** "No. El Inicio administrativo usa protección para staff o superusuario. Un jugador entra a su panel de cartones, y un visitante solo ve la sala pública o consulta de cartón."

## 2. Mostrar dashboard

**Qué debo hacer en pantalla:** mostrar las tarjetas de resumen y los accesos rápidos.

**Qué debo decir:** "Aquí el sistema resume entidades principales como socios, jugadores, Bingos, préstamos, cartones y aportes. No es una liquidación financiera, sino un tablero administrativo para ubicarse rápidamente."

**Qué parte técnica estoy defendiendo:** dashboard de lectura, contadores seguros, navegación modular.

**Pregunta posible del ingeniero:** "¿El total de cartones equivale a dinero recaudado?"

**Respuesta:** "No. Ese contador solo cuenta registros. La recaudación se calcula en el módulo financiero del Bingo, usando cartones maestros vendidos y evitando multiplicar por rondas."

## 3. Mostrar Socios

**Qué debo hacer en pantalla:** entrar al módulo `Socios` desde el menú.

**Qué debo decir:** "El módulo de socios centraliza la información de los miembros de la organización. Desde aquí puedo buscar, registrar, editar y entrar al detalle de un socio."

**Qué parte técnica estoy defendiendo:** CRUD administrativo protegido, búsqueda, paginación y modelo `Socio` mapeado a PostgreSQL.

**Pregunta posible del ingeniero:** "¿Los socios y jugadores son lo mismo?"

**Respuesta:** "No necesariamente. Un jugador puede estar vinculado a un socio, pero también puede existir como jugador independiente. Por eso el modelo de jugador tiene socio opcional."

## 4. Entrar a un socio

**Qué debo hacer en pantalla:** abrir el detalle de un socio.

**Qué debo decir:** "En el detalle del socio se ve que SIAB lo maneja como una entidad administrativa completa. No solo guarda datos personales, también conecta cuentas, ahorros, aportes y préstamos."

**Qué parte técnica estoy defendiendo:** consulta relacionada entre `Socio`, `Cuentabancaria`, `Ahorro`, `Aportesemanal` y `Prestamo`.

**Pregunta posible del ingeniero:** "¿Esto está en una sola tabla?"

**Respuesta:** "No. El socio es la entidad principal, pero la información financiera está separada en tablas relacionadas. Eso permite mantener orden y evitar mezclar conceptos."

## 5. Mostrar cuentas bancarias

**Qué debo hacer en pantalla:** abrir la pestaña de cuentas bancarias del socio.

**Qué debo decir:** "Aquí se registran cuentas bancarias asociadas al socio, con banco, número, tipo, estado y marca de cuenta principal."

**Qué parte técnica estoy defendiendo:** relación socio-cuenta bancaria, validación de número único y control de cuenta principal.

**Pregunta posible del ingeniero:** "¿Qué evita que se repita una cuenta?"

**Respuesta:** "El formulario valida unicidad y el modelo respeta las restricciones físicas de la base. Si se intenta repetir, el sistema muestra un error controlado."

## 6. Mostrar ahorro activo

**Qué debo hacer en pantalla:** abrir la pestaña de ahorros.

**Qué debo decir:** "Los ahorros se separan de otros movimientos. El sistema muestra el total de ahorro activo, y ese valor se usa para calcular capacidad de garantes en préstamos."

**Qué parte técnica estoy defendiendo:** `Ahorro`, estado activo, suma de ahorro activo y uso en reglas de préstamo.

**Pregunta posible del ingeniero:** "¿El ahorro se mezcla con aportes?"

**Respuesta:** "No. Ahorros y aportes semanales son módulos separados. El ahorro activo tiene uso financiero para capacidad de garante."

## 7. Mostrar aportes semanales

**Qué debo hacer en pantalla:** abrir la pestaña de aportes semanales.

**Qué debo decir:** "Los aportes semanales tienen semana, estado, fechas y un regalo asociado. La pantalla también muestra el valor del regalo asociado para que el aporte tenga contexto económico."

**Qué parte técnica estoy defendiendo:** separación de `Aportesemanal`, relación con `Regalo`, validación de semana y valor del regalo.

**Pregunta posible del ingeniero:** "¿El aporte semanal aumenta el ahorro?"

**Respuesta:** "No automáticamente. Se manejó separado para no mezclar conceptos: ahorro es una base financiera del socio; aporte semanal está relacionado con la dinámica de aportes y regalos."

## 8. Mostrar préstamos del socio

**Qué debo hacer en pantalla:** abrir la pestaña de préstamos del socio.

**Qué debo decir:** "Aquí se ven los préstamos asociados al socio, con monto solicitado, saldo pendiente, fechas y estado. Esto conecta el perfil del socio con el módulo financiero."

**Qué parte técnica estoy defendiendo:** relación `Prestamo` con `Socio`, saldo pendiente y estado.

**Pregunta posible del ingeniero:** "¿El saldo se edita manualmente?"

**Respuesta:** "Se reforzó para que el saldo no se modifique manualmente desde edición. El saldo baja mediante pagos registrados por el servicio de pagos."

## 9. Ir a Finanzas

**Qué debo hacer en pantalla:** entrar al módulo `Finanzas`.

**Qué debo decir:** "Finanzas concentra préstamos, pagos, ahorros y aportes. Aquí se separa claramente la administración financiera de socios de la operación del Bingo."

**Qué parte técnica estoy defendiendo:** módulo financiero protegido, dashboard financiero y separación de responsabilidades.

**Pregunta posible del ingeniero:** "¿Finanzas calcula la utilidad del Bingo?"

**Respuesta:** "La utilidad del Bingo se calcula dentro del panel financiero del Bingo. Este módulo maneja finanzas del socio: préstamos, pagos, ahorros y aportes."

## 10. Mostrar préstamos

**Qué debo hacer en pantalla:** abrir el listado de préstamos.

**Qué debo decir:** "El listado permite buscar préstamos por socio, cédula, nombre o estado. Cada préstamo mantiene monto solicitado, total a pagar, saldo y vencimiento."

**Qué parte técnica estoy defendiendo:** consulta, búsqueda, paginación y modelo `Prestamo`.

**Pregunta posible del ingeniero:** "¿Qué regla tiene el vencimiento?"

**Respuesta:** "El vencimiento no puede ser anterior a la solicitud y debe quedar dentro del mismo período anual, máximo hasta el 31 de diciembre."

## 11. Mostrar detalle de préstamo

**Qué debo hacer en pantalla:** entrar al detalle de un préstamo.

**Qué debo decir:** "En el detalle se ve el resumen del préstamo, sus garantes, pagos registrados, total pagado y si todavía permite registrar nuevos pagos."

**Qué parte técnica estoy defendiendo:** detalle consolidado, cálculo de total pagado con `PagoPrestamo`, control de estado final.

**Pregunta posible del ingeniero:** "¿Qué pasa si el préstamo está liquidado?"

**Respuesta:** "El sistema oculta o bloquea el registro de nuevos pagos. Además, el servicio rechaza pagos para préstamos cerrados o liquidados."

## 12. Mostrar garantes

**Qué debo hacer en pantalla:** mostrar la sección de garantes del préstamo.

**Qué debo decir:** "Un préstamo puede no tener garantes o tener hasta dos. Si se registran, su capacidad total debe cubrir al menos el 50% del monto solicitado."

**Qué parte técnica estoy defendiendo:** `PrestamoGarante`, regla del 50%, capacidad calculada.

**Pregunta posible del ingeniero:** "¿Cómo se calcula la capacidad?"

**Respuesta:** "Se calcula con el ahorro activo del socio garante menos sus préstamos pendientes. Si la deuda supera el ahorro, la capacidad queda en cero."

## 13. Mostrar pagos

**Qué debo hacer en pantalla:** mostrar historial de pagos y, si corresponde, el botón de nuevo pago.

**Qué debo decir:** "Los pagos de préstamo no usan la tabla legacy `Pago`; se registran en `PagoPrestamo`. El pago puede ser parcial o exacto, pero no puede superar el saldo pendiente."

**Qué parte técnica estoy defendiendo:** servicio `registrar_pago_prestamo`, transacción, `select_for_update`, descuento de saldo.

**Pregunta posible del ingeniero:** "¿Qué pasa si pago exactamente el saldo?"

**Respuesta:** "El sistema deja el saldo en cero y cambia el préstamo a Liquidado automáticamente."

## 14. Ir a Bingos

**Qué debo hacer en pantalla:** entrar al módulo `Bingos`.

**Qué debo decir:** "Este es el núcleo operativo del sistema. Desde aquí se administran Bingos, rondas, cartones, reportes y finanzas del Bingo."

**Qué parte técnica estoy defendiendo:** módulo `bingos`, modelo `Bingo`, rutas administrativas protegidas.

**Pregunta posible del ingeniero:** "¿El Bingo está separado de Finanzas?"

**Respuesta:** "Sí. Finanzas del socio está en `apps.finanzas`; la liquidación del evento Bingo está en `apps.bingos`, porque depende de cartones, rondas, premios y gastos del evento."

## 15. Entrar al Bingo

**Qué debo hacer en pantalla:** abrir el detalle de un Bingo.

**Qué debo decir:** "El detalle del Bingo muestra sus rondas y cartones. Aquí se ve la diferencia entre administrar el evento completo y administrar una ronda específica."

**Qué parte técnica estoy defendiendo:** detalle de Bingo, rondas relacionadas y cartones por `idbingo`.

**Pregunta posible del ingeniero:** "¿Un cartón pertenece a una ronda o a un Bingo?"

**Respuesta:** "En el flujo seguro actual, el cartón maestro pertenece al Bingo. Su participación en cada ronda se registra aparte en `CartonPartidaBingo`."

## 16. Explicar venta híbrida

**Qué debo hacer en pantalla:** señalar la opción de vender cartón para todo el Bingo y las rondas disponibles.

**Qué debo decir:** "La venta híbrida significa que se vende un cartón maestro una sola vez para el Bingo. Luego el sistema crea participaciones en las rondas elegibles. Así se evita cobrar el mismo cartón por cada ronda."

**Qué parte técnica estoy defendiendo:** `Carton` maestro, `CartonPartidaBingo`, recaudación por maestro.

**Pregunta posible del ingeniero:** "¿Por qué no crear un cartón por ronda?"

**Respuesta:** "Porque eso puede duplicar la recaudación. Si un cartón cuesta 5 y participa en 3 rondas, debe aportar 5 a la recaudación, no 15."

## 17. Vender cartón por Bingo

**Qué debo hacer en pantalla:** abrir la venta de cartón por Bingo y mostrar el formulario. Si la base de demo lo permite, registrar una venta.

**Qué debo decir:** "Este formulario solo pide jugador y precio. El sistema toma el Bingo desde la ruta y crea el cartón maestro con sus participaciones futuras elegibles."

**Qué parte técnica estoy defendiendo:** servicio `crear_carton_maestro_para_bingo`, transacción, bloqueo del Bingo y validación de precio.

**Pregunta posible del ingeniero:** "¿Qué rutas se bloquearon?"

**Respuesta:** "Se bloquearon rutas genéricas como crear o editar cartones directamente, y también la creación de cartón desde una partida. Ahora redirigen al flujo seguro por Bingo."

## 18. Mostrar jugador

**Qué debo hacer en pantalla:** ir al módulo `Jugadores` y abrir el jugador asociado al cartón.

**Qué debo decir:** "El jugador tiene su información, cuenta de acceso, cartones comprados y sesiones. Esto conecta la administración con la experiencia del participante."

**Qué parte técnica estoy defendiendo:** modelo `Jugador`, cuenta Django, grupo `Jugador`, alias sincronizado.

**Pregunta posible del ingeniero:** "¿El jugador puede entrar al admin?"

**Respuesta:** "No. El jugador pertenece al grupo `Jugador`, no es staff. Su acceso se dirige a `Mis cartones` y rutas públicas permitidas."

## 19. Mostrar cartón del jugador

**Qué debo hacer en pantalla:** entrar a `Mis cartones` como jugador o mostrar el detalle del jugador con sus cartones.

**Qué debo decir:** "El jugador puede ver sus propios cartones. Si un cartón participa en varias rondas, se muestra como un cartón de Bingo con rondas disponibles."

**Qué parte técnica estoy defendiendo:** `jugador_required`, filtro por jugador autenticado, consulta privada por propiedad.

**Pregunta posible del ingeniero:** "¿Puede un jugador ver el cartón de otro?"

**Respuesta:** "No desde la ruta privada. El detalle privado filtra por código y por jugador autenticado; si no coincide, responde como no encontrado."

## 20. Ir a sala pública

**Qué debo hacer en pantalla:** abrir `/juego/` o la opción `Sala de juego`.

**Qué debo decir:** "La sala pública permite seguir partidas sin entrar al panel administrativo. Muestra información del juego, no datos privados."

**Qué parte técnica estoy defendiendo:** rutas públicas de solo lectura, separación de información pública y administrativa.

**Pregunta posible del ingeniero:** "¿La sala pública modifica datos?"

**Respuesta:** "No. Sus vistas son de lectura. Las acciones de operación están en la consola del operador, protegida para administración."

## 21. Mostrar consultar cartón

**Qué debo hacer en pantalla:** abrir `Consultar cartón`, ingresar un código válido y mostrar la matriz.

**Qué debo decir:** "Un jugador o visitante puede consultar un cartón con su código. La pantalla muestra matriz, estado de la ronda, bolas marcadas y progreso del patrón."

**Qué parte técnica estoy defendiendo:** consulta pública controlada, matriz 5x5, casilla libre, progreso por patrón.

**Pregunta posible del ingeniero:** "¿Se muestra el precio o información privada?"

**Respuesta:** "No. La consulta pública evita exponer precio pagado, otros cartones, correos o información privada del jugador."

## 22. Ir a consola del operador

**Qué debo hacer en pantalla:** abrir la consola de una partida.

**Qué debo decir:** "La consola es la herramienta operativa. Aquí se inicia, pausa, reanuda o finaliza la partida, se extraen bolas y se validan cartones."

**Qué parte técnica estoy defendiendo:** estados de partida, acciones permitidas por estado, rutas POST protegidas.

**Pregunta posible del ingeniero:** "¿La consola puede operar en cualquier estado?"

**Respuesta:** "No. Cada acción tiene estados permitidos. Por ejemplo, la extracción solo está disponible cuando la partida está En curso."

## 23. Mostrar extracción manual/automática

**Qué debo hacer en pantalla:** mostrar el botón de sacar bola y el bolillero automático.

**Qué debo decir:** "El operador puede sacar bolas manualmente o activar el bolillero automático. El automático reutiliza la acción segura de extracción y controla concurrencia para no mandar solicitudes superpuestas."

**Qué parte técnica estoy defendiendo:** servicio `extraer_siguiente_bola`, selección sin repetición, CSRF y JavaScript de bolillero automático.

**Pregunta posible del ingeniero:** "¿Puede repetirse una bola?"

**Respuesta:** "No. El servicio parsea las bolas ya cantadas, calcula disponibles y elige solo entre las que faltan."

## 24. Explicar audio y WebSocket

**Qué debo hacer en pantalla:** activar el control de sonido y, si es posible, tener abierto el tablero público en otra pestaña.

**Qué debo decir:** "Cuando se extrae una bola, el sistema publica un evento por WebSocket. El tablero y el cartón se actualizan sin recargar, y el navegador puede cantar la bola con síntesis de voz."

**Qué parte técnica estoy defendiendo:** Django Channels, Redis, Daphne, `transaction.on_commit`, cliente WebSocket y `speechSynthesis`.

**Pregunta posible del ingeniero:** "¿El WebSocket permite mandar comandos?"

**Respuesta:** "No. El consumer público ignora mensajes del cliente. Solo distribuye eventos públicos de la partida."

## 25. Explicar validación de ganador

**Qué debo hacer en pantalla:** mostrar la sección de validación de cartones y el patrón ganador.

**Qué debo decir:** "La validación no se hace a ojo. El sistema marca la matriz con las bolas extraídas y evalúa el patrón configurado para la ronda: cartón lleno, líneas, diagonal, esquinas, cruz o X."

**Qué parte técnica estoy defendiendo:** servicios de patrón ganador, validación por participación, desempate si hay varios ganadores.

**Pregunta posible del ingeniero:** "¿Qué pasa si dos cartones ganan al mismo tiempo?"

**Respuesta:** "El sistema no elige arbitrariamente. Cambia la partida a Desempate y conserva los candidatos para resolverlos por el flujo de desempate."

## 26. Mostrar reportes

**Qué debo hacer en pantalla:** mostrar los botones de PDF de partida, Excel de cartones y Excel resumen del Bingo.

**Qué debo decir:** "Los reportes son administrativos. El PDF resume la partida; los Excel muestran cartones y resumen del Bingo. La recaudación registrada se calcula una sola vez por cartón maestro, no por ronda."

**Qué parte técnica estoy defendiendo:** `reportlab`, `openpyxl`, rutas `admin_required`, reportes de solo lectura.

**Pregunta posible del ingeniero:** "¿El reporte de ronda es una liquidación?"

**Respuesta:** "No. El reporte de ronda es operativo. La liquidación general se defiende desde el resumen y el panel financiero del Bingo."

## 27. Mostrar gestión financiera/cierre

**Qué debo hacer en pantalla:** abrir `Finanzas` del Bingo, mostrar resumen, gastos, costos, bloqueos y cierre.

**Qué debo decir:** "Aquí se calcula el resultado financiero del Bingo. Se toma la recaudación registrada por cartones maestros, se descuentan premios en efectivo finalizados, costos de premios materiales y gastos operativos. El sistema obtiene utilidad bruta y utilidad neta."

**Qué parte técnica estoy defendiendo:** `BingoCierreFinanciero`, gastos, costos, utilidad bruta, utilidad neta, cierre irreversible.

**Pregunta posible del ingeniero:** "¿Qué pasa después del cierre?"

**Respuesta:** "El cierre guarda un snapshot financiero. Después de cerrar, el panel queda de solo lectura y los servicios bloquean nuevos gastos, costos o anulaciones sobre ese Bingo cerrado."

## RESULTADO

**Archivos creados:**

- `documentos/PRESENTACION_DEFENSA_SIAB.md`
- `documentos/GUION_DEMO_SIAB.md`

**Resumen del contenido:**

- La presentación explica qué problema resuelve SIAB, qué módulos tiene, qué reglas de negocio protege, qué decisiones técnicas se tomaron, cómo se reforzó seguridad y qué pruebas respaldan el proyecto.
- El guion organiza la demo en pantalla paso a paso, con lo que debes hacer, lo que debes decir, la parte técnica que defiendes, preguntas probables del ingeniero y respuestas.

**Cómo usar cada documento mañana:**

- Usa `PRESENTACION_DEFENSA_SIAB.md` para estudiar el discurso general, la defensa técnica y el cierre.
- Usa `GUION_DEMO_SIAB.md` durante la práctica de la demo para seguir el orden de pantallas y preparar respuestas rápidas.
- Antes de presentar, abre el sistema local, elige un socio, un préstamo, un Bingo y un cartón que ya tengan datos suficientes para no improvisar durante la exposición.
