# Despliegue de Airflow y del pipeline de datos

Estado real en Railway (proyecto `factored-hackathon`), gestionado como código en `../.railway/railway.ts` (ver `ARCHITECTURE.md`, sección "Configuración de Railway como código").

## Piezas

| Servicio | Qué es | Fuente en el repo |
|---|---|---|
| `airflow` | orquesta el DAG `latam_bank_pipeline`; DuckDB extrae de S3 y carga a `bronze.*` | `infra/airflow/` (imagen) y `data/dags/` (DAG) |
| `airflow-db` | Postgres propio con la metadata de Airflow (corridas, estados), separado del de datos | addon |
| `dbt` | runner HTTP de dbt (`POST /run` ejecuta `dbt build` con un candado) | `infra/dbt/` y `data/dbt/` |
| `postgres` | base `data`: `bronze`, `silver`, `gold`, `ops` | addon |

Todos con `rootDirectory: "/"` y Dockerfile propio; se redeployan solo si cambian sus rutas (`watchPatterns` en la IaC), así un push de documentación no los reinicia.

## El DAG

```
bootstrap -> extract_load x 13 (paralelo, máx. 6) -> dbt_build -> record_run
```

`extract_load` ejecuta por tabla una sola sentencia de DuckDB que lee S3 y escribe en Postgres (`data/dags/lib/extract_load.py`). `dbt_build` llama al servicio `dbt` por la red privada solo cuando las 13 cargas terminaron. `record_run` deja una fila en `ops.etl_runs`. Se dispara a demanda desde la UI (el dataset es un snapshot estático, no hay programación ni frescura que mantener).

## Variables (nombres; los valores nunca van en el repo)

- **airflow:** `AIRFLOW__DATABASE__SQL_ALCHEMY_CONN` (referencia a `airflow-db`), `DBT_SERVICE_URL` (referencia al dominio privado de `dbt`), `PG_*` (referencias al Postgres de datos), `AWS_REGION`, `_AIRFLOW_WWW_USER_USERNAME`, y con `preserve()` las que se cargan a mano: `_AIRFLOW_WWW_USER_PASSWORD`, `LATAM_BANK_AWS_ACCESS_KEY_ID`, `LATAM_BANK_AWS_SECRET_ACCESS_KEY`.
- **dbt:** `DBT_PG_*` (referencias) y `PORT=80`, para que el dominio privado (que implica el puerto 80) funcione sin concatenar un puerto.

Las credenciales de S3 son de solo lectura y las entrega el organizador. Se cargan una vez desde un `.env` local (ignorado por git; plantilla en `../.env.example`) con `railway variable set`, nunca desde un archivo versionado.

## Lecciones que quedaron en la configuración

- El contenedor corre como `airflow` (uid 50000) pero Railway monta volúmenes nuevos como `root`: el `docker-entrypoint.sh` hace `chown` del volumen antes de ceder el proceso (`infra/airflow/`).
- Las dependencias de `dbt` chocan con el archivo de constraints de Airflow; por eso dbt es un servicio aparte y no se instala en la imagen de Airflow.
- Una referencia entre servicios (`${{servicio.VARIABLE}}`) se resuelve a vacío si el servicio de origen se borra: las credenciales deben vivir en el servicio que las usa.
- Railway no admite 0 réplicas; un servicio no se "apaga", se borra.

## Cómo reproducir desde cero

```bash
railway login && railway link
railway config plan    # previsualizar
railway config apply   # aplicar
# cargar las credenciales de S3 (ver .env.example) y la contraseña de Airflow
```
