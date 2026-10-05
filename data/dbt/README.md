# data/dbt/: dbt (bronze → silver → gold)

Vertical 2 of `../../docs/ARCHITECTURE.md`. It transforms `bronze.*` (loaded by the `latam_bank_gcp` DAG with DuckDB, see `../../infra/gcp/airflow/`) into `silver.*` and `gold.*` (what `../../backend/` reads), inside Postgres's `data` database.

This is data content, not infrastructure: how dbt is deployed lives in `../../infra/gcp/airflow/` (the VM) and `../../infra/gcp/etl/` (the Cloud Run Job).

**dbt runs inside the Airflow image on GCP** (`dbt-duckdb`), not as a separate service. The project also compiles against Postgres (`--target postgres`) for local tests.

## Structure

- `models/staging/stg_*.sql`: one view for each of the 13 bronze tables. It casts to real types, turns `''` into `NULL`, and has no business logic except conforming values (`macros/normalize_country.sql` unifies 'Mexico' and 'México'). Views in the `silver` schema.
- `models/staging/sources.yml`: declares the 13 `bronze.*` tables as a source, with the findings from `../../docs/DATA.md` documented per table.
- `models/staging/schema.yml`: tests (`not_null`, `unique`, `accepted_values`, `relationships`, `accepted_range`, `unique_combination`). These are the "data contracts" the challenge asks for. Known data defects run with `severity: warn`, so they do not stop the run but appear with their count in every build.
- `tests/generic/`: our own generic tests (`accepted_range`, `unique_combination`). `tests/*.sql`: business rules (transaction-to-product ownership, measured complaint defects, balance over limit, and so on).
- `models/gold/<entity>.sql`: tables materialized in the `gold` schema, which the tool layer (`backend/`) reads. There is no `clean_` prefix: the medallion pattern reserves cleaning (casts, nulls) for silver, and gold is named by business entity or consumer. Today they are pass-throughs of silver (no joins yet).
- `models/gold/schema.yml`: the same tests on the final layer.

## Data quality decisions already made (do not reinvent them when writing new models)

- **`gold.transactions` excludes `is_fraud` and `fraud_score`.** They are evaluation ground truth and never agent input (leakage). If a new model needs fraud as a feature, that is a bug.
- **`currency` never corrects the absence of MXN.** It is documented as a real data limit (see `../../docs/DATA.md`), and no conversion is invented.
- **`contact_reason` and `reason_category`** in `call_center_interactions` are the same field in practice. Do not assume they give more granularity than they do.

## Running locally

```bash
cd data/dbt
cp .env.example .env   # fill in the local Postgres credentials
export $(cat .env | xargs)
dbt build   # models + tests, each model is tested before building what depends on it
```

With the `postgres` target it needs `bronze.*` to be already loaded in that database. On GCP it is not needed: the DAG builds everything in memory with `dbt-duckdb` and publishes only `gold.*`.

## Great Expectations

Evaluated and dropped for now. It overlaps with the dbt tests above (the same kind of check: not_null, accepted values, uniqueness). The only thing it would add is an HTML report (Data Docs) for the pitch video. If the team wants it for that, add it later. It does not replace the dbt tests.
