# SIAB — Sistema Integral de Administración de Bingos

SIAB es un sistema web desarrollado con **Django** y **PostgreSQL** para administrar:

* Socios y jugadores.
* Préstamos y pagos.
* Ahorros y aportes.
* Bingos y partidas.
* Cartones.
* Ganadores.
* Reportes administrativos.

---

## 1. Requisitos para Windows

Antes de instalar el proyecto, verifica que tengas:

* Python 3.12.
* PostgreSQL.
* pgAdmin 4.
* Git.
* Visual Studio Code.
* Docker Desktop, opcional.

Docker solamente es necesario para utilizar Redis y algunas funciones en tiempo real.

---

## 2. Clonar el proyecto

Abre PowerShell o la terminal de Visual Studio Code y ejecuta:

```powershell
git clone https://github.com/jeffersonbravocedeno/SGB.git
cd SGB
code .
```

---

## 3. Crear el entorno virtual

Desde la terminal integrada de Visual Studio Code, ejecuta:

```powershell
py -3.12 -m venv .venv
```

Activa el entorno virtual:

```powershell
.\.venv\Scripts\Activate.ps1
```

Cuando esté correctamente activado, la terminal mostrará algo similar a:

```text
(.venv) PS C:\Users\Usuario\Desktop\SGB>
```

### PowerShell bloquea la activación

Ejecuta:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Luego vuelve a activar el entorno:

```powershell
.\.venv\Scripts\Activate.ps1
```

---

## 4. Instalar las dependencias

Con el entorno virtual activado, ejecuta:

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

---

## 5. Seleccionar el intérprete de Python

En Visual Studio Code:

1. Presiona `Ctrl + Shift + P`.
2. Busca `Python: Select Interpreter`.
3. Selecciona el intérprete ubicado en:

```text
SGB\.venv\Scripts\python.exe
```

---

## 6. Crear y restaurar la base de datos

El nombre de la base de datos puede variar. Por ejemplo:

```text
bingo
siab
bingo_limpia
```

El nombre que elijas deberá ser el mismo que coloques posteriormente en `DB_NAME`.

### Restauración mediante pgAdmin

1. Abre pgAdmin.
2. Conéctate al servidor PostgreSQL.
3. Crea una base de datos completamente vacía.
4. Asigna el nombre que desees, por ejemplo `bingo`.
5. Haz clic derecho sobre la base creada.
6. Selecciona **Restore** o **Restaurar**.
7. Selecciona el archivo:

```text
siab_base_limpia.backup
```

8. Comprueba que el formato sea **Custom or tar**.
9. En las opciones de restauración, activa:

   * **No owner** o **Sin propietario**.
   * **No privileges** o **Sin privilegios**.
10. Ejecuta la restauración.

> No ejecutes `python manage.py migrate` antes de restaurar el respaldo. El archivo de respaldo ya contiene la estructura necesaria de la base de datos.

---

## 7. Crear el archivo `.env`

En la raíz del proyecto, en la misma ubicación donde se encuentra `manage.py`, crea un archivo llamado:

```text
.env
```

### Generar la clave secreta

Con el entorno virtual activado, ejecuta:

```powershell
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Copia el resultado completo y colócalo en la variable `SECRET_KEY`.

### Contenido del archivo `.env`

```env
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
```

Reemplaza los siguientes valores:

* `PEGA_AQUI_LA_CLAVE_GENERADA`: clave generada mediante el comando anterior.
* `NOMBRE_DE_LA_BASE`: nombre utilizado al crear la base en pgAdmin.
* `USUARIO_DE_POSTGRESQL`: usuario de PostgreSQL, normalmente `postgres`.
* `CLAVE_DE_POSTGRESQL`: contraseña del usuario de PostgreSQL.

### Ejemplo de configuración

```env
DB_NAME=bingo
DB_USER=postgres
DB_PASSWORD=mi_clave
DB_HOST=127.0.0.1
DB_PORT=5432
```

> No subas el archivo `.env` a GitHub, ya que contiene contraseñas y configuraciones privadas.

---

## 8. Verificar el proyecto

Antes de iniciar el servidor, ejecuta:

```powershell
python manage.py check
```

Si todo está correctamente configurado, aparecerá un mensaje similar a:

```text
System check identified no issues.
```

---

## 9. Ejecutar SIAB

Docker no es obligatorio para iniciar el sistema.

Ejecuta:

```powershell
python manage.py runserver
```

Abre el sistema en:

```text
http://127.0.0.1:8000/
```

Panel de administración:

```text
http://127.0.0.1:8000/admin/
```

---

## 10. Usuario administrador

La base de datos restaurada ya contiene un usuario administrador.

```text
Usuario: admin
Contraseña: AdminSIAB2026!
```

Se recomienda cambiar la contraseña después del primer inicio de sesión.

También puede cambiarse desde la terminal con:

```powershell
python manage.py changepassword admin
```

---

## 11. Docker y Redis

Redis es opcional. Solamente es necesario para los WebSockets y determinadas funciones en tiempo real, como las actualizaciones simultáneas durante una partida.

Primero abre Docker Desktop y espera hasta que indique que Docker está funcionando.

### Iniciar Redis

```powershell
docker compose -f docker-compose.realtime.yml up -d
```

### Verificar el contenedor

```powershell
docker compose -f docker-compose.realtime.yml ps
```

### Detener Redis

```powershell
docker compose -f docker-compose.realtime.yml down
```

Sin Docker, SIAB puede iniciarse normalmente mediante:

```powershell
python manage.py runserver
```

Sin embargo, algunas funciones en tiempo real podrían no estar disponibles.

---

## 12. Problemas frecuentes

### La página no carga

Asegúrate de utilizar exactamente esta dirección:

```text
http://127.0.0.1:8000/
```

No utilices `https://` durante la ejecución local.

Comprueba también estas variables en el archivo `.env`:

```env
DEBUG=True
SECURE_SSL_REDIRECT=False
SESSION_COOKIE_SECURE=False
CSRF_COOKIE_SECURE=False
```

Después de modificar el archivo `.env`, detén el servidor con `Ctrl + C` y vuelve a iniciarlo:

```powershell
python manage.py runserver
```

---

### PostgreSQL no conecta

Comprueba que los siguientes datos coincidan con la configuración de pgAdmin:

```env
DB_NAME=
DB_USER=
DB_PASSWORD=
DB_HOST=127.0.0.1
DB_PORT=5432
```

También verifica que el servicio de PostgreSQL esté iniciado en Windows.

---

### Error `relation does not exist`

Este error normalmente significa que la base de datos no fue restaurada correctamente.

Solución:

1. Elimina la base de datos que presenta el error.
2. Crea una base de datos completamente vacía.
3. Restaura nuevamente `siab_base_limpia.backup`.
4. Activa las opciones **Sin propietario** y **Sin privilegios**.
5. Comprueba que `DB_NAME` tenga el mismo nombre de la base restaurada.

---

### Error relacionado con `siab_auditor`

Restaura el respaldo activando:

* **Sin propietario**.
* **Sin privilegios**.

El rol `siab_auditor` no es necesario para ejecutar SIAB normalmente.

---

### El tiempo real no funciona

Abre Docker Desktop e inicia Redis:

```powershell
docker compose -f docker-compose.realtime.yml up -d
```

Luego verifica su estado:

```powershell
docker compose -f docker-compose.realtime.yml ps
```

Después reinicia el servidor de Django:

```powershell
python manage.py runserver
```

---

### Docker Desktop no inicia

Docker es opcional. Puedes ejecutar el sistema sin Docker:

```powershell
python manage.py runserver
```

El sistema principal funcionará, pero las características que dependan de Redis o WebSockets podrían no estar disponibles.

---

### El entorno virtual no aparece activado

Ejecuta:

```powershell
.\.venv\Scripts\Activate.ps1
```

La terminal debe mostrar `(.venv)` al inicio de la línea.

---

### Error al instalar dependencias

Asegúrate de ejecutar el comando correctamente:

```powershell
pip install -r requirements.txt
```

No utilices:

```powershell
pip install requirements.txt
```

---

## 13. Tecnologías principales

* Python 3.12.
* Django 5.2.
* PostgreSQL.
* Django Channels.
* Daphne.
* Redis, opcional.
* Docker, opcional.
* Bootstrap 5.
* JavaScript.
* ReportLab.
* OpenPyXL.

---

## 14. Inicio rápido

Para iniciar el proyecto después de haber completado la instalación:

```powershell
cd SGB
.\.venv\Scripts\Activate.ps1
python manage.py runserver
```

Luego abre:

```text
http://127.0.0.1:8000/
```

Para utilizar también las funciones en tiempo real:

```powershell
docker compose -f docker-compose.realtime.yml up -d
python manage.py runserver
```
