# etl/ — ETL con DuckDB (un solo job)

Vertical 1 y 2 de `../spec/ARCHITECTURE.md`. Un proceso, `run.py`, que corre hasta terminar:

```
S3 (CSV) --DuckDB read_csv--> bronze.* --dbt build--> silver.* + gold.* + 121 tests --si pasan--> Postgres gold.*
```

1. **Extraer y cargar.** DuckDB lee los CSV de S3 (`hive_partitioning` + `filename`) a `bronze.<tabla>`, todo como texto. Cada fila trae `_source_key` (el objeto de S3 de origen) y `_ingested_at`.
2. **Transformar y probar.** `dbt build` (proyecto en `../data/dbt/`, adaptador dbt-duckdb) sobre el mismo archivo: 13 vistas silver, 5 tablas gold, 121 tests. Cada modelo se prueba antes de construir los que dependen de él.
3. **Publicar.** Solo si `dbt build` no tuvo errores, gold se copia a Postgres (`PUBLISH_SCHEMA`, por defecto `gold`), se indexa y se intercambia en una sola transacción. Si algo falla antes, Postgres conserva el último gold válido.

Cada corrida deja una fila en `ops.etl_runs` (estado, conteos, resultado de tests).

## Variables de entorno

| Variable | Uso |
|---|---|
| `LATAM_BANK_AWS_ACCESS_KEY_ID`, `LATAM_BANK_AWS_SECRET_ACCESS_KEY`, `AWS_REGION` | lectura del bucket (credenciales de solo lectura del organizador, nunca en el repo) |
| `PG_HOST`, `PG_PORT`, `PG_USER`, `PG_PASSWORD`, `PG_DATABASE` | Postgres de servicio donde se publica gold |
| `PUBLISH_SCHEMA` | schema destino (`gold`); usar otro para una corrida de prueba |
| `DUCKDB_PATH` | archivo de trabajo (`/tmp/latam.duckdb`); se borra y reconstruye en cada corrida |

Las credenciales que aparecen en un mensaje de error se ocultan antes de loguear o guardar.

## Correr

En Railway corre en cada deploy (reintentos: `ON_FAILURE`, 3 intentos) y solo se redeploya si cambia `etl/` o `data/dbt/`. Para repetirlo sin cambios, redeployar el servicio `etl` desde Railway.

Localmente, con las variables de arriba exportadas:

```bash
pip install -r etl/requirements.txt
cp -r data/dbt etl/dbt        # run.py busca el proyecto dbt junto a sí mismo (DBT_DIR lo cambia)
python etl/run.py
```

## Resultado medido (Railway, 2026-09-30)

~4,7 min de punta a punta: S3 a bronze ~2 min (23,5M filas), `dbt build` 22 s, publicación ~2 min. Mismos conteos en las 13 tablas y sumas de importes iguales al centavo que el pipeline anterior (Airflow + dbt sobre Postgres).
