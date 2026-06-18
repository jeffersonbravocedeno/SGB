# Base de Datos

La base PostgreSQL se configura para conexion desde Django, pero la estructura fisica aprobada no debe alterarse.

Politica:

- No modificar tablas.
- No eliminar campos.
- No modificar claves primarias.
- No modificar claves foraneas.
- No ejecutar migraciones sin autorizacion.

Usuario sugerido de aplicacion:

- Base: `siab_db`
- Usuario Django: `siab_app`

En este workspace se puede usar socket Unix local si el entorno no permite abrir puertos TCP:

```env
DB_HOST=/tmp
DB_PORT=5432
```

Cuando las tablas aprobadas ya existan, se pueden conceder permisos DML al usuario de aplicacion:

```sql
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO siab_app;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO siab_app;
```
