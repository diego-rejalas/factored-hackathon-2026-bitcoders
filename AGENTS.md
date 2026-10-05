# Repository Guidelines

## Project Structure & Module Organization

This repository is an AI-first banking customer-service hackathon prototype. Read `doc/Factored AI & Data Hackathon 2026.md` before changing product behavior, then use `docs/CRITERIA.md`, `docs/DATA.md`, and `docs/ARCHITECTURE.md` as the implementation contract.

- `infra/gcp/airflow/` holds the Airflow image and the DAG `latam_bank_gcp` that runs on the GCP VM; `infra/gcp/etl/` is the Cloud Run Job fallback. Shared pipeline stages live in `data/pipeline/`.
- `data/dbt/` contains the dbt project (dbt-postgres): `models/staging/` builds `silver.*` and `models/gold/` supplies `gold.*` tables; custom tests live in `tests/`.
- GCP infrastructure is Terraform in `infra/gcp/` (`envs/dev|qa|prod`, shared `modules/`). Preview with `terraform plan`; the user runs privileged `apply`s. The Railway stack was removed (see git history).
- `backend/` (FastAPI tool layer, read-only database role), `agent/` (LangGraph) and `frontend/` (Next.js, Cloud Run) are implemented. Follow their README contracts.
- `doc/` is organizer material; do not edit it.

## Build, Test, and Development Commands

Work is the data pipeline. From `data/dbt/`, configure credentials before running:

```bash
cp .env.example .env
export $(cat .env | xargs)
dbt build     # build silver and gold models, testing each one before its dependents
```

Do not invent npm, Python, lint, or test commands for the not-yet-created services; add verified commands here with the implementation.

## Coding Style & Naming Conventions

Use four-space indentation for Python and SQL. Keep DAG code small and place reusable stage logic in `data/pipeline/`. Name dbt models by layer and entity: `stg_<entity>.sql` in `models/staging/` for source normalization, and `<entity>.sql` (no prefix) in `models/gold/` for backend-ready relations — medallion reserves cleaning for silver, so gold models are named by business entity/consumer, not "clean_*". Define model contracts in the adjacent `schema.yml`/`sources.yml` files.

Prefer deterministic policy and permission checks outside LLM prompts. The agent must access banking data only through the backend HTTP tool layer, never directly through Postgres. Preserve the documented rule that fraud ground-truth fields are not agent inputs.

## Testing Guidelines

Add dbt tests for keys, required values, accepted values, and relationships whenever a model changes. Run `dbt build` against the intended database before submitting data-pipeline work. For future services, add focused tests alongside the code and document the exact test command before treating it as required.

## Commit & Pull Request Guidelines

Use concise Conventional Commit-style subjects, as in `feat: add ingest_latam_bank DAG`, `fix: pin psycopg2-binary`, or `refactor: split dbt service`. Keep commits scoped to one vertical. Pull requests should explain the workflow impact, list validation performed, link the relevant spec or issue, and include screenshots for frontend changes. Flag data-model changes, Railway configuration changes, and any guardrail impact explicitly.
