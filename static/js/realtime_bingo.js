(function () {
    "use strict";

    var CLAVE_PREFERENCIA_SONIDO = "siab.sonido_balotas_habilitado";
    var balotasProcesadas = new Set();
    var sonidoHabilitado = leerPreferenciaSonido();

    function leerPreferenciaSonido() {
        try {
            return window.localStorage.getItem(CLAVE_PREFERENCIA_SONIDO) === "true";
        } catch (error) {
            return false;
        }
    }

    function guardarPreferenciaSonido(habilitado) {
        try {
            window.localStorage.setItem(
                CLAVE_PREFERENCIA_SONIDO,
                habilitado ? "true" : "false"
            );
        } catch (error) {
            // El audio sigue funcionando durante esta visita si localStorage no está disponible.
        }
    }

    function actualizarControlesSonido() {
        document.querySelectorAll("[data-realtime-audio-toggle]").forEach(function (control) {
            control.setAttribute("aria-pressed", sonidoHabilitado ? "true" : "false");
            control.textContent = sonidoHabilitado ? "Silenciar sonido" : "Activar sonido";
            control.classList.toggle("btn-light", sonidoHabilitado);
            control.classList.toggle("btn-outline-light", !sonidoHabilitado);
        });
    }

    function iniciarControlesSonido() {
        document.querySelectorAll("[data-realtime-audio-toggle]").forEach(function (control) {
            control.addEventListener("click", function () {
                sonidoHabilitado = !sonidoHabilitado;
                guardarPreferenciaSonido(sonidoHabilitado);
                actualizarControlesSonido();
            });
        });
        actualizarControlesSonido();
    }

    function anunciarBolaExtraida(payload, partidaId) {
        if (
            !payload || payload.tipo !== "partida_actualizada" ||
            payload.evento !== "bola_extraida" || !payload.partida ||
            !payload.partida.ultima_bola
        ) {
            return;
        }

        var numero = Number(payload.partida.ultima_bola.numero);
        if (!Number.isInteger(numero) || numero < 1 || numero > 75) {
            return;
        }

        var claveBalota = partidaId + ":" + numero;
        if (balotasProcesadas.has(claveBalota)) {
            return;
        }
        balotasProcesadas.add(claveBalota);

        if (
            !sonidoHabilitado || !("speechSynthesis" in window) ||
            !("SpeechSynthesisUtterance" in window)
        ) {
            return;
        }

        try {
            var codigo = String(payload.partida.ultima_bola.codigo || codigoBola(numero));
            var letra = codigo.split("-")[0];
            var utterance = new window.SpeechSynthesisUtterance(
                letra + ", " + numero + "."
            );
            utterance.lang = "es-EC";
            utterance.rate = 0.9;
            window.speechSynthesis.speak(utterance);
        } catch (error) {
            // La actualización visual continúa si el navegador bloquea la síntesis de voz.
        }
    }

    function codigoBola(numero) {
        var letras = "BINGO";
        return letras[Math.floor((numero - 1) / 15)] + "-" + numero;
    }

    function seleccionarTodos(raiz, selector) {
        return Array.prototype.slice.call(raiz.querySelectorAll(selector));
    }

    function establecerEstadoConexion(raiz, estado) {
        var indicador = raiz.querySelector("[data-realtime-status]");
        if (!indicador) {
            return;
        }
        indicador.classList.remove(
            "realtime-status--manual",
            "realtime-status--connected",
            "realtime-status--reconnecting"
        );
        indicador.classList.add("realtime-status--" + estado);
        indicador.textContent = estado === "connected"
            ? "En tiempo real"
            : estado === "reconnecting"
                ? "Reconectando"
                : "Actualización manual";
    }

    function actualizarTexto(raiz, selector, valor) {
        seleccionarTodos(raiz, selector).forEach(function (elemento) {
            elemento.textContent = valor;
        });
    }

    function actualizarDatosComunes(raiz, partida) {
        actualizarTexto(raiz, "[data-realtime-estado]", partida.estado_visible);
        var mensaje = raiz.dataset.realtimeMode === "carton"
            ? partida.mensaje_estado_carton
            : partida.mensaje_estado;
        actualizarTexto(raiz, "[data-realtime-mensaje]", mensaje);
        actualizarTexto(
            raiz,
            "[data-realtime-ultima-bola]",
            partida.ultima_bola ? partida.ultima_bola.codigo : "—"
        );
        seleccionarTodos(raiz, "[data-realtime-sin-bolas]").forEach(function (elemento) {
            elemento.hidden = Boolean(partida.ultima_bola);
        });
    }

    function actualizarTablero(raiz, partida) {
        var bolas = Array.isArray(partida.bolas_extraidas)
            ? partida.bolas_extraidas.map(Number).filter(function (numero) {
                return Number.isInteger(numero) && numero >= 1 && numero <= 75;
            })
            : [];
        var extraidas = new Set(bolas);

        actualizarTexto(raiz, "[data-realtime-total-extraidas]", String(partida.total_extraidas));
        actualizarTexto(raiz, "[data-realtime-restantes]", String(partida.restantes));

        seleccionarTodos(raiz, "[data-bola-numero]").forEach(function (elemento) {
            var numero = Number(elemento.dataset.bolaNumero);
            var extraida = extraidas.has(numero);
            elemento.classList.toggle("is-drawn", extraida);
            elemento.title = codigoBola(numero) + (extraida ? " extraída" : "");
            var indicador = elemento.querySelector("[data-realtime-ball-check]");
            var estado = elemento.querySelector("[data-realtime-ball-state]");
            if (indicador) {
                indicador.hidden = !extraida;
            }
            if (estado) {
                estado.textContent = extraida ? "Extraída" : "Pendiente";
            }
        });

        var historial = raiz.querySelector("[data-realtime-history]");
        var vacio = raiz.querySelector("[data-realtime-history-empty]");
        if (historial) {
            historial.replaceChildren();
            bolas.forEach(function (numero) {
                var etiqueta = document.createElement("span");
                etiqueta.className = "public-history-ball badge rounded-pill";
                etiqueta.setAttribute("role", "listitem");
                etiqueta.textContent = codigoBola(numero);
                historial.appendChild(etiqueta);
            });
            historial.classList.toggle("d-none", bolas.length === 0);
        }
        if (vacio) {
            vacio.classList.toggle("d-none", bolas.length !== 0);
        }

        var resultado = raiz.querySelector("[data-realtime-result]");
        if (resultado) {
            resultado.classList.toggle("d-none", !partida.finalizada);
        }
        actualizarTexto(
            raiz,
            "[data-realtime-ganador]",
            partida.ganador ? "Ganador: " + partida.ganador : "Ganador no confirmado"
        );
        seleccionarTodos(raiz, "[data-realtime-desempate]").forEach(function (elemento) {
            elemento.classList.toggle("d-none", !partida.resuelta_por_desempate);
        });
    }

    function actualizarCarton(raiz, partida) {
        var extraidas = new Set(
            (Array.isArray(partida.bolas_extraidas) ? partida.bolas_extraidas : [])
                .map(Number)
        );
        var marcados = 0;
        seleccionarTodos(raiz, "[data-carton-cell]").forEach(function (celda) {
            var marcada = extraidas.has(Number(celda.dataset.bolaNumero));
            celda.classList.toggle("public-card-cell--marked", marcada);
            celda.classList.toggle("public-card-cell--pending", !marcada);
            var estado = celda.querySelector("[data-carton-cell-state]");
            if (estado) {
                estado.textContent = marcada ? "✓ Marcado" : "○ Pendiente";
            }
            if (marcada) {
                marcados += 1;
            }
        });
        seleccionarTodos(raiz, "[data-realtime-progreso]").forEach(function (elemento) {
            var puntoFinal = elemento.tagName === "P" ? "." : "";
            elemento.textContent = marcados + " de " + raiz.dataset.totalNumerosCarton +
                " números marcados" + puntoFinal;
        });
    }

    function recargarVistaActual() {
        // reload conserva la ruta, el query string y el fragmento actuales.
        window.location.reload();
    }

    function iniciarTiempoReal(raiz) {
        var partidaId = raiz.dataset.partidaId;
        if (!/^[1-9][0-9]*$/.test(partidaId || "") || !("WebSocket" in window)) {
            establecerEstadoConexion(raiz, "manual");
            return;
        }

        var intento = 0;
        var socket = null;
        var temporizador = null;

        function conectar() {
            var protocolo = window.location.protocol === "https:" ? "wss:" : "ws:";
            establecerEstadoConexion(raiz, "reconnecting");
            socket = new WebSocket(
                protocolo + "//" + window.location.host + "/ws/juego/partidas/" + partidaId + "/"
            );

            socket.addEventListener("open", function () {
                intento = 0;
                establecerEstadoConexion(raiz, "connected");
            });

            socket.addEventListener("message", function (evento) {
                var payload;
                try {
                    payload = JSON.parse(evento.data);
                } catch (error) {
                    return;
                }
                if (
                    !payload || payload.tipo !== "partida_actualizada" ||
                    !payload.partida || String(payload.partida.id) !== partidaId
                ) {
                    return;
                }
                anunciarBolaExtraida(payload, partidaId);
                if (payload.requiere_recarga === true) {
                    recargarVistaActual();
                    return;
                }
                actualizarDatosComunes(raiz, payload.partida);
                if (raiz.dataset.realtimeMode === "tablero") {
                    actualizarTablero(raiz, payload.partida);
                } else if (raiz.dataset.realtimeMode === "carton") {
                    actualizarCarton(raiz, payload.partida);
                }
            });

            socket.addEventListener("close", function (evento) {
                if (evento.code === 4404) {
                    establecerEstadoConexion(raiz, "manual");
                    return;
                }
                establecerEstadoConexion(raiz, "reconnecting");
                var espera = Math.min(30000, 1000 * Math.pow(2, intento));
                intento += 1;
                window.clearTimeout(temporizador);
                temporizador = window.setTimeout(conectar, espera);
            });

            socket.addEventListener("error", function () {
                socket.close();
            });
        }

        conectar();
    }

    iniciarControlesSonido();
    document.querySelectorAll("[data-realtime-bingo]").forEach(iniciarTiempoReal);
}());
