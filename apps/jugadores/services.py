from functools import wraps
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import Group, User
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.common.ids import assign_next_integer_pk

from .models import Jugador


GRUPO_JUGADOR = "Jugador"
ESTADO_JUGADOR_ACTIVO = "Activo"


def normalizar_alias_jugador(alias):
    return str(alias or "").strip()


def jugador_esta_activo(jugador):
    estado = str(getattr(jugador, "estadocuentajugador", "") or "").strip()
    return estado.lower() == ESTADO_JUGADOR_ACTIVO.lower()


def usuario_es_jugador(user):
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "pk", None) is None:
        return False
    return user.groups.filter(name=GRUPO_JUGADOR).exists()


def obtener_grupo_jugador():
    grupo, _created = Group.objects.get_or_create(name=GRUPO_JUGADOR)
    return grupo


def agregar_usuario_a_grupo_jugador(user):
    user.groups.add(obtener_grupo_jugador())


def crear_usuario_jugador(alias, correo, password):
    user = User.objects.create_user(
        username=alias,
        email=correo or "",
        password=password,
        is_staff=False,
        is_superuser=False,
        is_active=True,
    )
    agregar_usuario_a_grupo_jugador(user)
    return user


def registrar_jugador_publico(alias, correo, password):
    alias = normalizar_alias_jugador(alias)
    correo = (correo or "").strip().lower()

    with transaction.atomic():
        jugador = Jugador(
            aliasjugador=alias,
            correojugador=correo,
            fecharegistrojugador=timezone.now(),
            saldocreditojugador=Decimal("0.00"),
            estadocuentajugador=ESTADO_JUGADOR_ACTIVO,
        )
        assign_next_integer_pk(jugador)
        jugador.save(force_insert=True)
        user = crear_usuario_jugador(alias, correo, password)

    return jugador, user


def crear_acceso_para_jugador(jugador, password):
    alias = normalizar_alias_jugador(jugador.aliasjugador)
    if not alias:
        raise ValidationError("El jugador debe tener alias para crear acceso.")
    if not jugador_esta_activo(jugador):
        raise ValidationError("Solo se puede crear acceso para jugadores Activos.")
    if User.objects.filter(username__iexact=alias).exists():
        raise ValidationError("Ya existe una cuenta con ese alias.")

    with transaction.atomic():
        return crear_usuario_jugador(
            alias,
            jugador.correojugador or "",
            password,
        )


def obtener_usuario_por_alias(alias):
    alias = normalizar_alias_jugador(alias)
    if not alias:
        return None
    return User.objects.filter(username=alias).first()


def obtener_usuario_por_alias_insensible(alias):
    alias = normalizar_alias_jugador(alias)
    if not alias:
        return None
    return User.objects.filter(username__iexact=alias).first()


def estado_cuenta_acceso_jugador(jugador):
    alias = normalizar_alias_jugador(jugador.aliasjugador)
    estado = {
        "alias": alias,
        "usuario": None,
        "tiene_cuenta": False,
        "conflicto": False,
        "puede_crear": False,
        "mensaje": "",
    }
    if not alias:
        estado["mensaje"] = "El jugador no tiene alias."
        return estado
    if not jugador_esta_activo(jugador):
        estado["mensaje"] = "Solo los jugadores Activos pueden tener acceso."
        return estado

    usuario = obtener_usuario_por_alias(alias)
    if usuario is not None:
        estado["usuario"] = usuario
        estado["tiene_cuenta"] = usuario_es_jugador(usuario)
        estado["conflicto"] = not estado["tiene_cuenta"]
        estado["mensaje"] = (
            "Este jugador ya tiene cuenta de acceso."
            if estado["tiene_cuenta"]
            else "El alias pertenece a un usuario que no es jugador."
        )
        return estado

    usuario_conflicto = obtener_usuario_por_alias_insensible(alias)
    if usuario_conflicto is not None:
        estado["usuario"] = usuario_conflicto
        estado["conflicto"] = True
        estado["mensaje"] = "El alias ya está ocupado por otra cuenta."
        return estado

    estado["puede_crear"] = True
    estado["mensaje"] = "El jugador puede recibir una cuenta de acceso."
    return estado


def obtener_jugador_autenticado(user):
    if not getattr(user, "is_authenticated", False):
        raise PermissionDenied
    if not usuario_es_jugador(user):
        raise PermissionDenied

    alias = normalizar_alias_jugador(user.username)
    if not alias:
        raise PermissionDenied

    jugador = Jugador.objects.filter(aliasjugador=alias).first()
    if jugador is None or not jugador_esta_activo(jugador):
        raise PermissionDenied
    return jugador


def jugador_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path(), settings.LOGIN_URL)
        request.jugador = obtener_jugador_autenticado(request.user)
        return view_func(request, *args, **kwargs)

    return _wrapped_view


def sincronizar_alias_jugador_si_corresponde(form, alias_anterior):
    alias_anterior = normalizar_alias_jugador(alias_anterior)
    alias_nuevo = normalizar_alias_jugador(form.cleaned_data.get("aliasjugador"))
    usuario = obtener_usuario_por_alias(alias_anterior)

    if usuario is None or not usuario_es_jugador(usuario):
        with transaction.atomic():
            return form.save()

    if not alias_nuevo:
        form.add_error(
            "aliasjugador",
            "No se puede quitar el alias porque existe una cuenta vinculada.",
        )
        return None

    if User.objects.filter(username__iexact=alias_nuevo).exclude(pk=usuario.pk).exists():
        form.add_error(
            "aliasjugador",
            "Ya existe una cuenta con ese alias.",
        )
        return None

    jugador_pk = getattr(form.instance, "pk", None)
    if Jugador.objects.filter(aliasjugador__iexact=alias_nuevo).exclude(pk=jugador_pk).exists():
        form.add_error(
            "aliasjugador",
            "Ya existe otro jugador con ese alias.",
        )
        return None

    with transaction.atomic():
        jugador = form.save()
        if alias_nuevo != usuario.username:
            usuario.username = alias_nuevo
            usuario.save(update_fields=["username"])
    return jugador
