# infra/airflow/ — deployment de Airflow (standalone)

Solo config de despliegue acá — el contenido real (DAGs, dbt) vive en `../../data/`, separado a propósito. Ver `../../spec/ARCHITECTURE.md` (sección "Configuración de Railway como código") para el porqué de esta separación.

Fork fixeado de [`vergissberlin/railwayapp-airflow`](https://github.com/vergissberlin/railwayapp-airflow) — modo standalone (1 contenedor, SequentialExecutor), pensado para el volumen de datos de este hackathon, no para producción a escala.

## Fix sobre el template original

El template original crashea al montar un volumen de Railway: el contenedor corre como usuario no-root `airflow` (uid 50000), pero Railway monta volúmenes nuevos con dueño `root`, y el entrypoint no podía escribir ahí (`PermissionError` en `simple_auth_manager_passwords.json.generated.tmp`).

- `Dockerfile`: agregado `USER root` antes del `ENTRYPOINT`.
- `docker-entrypoint.sh`: agregado `chown -R "${AIRFLOW_UID:-50000}:0" /opt/airflow/data` después del `mkdir -p`. El `/entrypoint` oficial de la imagen base (invocado al final) sigue bajando privilegios al usuario `airflow` para el proceso final.

## Build context

El `Dockerfile` acá espera el **build context en la raíz del repo** (no esta carpeta), para poder copiar `data/dags/` y `data/dbt/` adentro de la imagen. Configurado en `.railway/railway.ts`: `rootDirectory: "/"`, `dockerfilePath: "infra/airflow/Dockerfile"`.

## Despliegue en Railway (Infrastructure as Code)

Todo el despliegue de este servicio (build, healthcheck, volumen, variables no-secretas) está declarado en `../../.railway/railway.ts` — no en un `railway.toml` acá (deprecado, ver `../../spec/ARCHITECTURE.md`). Para aplicar cambios:

```bash
railway config plan   # previsualizar
railway config apply  # aplicar
```

- Volumen montado en `/opt/airflow/data` (metadata DB SQLite + logs + password file — todo persistente ahí).
- Variables: ver `.env.example`. **`_AIRFLOW_WWW_USER_PASSWORD` debe rotarse** (el default `replace-with-strong-password` no sirve) — se mantiene con `preserve()` en el IaC, no se pisa desde el archivo.
- Deploy automático en cada push a `main` (Railway sigue el repo por GitHub App); `.railway/railway.ts` solo gestiona configuración, no dispara el build.

Detalle completo del mapeo de despliegue: `../../spec/AIRFLOW_DEPLOYMENT.md`.
