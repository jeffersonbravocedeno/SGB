(function () {
    "use strict";

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

    document.querySelectorAll("[data-realtime-bingo]").forEach(iniciarTiempoReal);
}());
