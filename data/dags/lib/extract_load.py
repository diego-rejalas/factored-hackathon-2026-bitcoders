"""Extract and load with DuckDB: S3 (CSV) -> Postgres bronze, one statement per table.

DuckDB reads the organizer's CSVs straight from S3 and writes them into a
Postgres table through its postgres extension, so extraction and load are the
same SQL statement: no separate loader, no ledger. Every bronze table is a
faithful copy (all columns as text) plus two lineage columns: _source_key (the
S3 object the row came from) and _ingested_at. The transformations live in dbt.

Each run reloads a table from scratch (DROP + CREATE): the dataset is a static
snapshot, so a full reload is the simplest thing that is always correct. Nothing
reads bronze except dbt, and the backend reads only gold, so the drop window is
harmless.

Credentials come from the environment set on the Airflow service in
.railway/railway.ts (LATAM_BANK_AWS_*, PG_*), never hardcoded here.
"""
import datetime as dt
import json
import os

import duckdb

BUCKET = os.environ.get("LATAM_BANK_S3_BUCKET", "factored-datathon-2026-s3-157725502942-us-east-2-an")

# data/<name>.csv
FLAT = ["customers", "products", "branches", "service_agents", "marketing_campaigns", "daily_exchange_rates"]
# data/<name>/year=YYYY/month=MM/day=DD/<name>_YYYYMMDD.csv
PARTITIONED = [
    "transactions", "complaints", "call_center_interactions", "call_transcripts",
    "satisfaction_surveys", "campaign_sends", "digital_events",
]
ALL_TABLES = FLAT + PARTITIONED

SCHEMAS = ("bronze", "silver", "gold", "ops")

# Several tables load at once (see max_active_tasks in the DAG): bound each one.
THREADS = int(os.environ.get("DUCKDB_THREADS", "4"))
MEMORY_LIMIT = os.environ.get("DUCKDB_MEMORY_LIMIT", "3GB")


def _scrub(text: str) -> str:
    """Errors from ATTACH or S3 can echo the connection string; never log a secret."""
    for name in ("PG_PASSWORD", "LATAM_BANK_AWS_SECRET_ACCESS_KEY", "LATAM_BANK_AWS_ACCESS_KEY_ID"):
        secret = os.environ.get(name)
        if secret:
            text = text.replace(secret, "***")
    return text


def _pg_dsn() -> str:
    return (
        f"host={os.environ['PG_HOST']} port={os.environ.get('PG_PORT', '5432')} "
        f"dbname={os.environ['PG_DATABASE']} user={os.environ['PG_USER']} password={os.environ['PG_PASSWORD']}"
    )


def _connect(with_s3: bool) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute(f"SET threads = {THREADS}; SET memory_limit = '{MEMORY_LIMIT}'")
    con.execute("INSTALL postgres; LOAD postgres;")
    con.execute(f"ATTACH '{_pg_dsn()}' AS pg (TYPE postgres)")
    if with_s3:
        con.execute("INSTALL httpfs; LOAD httpfs;")
        con.execute(
            "CREATE OR REPLACE SECRET s3 (TYPE S3, KEY_ID '%s', SECRET '%s', REGION '%s')"
            % (
                os.environ["LATAM_BANK_AWS_ACCESS_KEY_ID"],
                os.environ["LATAM_BANK_AWS_SECRET_ACCESS_KEY"],
                os.environ.get("AWS_REGION", "us-east-2"),
            )
        )
        # Reads that drop mid-transfer are retried by DuckDB itself.
        con.execute("SET http_retries = 6; SET http_retry_wait_ms = 1000")
    return con


def _pg(con: duckdb.DuckDBPyConnection, sql: str) -> None:
    """Run DDL on Postgres. Several statements in one call run as one transaction."""
    escaped = sql.replace("'", "''")
    con.execute(f"CALL postgres_execute('pg', '{escaped}')")


def bootstrap() -> dict:
    """Make sure the medallion schemas (and the run log's schema) exist."""
    con = _connect(with_s3=False)
    try:
        _pg(con, "; ".join(f"CREATE SCHEMA IF NOT EXISTS {schema}" for schema in SCHEMAS))
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(_scrub(f"{type(exc).__name__}: {exc}")) from None
    finally:
        con.close()
    return {"schemas": list(SCHEMAS)}


def extract_load(table: str, source_root: str | None = None, target_schema: str = "bronze") -> dict:
    """One table: S3 -> DuckDB -> Postgres <target_schema>.<table>.

    `source_root` and `target_schema` exist so the statement can be exercised
    against local files and a scratch schema; production uses the defaults.
    """
    root = source_root or f"s3://{BUCKET}"
    path = f"data/{table}.csv" if table in FLAT else f"data/{table}/*/*/*/*.csv"
    hive = "" if table in FLAT else ", hive_partitioning = true, hive_types_autocast = false"
    con = _connect(with_s3=root.startswith("s3://"))
    try:
        # CASCADE: silver views built on the old table go with it; dbt recreates them.
        _pg(con, f"DROP TABLE IF EXISTS {target_schema}.{table} CASCADE")
        con.execute(
            f"""
            CREATE TABLE pg.{target_schema}.{table} AS
            SELECT * EXCLUDE (filename), filename AS _source_key, current_timestamp AS _ingested_at
            FROM read_csv('{root}/{path}', all_varchar = true, filename = true{hive})
            """
        )
        rows = con.execute(f"SELECT count(*) FROM pg.{target_schema}.{table}").fetchone()[0]
    except Exception as exc:  # noqa: BLE001 - re-raised with secrets removed
        raise RuntimeError(_scrub(f"{type(exc).__name__}: {exc}")) from None
    finally:
        con.close()
    if rows == 0:
        raise RuntimeError(f"{target_schema}.{table} is empty: nothing matched {root}/{path}")
    return {"table": table, "rows": rows}


def record_run(run_id: str, started: dt.datetime, status: str, detail: dict) -> None:
    """One row per successful run in ops.etl_runs: when it ran and what it moved."""
    con = _connect(with_s3=False)
    try:
        _pg(
            con,
            "CREATE TABLE IF NOT EXISTS ops.etl_runs (run_id text PRIMARY KEY, started_at timestamptz, "
            "finished_at timestamptz, status text, detail text)",
        )
        con.execute(
            "INSERT INTO pg.ops.etl_runs VALUES (?, ?, ?, ?, ?)",
            [run_id, started, dt.datetime.now(dt.timezone.utc), status, json.dumps(detail)],
        )
    finally:
        con.close()
