# Airflow (standalone)

Fork fixeado de [`vergissberlin/railwayapp-airflow`](https://github.com/vergissberlin/railwayapp-airflow) — modo standalone (1 contenedor, SequentialExecutor), pensado para el volumen de datos de este hackathon, no para producción a escala.

## Fix sobre el template original

El template original crashea al montar un volumen de Railway: el contenedor corre como usuario no-root `airflow` (uid 50000), pero Railway monta volúmenes nuevos con dueño `root`, y el entrypoint no podía escribir ahí (`PermissionError` en `simple_auth_manager_passwords.json.generated.tmp`).

- `Dockerfile`: agregado `USER root` antes del `ENTRYPOINT`.
- `docker-entrypoint.sh`: agregado `chown -R "${AIRFLOW_UID:-50000}:0" /opt/airflow/data` después del `mkdir -p`. El `/entrypoint` oficial de la imagen base (invocado al final) sigue bajando privilegios al usuario `airflow` para el proceso final.

## Despliegue en Railway

- Servicio con `rootDirectory: airflow`, builder Dockerfile.
- Volumen montado en `/opt/airflow/data` (metadata DB SQLite + logs + password file — todo persistente ahí).
- Variables: ver `.env.example`. **`_AIRFLOW_WWW_USER_PASSWORD` debe rotarse** (el default `replace-with-strong-password` no sirve).
- Deploy automático en cada push a `main` que toque `airflow/**` (Railway sigue el repo por GitHub App).

Detalle completo del mapeo de despliegue: `../spec/AIRFLOW_DEPLOYMENT.md`.
