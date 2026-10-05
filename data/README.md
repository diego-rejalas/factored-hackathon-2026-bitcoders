# data/: data logic (not infrastructure)

Kept apart from `../infra/` on purpose. This folder holds **what** the pipeline does (the content), not **how it is deployed** (that is `infra/gcp/airflow/`). See `../docs/ARCHITECTURE.md` for the reasoning.

- `pipeline/`: the pipeline stages (S3 → bronze → silver) that the DAG and the job use.
- `dbt/`: the dbt project (the `bronze.*` → `silver.*` → `gold.*` transformation).

Both folders are baked into the `../infra/gcp/airflow/` image at build time.
