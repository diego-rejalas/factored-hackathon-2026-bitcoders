# data/dbt/ — dbt (raw. → clean.)

Vertical 2 de `../../spec/ARCHITECTURE.md`. Proyecto dbt sobre el Postgres del proyecto: transforma `raw.*` (volcado por el DAG en `../dags/`) en `clean.*` (lo que lee `../../backend/`).

Contenido de datos, no de infraestructura — la config de cómo se despliega Airflow (que ejecuta esto) vive aparte en `../../infra/airflow/`. Horneado dentro de la imagen de Airflow en build time (`../../infra/airflow/Dockerfile` copia esta carpeta a `/opt/airflow/dbt/`) — simple y suficiente a esta escala; el patrón de mercado a mayor escala (imagen de dbt separada, disparada por un operator) queda documentado como camino de escalamiento en `../../spec/ARCHITECTURE.md`, no implementado ahora.

Pendiente de crear (una vez el equipo vote el workflow):
- `dbt_project.yml`, `profiles.yml` (o variables de conexión vía env vars, no hardcodeadas)
- `models/staging/stg_*.sql` — cast de tipos, nulls tratados
- `models/clean/clean_*.sql` — joins resueltos, listos para el tool layer
- `models/schema.yml` — tests (`not_null`, `unique`, `accepted_values`) sobre los campos clave

Ver hallazgos de calidad de datos a resolver acá en `../../spec/DATA_FINDINGS.md` (nulls, ausencia de MXN, etc).
