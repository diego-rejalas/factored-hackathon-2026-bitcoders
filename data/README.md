# data/ — lógica de datos (no infraestructura)

Separado de `../infra/` a propósito: acá vive **qué hace** el pipeline (contenido), no **cómo se despliega** (eso es `infra/airflow/`). Ver `../spec/ARCHITECTURE.md` para el razonamiento.

- `dags/` — DAGs de Airflow (bootstrap de `data`, ingesta: S3 → `bronze.*`, luego trigger de dbt).
- `dbt/` — proyecto dbt (transformación `bronze.*` → `silver.*` → `gold.*`).

Ambas carpetas se hornean dentro de la imagen de `../infra/airflow/` en build time.
