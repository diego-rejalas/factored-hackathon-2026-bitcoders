# data/ — lógica de datos (no infraestructura)

Separado de `../infra/` a propósito: acá vive **qué hace** el pipeline (contenido), no **cómo se despliega** (eso es `infra/gcp/airflow/`). Ver `../docs/ARCHITECTURE.md` para el razonamiento.

- `pipeline/` — etapas del pipeline (S3 → bronze → silver) que usa el DAG y el job.
- `dbt/` — proyecto dbt (transformación `bronze.*` → `silver.*` → `gold.*`).

Ambas carpetas se hornean dentro de la imagen de `../infra/gcp/airflow/` en build time.
