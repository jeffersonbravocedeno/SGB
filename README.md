SIAB — Sistema Integral de Administración de Bingos
Sistema web desarrollado con Django y PostgreSQL para administrar socios, jugadores, préstamos, pagos, ahorros, aportes, bingos, partidas, cartones, ganadores y reportes.
Requisitos en Windows
    • Python 3.12
    • PostgreSQL y pgAdmin
    • Git
    • Visual Studio Code
    • Docker Desktop, opcional
1. Clonar y abrir el proyecto
git clone https://github.com/jeffersonbravocedeno/SGB.git
cd SGB
code .

2. Crear el entorno virtual
En la terminal integrada de Visual Studio Code:
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip

pip install -r requirements.txt

Si PowerShell bloquea la activación:
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1

Selecciona el intérprete:

3. Crear y restaurar la base de datos
El nombre de la base puede variar, por ejemplo:
bingo
siab
bingo_limpia

En pgAdmin:
    1. Crear una base vacía con el nombre deseado.
    2. Hacer clic derecho sobre la base.
    3. Seleccionar Restore.
    4. Elegir siab_base_limpia.backup.
    5. Seleccionar formato Custom or tar.
    6. Activar No owner y No privileges.
    7. Ejecutar la restauración.
No ejecutes python manage.py migrate antes de restaurar el respaldo.
4. Crear el archivo .env
En la raíz del proyecto crea un archivo llamado .env.
Genera una clave secreta:
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

Copia el resultado completo en SECRET_KEY.
SECRET_KEY=PEGA_AQUI_LA_CLAVE_GENERADA
DEBUG=True

ALLOWED_HOSTS=127.0.0.1,localhost
CSRF_TRUSTED_ORIGINS=http://127.0.0.1:8000,http://localhost:8000

DB_NAME=NOMBRE_DE_LA_BASE
DB_USER=USUARIO_DE_POSTGRESQL
DB_PASSWORD=CLAVE_DE_POSTGRESQL
DB_HOST=127.0.0.1
DB_PORT=5432
DB_CONN_MAX_AGE=0

REDIS_URL=redis://127.0.0.1:6379/0

LANGUAGE_CODE=es-ec
TIME_ZONE=America/Guayaquil

SECURE_SSL_REDIRECT=False
SESSION_COOKIE_SECURE=False
CSRF_COOKIE_SECURE=False

Reemplaza:
    • PEGA_AQUI_LA_CLAVE_GENERADA por la clave generada.
    • NOMBRE_DE_LA_BASE por el nombre usado en pgAdmin.
    • USUARIO_DE_POSTGRESQL por el usuario disponible, normalmente postgres.
    • CLAVE_DE_POSTGRESQL por su contraseña.
Ejemplo:
DB_NAME=bingo
DB_USER=postgres
DB_PASSWORD=mi_clave
DB_HOST=127.0.0.1
DB_PORT=5432

5. Ejecutar SIAB
Docker no es obligatorio para iniciar el sistema.

python manage.py runserver 
Abrir:
http://127.0.0.1:8000/

Administración:
http://127.0.0.1:8000/admin/

6. Docker y Redis — Opcional
Redis solo es necesario para WebSockets y las funciones en tiempo real.
docker compose -f docker-compose.realtime.yml up -d

Verificar:
docker compose -f docker-compose.realtime.yml ps

Detener:
docker compose -f docker-compose.realtime.yml down

Sin Docker, el sistema puede iniciarse con:
python manage.py runserver

pero las funciones en tiempo real pueden no estar disponibles.
La base de datos ya contiene un usuario admin

Usuario : admin
Contraseña: AdminSIAB2026!

Problemas frecuentes
La página no carga
Usa:
http://127.0.0.1:8000/

Y verifica:
DEBUG=True
SECURE_SSL_REDIRECT=False
SESSION_COOKIE_SECURE=False
CSRF_COOKIE_SECURE=False

PostgreSQL no conecta
Comprueba que DB_NAME, DB_USER, DB_PASSWORD, DB_HOST y DB_PORT coincidan con la configuración de pgAdmin.
Error relation does not exist
Restaura siab_base_limpia.backup sobre una base completamente vacía.
Error relacionado con siab_auditor
Restaura activando:
No owner
No privileges

Ese rol no es necesario para ejecutar SIAB.
El tiempo real no funciona
Abre Docker Desktop e inicia Redis:
docker compose -f docker-compose.realtime.yml up -d

Tecnologías principales
    • Django 5.2
    • PostgreSQL
    • Django Channels
    • Daphne
    • Redis, opcional
    • Bootstrap 5
    • JavaScript
    • ReportLab
    • OpenPyXL

