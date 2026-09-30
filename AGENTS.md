# Repository Guidelines

## Project Structure & Module Organization

This repository is an AI-first banking customer-service hackathon prototype. Read `doc/Factored AI & Data Hackathon 2026.md` before changing product behavior, then use `spec/CRITERIA.md`, `spec/DATA_FINDINGS.md`, and `spec/ARCHITECTURE.md` as the implementation contract.

- `etl/` is the whole pipeline as one job (`etl/run.py`): DuckDB reads the CSVs from S3 into bronze, `dbt build` builds and tests silver and gold, and only if every test passed the gold tables are published to Postgres (the serving database).
- `data/dbt/` contains the dbt project (dbt-duckdb): `models/staging/` builds `silver.*` and `models/gold/` supplies `gold.*` tables; custom tests live in `tests/`.
- Railway configuration is centralized in `.railway/railway.ts`.
- `backend/`, `agent/`, and `frontend/` are reserved for the banking tool layer, guarded agent, and chat UI. Follow their README contracts when adding them.
- `doc/` is organizer material; do not edit it.

## Build, Test, and Development Commands

Work is the data pipeline. From `data/dbt/`, configure credentials before running:

```bash
cp .env.example .env
export $(cat .env | xargs)
dbt build     # build silver and gold models, testing each one before its dependents
```

Railway configuration changes should be previewed with `railway config plan` before `railway config apply`. Do not invent npm, Python, lint, or test commands for the not-yet-created services; add verified commands here with the implementation.

## Coding Style & Naming Conventions

Use four-space indentation for Python and SQL. Keep `etl/run.py` small and readable: one job, no framework. Name dbt models by layer and entity: `stg_<entity>.sql` in `models/staging/` for source normalization, and `<entity>.sql` (no prefix) in `models/gold/` for backend-ready relations — medallion reserves cleaning for silver, so gold models are named by business entity/consumer, not "clean_*". Define model contracts in the adjacent `schema.yml`/`sources.yml` files.

Prefer deterministic policy and permission checks outside LLM prompts. The agent must access banking data only through the backend HTTP tool layer, never directly through Postgres. Preserve the documented rule that fraud ground-truth fields are not agent inputs.

## Testing Guidelines

Add dbt tests for keys, required values, accepted values, and relationships whenever a model changes. Run `dbt build` against the intended database before submitting data-pipeline work. For future services, add focused tests alongside the code and document the exact test command before treating it as required.

## Commit & Pull Request Guidelines

Use concise Conventional Commit-style subjects, as in `feat: add ingest_latam_bank DAG`, `fix: pin psycopg2-binary`, or `refactor: split dbt service`. Keep commits scoped to one vertical. Pull requests should explain the workflow impact, list validation performed, link the relevant spec or issue, and include screenshots for frontend changes. Flag data-model changes, Railway configuration changes, and any guardrail impact explicitly.
