# SIAB - Sistema Integral de Administración de Bingos

## 1. Título del proyecto

**SIAB - Sistema Integral de Administración de Bingos**

SIAB es una aplicación web desarrollada con Django y PostgreSQL para administrar una organización o cooperativa que realiza Bingos, controla socios, registra jugadores, maneja préstamos, ahorros, aportes, pagos, premios, reportes y cierre financiero.

La idea central del proyecto es que el Bingo no se trate como una pantalla aislada de juego, sino como parte de una operación administrativa completa.

## 2. Presentación inicial

Buenos días, ingeniero. El proyecto que voy a presentar es **SIAB, Sistema Integral de Administración de Bingos**. Este sistema nace para resolver un problema real: cuando una organización maneja socios, jugadores, cartones, rondas, préstamos, aportes, premios y gastos de forma manual, es fácil perder control, duplicar valores o no tener una trazabilidad clara de lo que ocurre.

SIAB centraliza esa operación en una sola plataforma. Permite registrar socios y jugadores, vender cartones de forma controlada, operar partidas de Bingo en tiempo real, validar ganadores por patrones, administrar préstamos con garantes, registrar pagos, controlar ahorros y aportes semanales, calcular resultados financieros del Bingo y generar reportes.

Lo importante es que no es solamente un Bingo digital. Es un sistema administrativo integral para una organización que necesita transparencia, control financiero y orden operativo. Además, se reforzaron reglas críticas con servicios, transacciones, rutas seguras y pruebas automatizadas.

## 3. Problema identificado

Una organización que maneja Bingos, socios, aportes, préstamos y premios puede crecer rápidamente en complejidad. Si todo se controla con hojas sueltas, registros manuales o procesos separados, aparecen problemas como:

- **Control manual:** los datos dependen de apuntes físicos o archivos aislados.
- **Duplicación de recaudación:** un cartón puede confundirse como si se cobrara por cada ronda.
- **Confusión financiera:** ahorro, aporte semanal, pago de préstamo, premio, gasto y utilidad pueden mezclarse.
- **Dificultad para controlar cartones:** no siempre queda claro qué jugador compró un cartón, a qué Bingo pertenece y en qué rondas participa.
- **Falta de trazabilidad:** si se modifica un préstamo, un pago o un cierre financiero, puede ser difícil saber qué regla se aplicó.
- **Falta de control financiero del Bingo:** sin gastos, premios y recaudación bien separados, no se puede obtener una utilidad real.
- **Falta de transparencia:** socios y jugadores no tienen una forma clara de consultar su información o seguir el juego.

Ese problema es más administrativo que visual. Por eso SIAB se diseñó como un sistema de gestión, no solo como una interfaz para sacar bolas.

## 4. Solución propuesta

SIAB resuelve el problema centralizando la operación en módulos conectados:

- centraliza el registro, edición y consulta de socios;
- permite manejar jugadores independientes o vinculados a socios;
- organiza Bingos y sus rondas;
- vende cartones mediante el flujo seguro por Bingo;
- permite que el jugador compre y consulte sus cartones;
- expone una sala pública y un tablero público de solo lectura;
- controla préstamos, garantes y pagos;
- separa ahorros, aportes semanales y pagos de préstamo;
- calcula finanzas del Bingo con recaudación registrada, premios, costos, gastos, utilidad bruta y utilidad neta;
- genera reportes administrativos en Excel y PDF;
- usa WebSockets para actualizar tablero, cartón y consola en tiempo real;
- bloquea rutas genéricas peligrosas de cartones para proteger el flujo seguro.

La solución no solo muestra datos: aplica reglas de negocio. Por ejemplo, un cartón maestro se vende una vez para un Bingo, y sus participaciones por ronda no vuelven a sumar dinero.

## 5. Módulos implementados

### A. Módulo de socios

El módulo de socios permite administrar la información principal de los miembros de la organización:

- registro de socios;
- edición de datos personales;
- detalle con pestañas;
- cuentas bancarias del socio;
- ahorros registrados;
- total de ahorro activo;
- aportes semanales;
- préstamos asociados.

En el detalle del socio se puede defender que SIAB no trata al socio como un dato aislado, sino como una entidad administrativa con relación financiera.

### B. Módulo de jugadores

El módulo de jugadores permite gestionar a las personas que participan en los Bingos:

- jugadores independientes o vinculados a socios mediante el campo opcional de socio;
- alias, correo, saldo y estado de cuenta;
- creación de cuenta de acceso para jugadores;
- registro público de jugador;
- grupo Django `Jugador`;
- panel privado de `Mis cartones`;
- consulta de cartones comprados;
- acceso a la sala de juego.

La relación entre usuario y jugador se controla por el alias del jugador y el `username` del usuario Django, sin crear una tabla física adicional.

### C. Módulo de Bingo

El módulo de Bingo administra el evento principal:

- creación y edición de Bingos;
- fecha, tipo, lugar, precio del cartón, premio mayor y descripción de premios;
- partidas o rondas dentro del Bingo;
- premios en efectivo por ronda;
- premios materiales por ronda;
- patrón ganador por ronda;
- consola del operador;
- venta de cartones;
- tablero público;
- reportes administrativos;
- panel financiero del Bingo.

Cada ronda puede tener un patrón ganador diferente: cartón lleno, línea horizontal, línea vertical, diagonal, cuatro esquinas, cruz o X.

### D. Módulo de cartones

El módulo de cartones fue reforzado para evitar duplicar recaudación:

- existe un cartón maestro por Bingo;
- el cartón maestro tiene un único precio registrado;
- el cartón maestro puede participar en varias rondas;
- cada participación por ronda vive en `CartonPartidaBingo`;
- el precio no se repite por participación;
- las rondas elegibles reciben participación automáticamente;
- se bloqueó la creación y edición genérica peligrosa de cartones;
- el flujo seguro de venta es por Bingo.

La regla que se defiende es: **un cartón se compra una sola vez para el Bingo; las rondas son participaciones, no ventas adicionales**.

### E. Módulo de préstamos

El módulo de préstamos permite registrar obligaciones financieras asociadas a un socio:

- préstamo por socio;
- monto solicitado;
- tasa de interés;
- total a pagar;
- saldo pendiente;
- número de cuotas;
- fecha de solicitud;
- fecha de vencimiento;
- estado del préstamo;
- edición segura.

La fecha de vencimiento se valida dentro del mismo período anual, como máximo hasta el 31 de diciembre del año de solicitud.

### F. Módulo de garantes

El módulo de garantes refuerza el control del préstamo:

- un préstamo puede registrarse con 0, 1 o 2 garantes;
- si se registran garantes, su capacidad total debe cubrir mínimo el 50% del monto solicitado;
- el garante no puede ser el mismo socio deudor;
- el garante no puede repetirse;
- la capacidad se calcula con ahorro activo menos préstamos pendientes;
- los garantes se guardan en `PrestamoGarante`.

Esto permite defender que el préstamo no solo se registra, sino que pasa por una regla de respaldo financiero.

### G. Módulo de pagos de préstamos

Los pagos de préstamos usan la tabla específica `PagoPrestamo`, separada de la tabla legacy `Pago`.

El módulo permite:

- registrar pago parcial;
- registrar pago exacto;
- rechazar pagos con monto menor o igual a cero;
- rechazar sobrepagos;
- descontar automáticamente el saldo pendiente;
- liquidar el préstamo cuando el saldo llega a cero;
- mantener historial de pagos por préstamo.

Esta separación evita reutilizar una tabla anterior con otro contrato y reduce errores de interpretación.

### H. Módulo de ahorros

El módulo de ahorros registra montos asociados a socios y Bingos:

- el monto debe ser mayor que cero;
- el ahorro puede ser obligatorio o voluntario;
- el estado puede ser activo o inactivo;
- el detalle del socio muestra el total de ahorro activo;
- el ahorro activo se usa para calcular la capacidad de los garantes.

Esto conecta el módulo de socios con la evaluación financiera de préstamos.

### I. Módulo de aportes semanales

Los aportes semanales están separados del ahorro:

- se registra socio;
- regalo asociado;
- partida opcional;
- número de semana;
- fecha planificada;
- fecha real de entrega;
- método de ingreso;
- referencia;
- estado;
- valor del regalo asociado.

La separación es importante porque un aporte semanal no debe confundirse con un ahorro ni con un pago de préstamo.

### J. Módulo financiero del Bingo

El módulo financiero del Bingo permite pasar de una operación de juego a una operación administrativa:

- gastos operativos;
- costos de premios materiales;
- premios en efectivo de rondas finalizadas;
- recaudación registrada por cartones maestros vendidos;
- resultado provisional;
- utilidad bruta;
- utilidad neta;
- bloqueos antes del cierre;
- cierre financiero;
- cierre irreversible;
- panel solo lectura después del cierre.

El cierre guarda un snapshot financiero. Después de cerrar, no se pueden registrar o anular gastos y costos del Bingo cerrado.

### K. Tiempo real

SIAB implementa tiempo real para el juego:

- WebSockets con Django Channels;
- Daphne como servidor ASGI;
- Redis como capa de canales;
- tablero público actualizado en vivo;
- cartón público actualizado en vivo;
- consola del operador;
- extracción manual de bolas;
- bolillero automático;
- audio que canta las bolas mediante síntesis de voz del navegador;
- publicación de eventos después de confirmar la transacción.

El WebSocket es público y de solo lectura. El cliente no manda comandos administrativos por ese canal.

### L. Reportes

El módulo de reportes permite descargar información administrativa:

- reporte PDF de partida;
- Excel de cartones de una partida;
- Excel resumen del Bingo;
- resumen operativo de rondas;
- cartones históricos y cartones de Bingo;
- participación por ronda;
- recaudación registrada sin duplicar por participación;
- notas operativas para distinguir reporte de ronda y liquidación general.

Los reportes están protegidos para usuarios administrativos.

## 6. Reglas de negocio importantes

Estas son las reglas que conviene defender con seguridad:

- Un cartón se vende una sola vez por Bingo.
- Ese cartón participa en las rondas elegibles del Bingo.
- No se cobra un cartón por cada ronda.
- La recaudación se calcula por cartón maestro, no por participación.
- Una participación por ronda no representa una venta adicional.
- Una misma tarjeta puede ganar en más de una ronda porque cada ronda es independiente.
- La validación de ganador depende del patrón configurado en esa ronda.
- El préstamo respeta el período anual: el vencimiento no puede pasar del 31 de diciembre del año de solicitud.
- Los garantes respaldan el préstamo según su capacidad calculada.
- Si hay garantes, deben cubrir mínimo el 50% del monto solicitado.
- El garante no puede ser el mismo deudor ni repetirse.
- El pago de préstamo descuenta saldo.
- Un pago exacto liquida automáticamente el préstamo.
- Un sobrepago se rechaza.
- El cierre financiero congela el resultado.
- Después del cierre financiero, el panel queda como consulta y no como edición.

## 7. Decisiones técnicas importantes

SIAB está construido con decisiones técnicas orientadas a respetar la base de datos existente y proteger reglas críticas:

- **Django como framework principal:** permite separar modelos, formularios, vistas, servicios, plantillas y autenticación.
- **PostgreSQL como base de datos:** se usa como base relacional principal del sistema.
- **Modelos `managed=False`:** los modelos respetan la estructura física aprobada y no intentan que Django administre esas tablas con migraciones.
- **SQL manual versionado:** los scripts en `sql/` documentan cambios físicos como garantes, pagos de préstamo, cierre financiero, costos y gastos.
- **Servicios para reglas críticas:** préstamos, garantes, pagos, venta de cartones, extracción de bolas, ganador y cierre financiero se concentran en servicios.
- **Transacciones (`transaction.atomic`):** se usan en operaciones donde no debe haber cambios parciales.
- **Bloqueos (`select_for_update`):** se usan en préstamos, pagos, garantes, Bingo, rondas, cartones, participaciones y cierre para mantener consistencia.
- **Separación de `PagoPrestamo`:** evita usar la tabla legacy `Pago` para pagos nuevos de préstamos.
- **Validaciones en formularios y servicios:** el formulario muestra errores al usuario y el servicio protege la regla incluso si alguien manipula el POST.
- **WebSockets:** permiten actualización visual en vivo de tablero, cartón y consola.
- **Redis, Daphne y Channels:** forman la infraestructura de comunicación en vivo.
- **Pruebas automatizadas:** validan reglas de negocio, rutas, reportes, tiempo real, pagos, garantes y cierre financiero.

## 8. Seguridad y control

El proyecto refuerza seguridad y control de varias formas:

- las rutas administrativas usan `admin_required`;
- usuarios anónimos son redirigidos o limitados según la ruta;
- el jugador solo ve sus propios cartones en `Mis cartones`;
- si un jugador intenta consultar un cartón ajeno por ruta privada, no se revela información;
- las rutas públicas no muestran datos privados como precios, correos, otros cartones o candidatos internos de desempate;
- los reportes administrativos están protegidos;
- las rutas genéricas de cartones fueron bloqueadas;
- el flujo seguro de cartones es por Bingo;
- los pagos de préstamos se registran por `PagoPrestamo`, no por la tabla vieja `Pago`;
- las acciones sensibles usan POST y CSRF;
- el WebSocket público es de solo lectura;
- el payload público no expone `idbingadores`, precios ni datos privados;
- el cierre financiero no se modifica después de cerrar.

## 9. Pruebas y calidad

En el estado final de la entrega se validó lo siguiente:

- `manage.py check` terminó sin errores;
- `apps.finanzas` + `apps.socios` pasaron **117 pruebas**;
- `apps.bingos` pasó **407 pruebas**;
- la rama final fue fusionada a `main` / `principal`;
- en el repositorio actual, `main` apunta al merge final de `feat/garantes-prestamos`;
- las rutas genéricas peligrosas de cartones fueron bloqueadas;
- el flujo seguro de venta de cartones quedó por Bingo.

Las pruebas cubren:

- préstamos;
- garantes;
- pagos de préstamos;
- ahorros;
- aportes semanales;
- venta segura de cartones;
- recaudación no duplicada;
- reportes Excel/PDF;
- validación de ganador por patrones;
- WebSockets;
- bolillero y audio;
- sala pública;
- acceso del jugador;
- cierre financiero;
- panel solo lectura después del cierre.

Esto demuestra que el proyecto no se hizo solo visualmente. Las reglas críticas fueron validadas con pruebas automatizadas y con separación de lógica en servicios.

## 10. Alcance actual

El sistema está listo para una **demo integral local**.

El alcance actual permite demostrar:

- inicio administrativo;
- dashboard;
- socios;
- cuentas bancarias;
- ahorros;
- aportes;
- préstamos;
- garantes;
- pagos de préstamos;
- jugadores;
- acceso de jugador;
- compra y consulta de cartón;
- Bingos;
- rondas;
- patrones ganadores;
- consola del operador;
- extracción manual y automática;
- tablero público;
- WebSockets;
- audio;
- reportes;
- finanzas del Bingo;
- cierre financiero.

La demo debe hacerse con una base local de prueba o de demostración, no con una base real de producción.

## 11. Alcance futuro

Hay mejoras futuras que no deben presentarse como ya implementadas:

- portal completo del socio;
- solicitud de pago por socio;
- roles separados: operador, cajero, bodeguero y finanzas;
- despliegue en servidor real;
- comprobantes formales de pago;
- notificaciones por correo o mensajería;
- reparto formal de utilidades;
- auditoría avanzada de cambios;
- relación física formal entre usuario Django y jugador;
- confirmación contable de cobro de cartones;
- comprobante o recibo de venta de cartón;
- observabilidad de WebSockets y Redis en producción.

Estas mejoras no reducen el valor del alcance actual. Más bien muestran que el proyecto ya tiene una base sólida y puede crecer por etapas.

## 12. Cierre de presentación

Para cerrar, puedo decir lo siguiente:

Con este proyecto aprendí a construir un sistema que no solo muestra pantallas, sino que protege reglas de negocio reales. SIAB resuelve el control de una organización que maneja Bingos, socios, préstamos, pagos, ahorros, aportes, premios y gastos.

El valor principal está en que evita duplicar recaudación, separa conceptos financieros, controla quién puede ver o modificar información y permite operar el Bingo en tiempo real. Además, las reglas críticas se reforzaron con servicios, transacciones, rutas seguras y pruebas automatizadas.

Por eso considero que SIAB está listo para demostrarse como un sistema administrativo integral, no solo como un juego de Bingo.
