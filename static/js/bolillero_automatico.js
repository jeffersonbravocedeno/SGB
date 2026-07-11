(function () {
    "use strict";

    var ESTADO_EN_CURSO = "En curso";
    var SELECTOR_BOLILLERO = "[data-bolillero-automatico]";

    function enteroSeguro(valor, predeterminado) {
        var numero = Number(valor);
        return Number.isInteger(numero) ? numero : predeterminado;
    }

    function limpiarTexto(elemento) {
        if (!elemento) {
            return "";
        }
        var copia = elemento.cloneNode(true);
        var cierre = copia.querySelector(".btn-close");
        if (cierre) {
            cierre.remove();
        }
        return copia.textContent.replace(/\s+/g, " ").trim();
    }

    function leerContexto(raiz) {
        var contenedorTiempoReal = raiz.closest("[data-realtime-bingo]");
        var formularioManual = contenedorTiempoReal
            ? contenedorTiempoReal.querySelector("[data-bolillero-manual-form]")
            : document.querySelector("[data-bolillero-manual-form]");

        return {
            raiz: raiz,
            partidaId: String(raiz.dataset.partidaId || ""),
            formularioManual: formularioManual,
            botonManual: formularioManual
                ? formularioManual.querySelector("[data-bolillero-manual-button]")
                : null,
            selectorIntervalo: raiz.querySelector("[data-bolillero-intervalo]"),
            botonIniciar: raiz.querySelector("[data-bolillero-iniciar]"),
            botonDetener: raiz.querySelector("[data-bolillero-detener]"),
            indicadorEstado: raiz.querySelector("[data-bolillero-estado]"),
            estadoPartida: String(raiz.dataset.estadoPartida || "").trim(),
            bolasFaltantes: enteroSeguro(raiz.dataset.bolasFaltantes, 0),
            puedeSacarBola: raiz.dataset.puedeSacarBola === "true",
            activo: false,
            solicitudPendiente: false,
            detenerSolicitado: false,
            temporizador: null,
            segundosRestantes: 0,
        };
    }

    function puedeExtraer(contexto) {
        return (
            contexto.estadoPartida === ESTADO_EN_CURSO &&
            contexto.bolasFaltantes > 0 &&
            contexto.puedeSacarBola
        );
    }

    function obtenerIntervalo(contexto) {
        var permitidos = [3, 5, 8, 10];
        var intervalo = enteroSeguro(contexto.selectorIntervalo.value, 5);
        return permitidos.indexOf(intervalo) === -1 ? 5 : intervalo;
    }

    function escribirEstado(contexto, mensaje) {
        if (contexto.indicadorEstado) {
            contexto.indicadorEstado.textContent = mensaje;
        }
    }

    function actualizarBotones(contexto) {
        var extraccionDisponible = puedeExtraer(contexto);
        if (contexto.botonIniciar) {
            contexto.botonIniciar.disabled = (
                !extraccionDisponible || contexto.activo || contexto.solicitudPendiente
            );
        }
        if (contexto.botonDetener) {
            contexto.botonDetener.disabled = (
                (!contexto.activo && !contexto.solicitudPendiente) ||
                contexto.detenerSolicitado
            );
        }
        if (contexto.selectorIntervalo) {
            contexto.selectorIntervalo.disabled = contexto.activo || contexto.solicitudPendiente;
        }
        if (contexto.botonManual) {
            contexto.botonManual.disabled = contexto.solicitudPendiente || !extraccionDisponible;
        }
    }

    function limpiarTemporizador(contexto) {
        if (contexto.temporizador) {
            window.clearTimeout(contexto.temporizador);
            contexto.temporizador = null;
        }
    }

    function mensajeDetencionPorEstado(contexto) {
        if (contexto.bolasFaltantes <= 0) {
            return "Extracción detenida: ya no quedan bolas disponibles";
        }
        return "Extracción detenida: la partida ya no está En curso";
    }

    function detenerAutomatico(contexto, mensaje) {
        limpiarTemporizador(contexto);
        if (contexto.solicitudPendiente) {
            contexto.detenerSolicitado = true;
            contexto.activo = false;
            actualizarBotones(contexto);
            escribirEstado(contexto, "Se detendrá después de la balota actual.");
            return;
        }
        contexto.detenerSolicitado = false;
        contexto.activo = false;
        actualizarBotones(contexto);
        escribirEstado(contexto, mensaje || "Automático detenido");
    }

    function detenerPorError(contexto, mensaje) {
        limpiarTemporizador(contexto);
        contexto.detenerSolicitado = false;
        contexto.activo = false;
        contexto.solicitudPendiente = false;
        actualizarBotones(contexto);
        escribirEstado(contexto, mensaje);
    }

    function textoCuentaRegresiva(segundos) {
        return "Próxima balota en " + segundos + " segundo" + (segundos === 1 ? "" : "s");
    }

    function programarCuentaRegresiva(contexto) {
        limpiarTemporizador(contexto);
        if (!contexto.activo) {
            return;
        }
        if (!puedeExtraer(contexto)) {
            detenerAutomatico(contexto, mensajeDetencionPorEstado(contexto));
            return;
        }

        contexto.segundosRestantes = obtenerIntervalo(contexto);
        escribirEstado(contexto, textoCuentaRegresiva(contexto.segundosRestantes));
        contexto.temporizador = window.setTimeout(function avanzarCuentaRegresiva() {
            if (!contexto.activo) {
                return;
            }
            contexto.segundosRestantes -= 1;
            if (contexto.segundosRestantes <= 0) {
                ejecutarExtraccion(contexto);
                return;
            }
            escribirEstado(contexto, textoCuentaRegresiva(contexto.segundosRestantes));
            contexto.temporizador = window.setTimeout(avanzarCuentaRegresiva, 1000);
        }, 1000);
    }

    function obtenerTokenCsrf(contexto) {
        var token = contexto.formularioManual
            ? contexto.formularioManual.querySelector("input[name=csrfmiddlewaretoken]")
            : null;
        return token ? token.value : "";
    }

    function actualizarEstadoDesdeRaiz(contexto, raizActualizada) {
        if (!raizActualizada) {
            return;
        }
        contexto.estadoPartida = String(
            raizActualizada.dataset.estadoPartida || contexto.estadoPartida
        ).trim();
        contexto.bolasFaltantes = enteroSeguro(
            raizActualizada.dataset.bolasFaltantes,
            contexto.bolasFaltantes
        );
        contexto.puedeSacarBola = raizActualizada.dataset.puedeSacarBola === "true";
        contexto.raiz.dataset.estadoPartida = contexto.estadoPartida;
        contexto.raiz.dataset.bolasFaltantes = String(contexto.bolasFaltantes);
        contexto.raiz.dataset.puedeSacarBola = contexto.puedeSacarBola ? "true" : "false";
        actualizarBotones(contexto);
    }

    function actualizarEstadoDesdePayload(contexto, partida) {
        if (!partida || String(partida.id) !== contexto.partidaId) {
            return;
        }
        contexto.estadoPartida = String(partida.estado || contexto.estadoPartida).trim();
        contexto.bolasFaltantes = enteroSeguro(partida.restantes, contexto.bolasFaltantes);
        contexto.puedeSacarBola = (
            contexto.estadoPartida === ESTADO_EN_CURSO && contexto.bolasFaltantes > 0
        );
        contexto.raiz.dataset.estadoPartida = contexto.estadoPartida;
        contexto.raiz.dataset.bolasFaltantes = String(contexto.bolasFaltantes);
        contexto.raiz.dataset.puedeSacarBola = contexto.puedeSacarBola ? "true" : "false";
        actualizarBotones(contexto);
    }

    function detectarMensajeError(documento) {
        return limpiarTexto(
            documento.querySelector('.messages-wrap [data-message-level="error"]')
        );
    }

    function procesarRespuestaHtml(contexto, html) {
        var documento = new window.DOMParser().parseFromString(html, "text/html");
        var raizActualizada = documento.querySelector(SELECTOR_BOLILLERO);
        if (!raizActualizada) {
            throw new Error("el servidor no devolvió la consola del operador.");
        }
        actualizarEstadoDesdeRaiz(contexto, raizActualizada);
        var mensajeError = detectarMensajeError(documento);
        if (mensajeError) {
            throw new Error(mensajeError);
        }
    }

    function finalizarSolicitud(contexto) {
        contexto.solicitudPendiente = false;
        if (contexto.detenerSolicitado) {
            contexto.detenerSolicitado = false;
            contexto.activo = false;
            actualizarBotones(contexto);
            escribirEstado(contexto, "Automático detenido");
            return;
        }
        actualizarBotones(contexto);
        if (!contexto.activo) {
            return;
        }
        if (!puedeExtraer(contexto)) {
            detenerAutomatico(contexto, mensajeDetencionPorEstado(contexto));
            return;
        }
        programarCuentaRegresiva(contexto);
    }

    function ejecutarExtraccion(contexto) {
        limpiarTemporizador(contexto);
        if (!contexto.activo || contexto.solicitudPendiente) {
            return;
        }
        if (!puedeExtraer(contexto)) {
            detenerAutomatico(contexto, mensajeDetencionPorEstado(contexto));
            return;
        }
        if (!contexto.formularioManual || !contexto.formularioManual.action) {
            detenerAutomatico(contexto, "Extracción detenida: no se encontró la acción manual segura");
            return;
        }

        contexto.solicitudPendiente = true;
        actualizarBotones(contexto);
        escribirEstado(contexto, "Extrayendo siguiente balota...");

        window.fetch(contexto.formularioManual.action, {
            method: "POST",
            credentials: "same-origin",
            headers: {
                "X-CSRFToken": obtenerTokenCsrf(contexto),
                "X-Requested-With": "XMLHttpRequest",
            },
            body: new window.FormData(contexto.formularioManual),
        }).then(function (respuesta) {
            if (!respuesta.ok) {
                throw new Error("El servidor respondió con error.");
            }
            return respuesta.text();
        }).then(function (html) {
            procesarRespuestaHtml(contexto, html);
        }).catch(function (error) {
            detenerPorError(
                contexto,
                "Extracción automática detenida: " + (error.message || "el servidor respondió con error.")
            );
        }).finally(function () {
            finalizarSolicitud(contexto);
        });
    }

    function iniciarAutomatico(contexto) {
        if (contexto.activo || contexto.solicitudPendiente) {
            return;
        }
        if (!puedeExtraer(contexto)) {
            escribirEstado(contexto, mensajeDetencionPorEstado(contexto));
            actualizarBotones(contexto);
            return;
        }
        contexto.detenerSolicitado = false;
        contexto.activo = true;
        actualizarBotones(contexto);
        escribirEstado(contexto, "Extracción automática activa");
        programarCuentaRegresiva(contexto);
    }

    function registrarEventos(contexto) {
        if (contexto.botonIniciar) {
            contexto.botonIniciar.addEventListener("click", function () {
                iniciarAutomatico(contexto);
            });
        }
        if (contexto.botonDetener) {
            contexto.botonDetener.addEventListener("click", function () {
                detenerAutomatico(contexto, "Automático detenido");
            });
        }
        if (contexto.formularioManual) {
            contexto.formularioManual.addEventListener("submit", function (evento) {
                if (contexto.solicitudPendiente) {
                    evento.preventDefault();
                    escribirEstado(
                        contexto,
                        "Espera a que termine la extracción automática pendiente."
                    );
                    return;
                }
                if (contexto.activo) {
                    detenerAutomatico(contexto, "Automático detenido por extracción manual.");
                }
            });
        }
        window.addEventListener("beforeunload", function () {
            limpiarTemporizador(contexto);
        });
        document.addEventListener("siab:partidaActualizada", function (evento) {
            var payload = evento.detail || {};
            if (!payload.partida || String(payload.partida.id) !== contexto.partidaId) {
                return;
            }
            actualizarEstadoDesdePayload(contexto, payload.partida);
            if (
                contexto.activo &&
                (payload.evento === "desempate_detectado" || !puedeExtraer(contexto))
            ) {
                detenerAutomatico(contexto, mensajeDetencionPorEstado(contexto));
            }
        });
    }

    document.querySelectorAll(SELECTOR_BOLILLERO).forEach(function (raiz) {
        var contexto = leerContexto(raiz);
        registrarEventos(contexto);
        actualizarBotones(contexto);
    });
}());
