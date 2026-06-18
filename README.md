# SIAB

Sistema Integral de Administracion de Bingos.

## Stack

- Python 3
- Django 5
- PostgreSQL
- Bootstrap 5
- JavaScript

## Regla critica de base de datos

La estructura fisica de la base de datos ya fue aprobada por el docente.

No se deben modificar tablas, eliminar campos, modificar claves primarias, modificar claves foraneas ni redisenar el modelo.

En esta etapa no se ejecutan migraciones. Los modelos se prepararan despues para mapear exactamente la base aprobada.

## Uso local

```bash
source .venv/bin/activate
python manage.py check
python manage.py runserver 127.0.0.1:8000
```

Endpoints iniciales:

- `http://127.0.0.1:8000/`
- `http://127.0.0.1:8000/health/`
