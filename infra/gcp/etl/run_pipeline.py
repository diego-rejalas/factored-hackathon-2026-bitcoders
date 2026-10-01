"""Ultra-lightweight ETL pipeline runner for GCP (Cloud Run Job).

Architecture:
  1. DuckDB reads organizer's CSVs from S3 into local ephemeral DuckDB (/tmp/latam.duckdb) -> bronze.*
  2. dbt-duckdb builds silver views and gold tables, running all 121 tests locally in RAM.
  3. Only if all tests pass, publishes EXCLUSIVELY the 5 gold.* tables to Cloud SQL PostgreSQL.
  4. Purges any residual bronze/silver tables from Cloud SQL to keep disk usage minimal.
  5. Records the run in ops.etl_runs.
"""

import datetime as dt
import json
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path

import duckdb

BUCKET = os.environ.get("LATAM_BANK_S3_BUCKET", "factored-datathon-2026-s3-157725502942-us-east-2-an")
DB_PATH = os.environ.get("DUCKDB_PATH", "/tmp/latam.duckdb")
DBT_DIR = os.environ.get("DBT_DIR", "/app/dbt")
PUBLISH_SCHEMA = os.environ.get("PUBLISH_SCHEMA", "gold")
THREADS = int(os.environ.get("DUCKDB_THREADS", "4"))
MEMORY_LIMIT = os.environ.get("DUCKDB_MEMORY_LIMIT", "8GB")

# data/<name>.csv
FLAT = ["customers", "products", "branches", "service_agents", "marketing_campaigns", "daily_exchange_rates"]
# data/<name>/year=YYYY/month=MM/day=DD/<name>_YYYYMMDD.csv
PARTITIONED = [
    "transactions", "complaints", "call_center_interactions", "call_transcripts",
    "satisfaction_surveys", "campaign_sends", "digital_events",
]

# Published tables: key is primary/unique; indexes support backend queries.
GOLD = {
    "customers": {"key": ["customer_id"], "indexes": [["document_number"]]},
    "products": {"key": ["product_id"], "indexes": [["customer_id"]]},
    "transactions": {
        "key": ["transaction_id"],
        "indexes": [["customer_id", "transaction_date"], ["product_id"]],
    },
    "complaints": {"key": ["complaint_id"], "indexes": [["customer_id"]]},
    "call_center_interactions": {"key": ["interaction_id"], "indexes": [["customer_id"]]},
}


def _scrub(text: str) -> str:
    """Never log database passwords or AWS secrets."""
    for name in ("PG_PASSWORD", "LATAM_BANK_AWS_SECRET_ACCESS_KEY", "LATAM_BANK_AWS_ACCESS_KEY_ID"):
        secret = os.environ.get(name)
        if secret:
            text = text.replace(secret, "***")
    return text


def log(msg: str) -> None:
    print(f"[{dt.datetime.now(dt.timezone.utc):%H:%M:%S}] [etl] {_scrub(msg)}", flush=True)


def _pg_dsn() -> str:
    return (
        f"host={os.environ['PG_HOST']} port={os.environ.get('PG_PORT', '5432')} "
        f"dbname={os.environ['PG_DATABASE']} user={os.environ['PG_USER']} password={os.environ['PG_PASSWORD']}"
    )


def _pg(con: duckdb.DuckDBPyConnection, sql: str) -> None:
    """Run DDL on Postgres via DuckDB postgres extension."""
    escaped = sql.replace("'", "''")
    con.execute(f"CALL postgres_execute('pg', '{escaped}')")


def extract_load_bronze(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    """S3 (CSVs) -> local DuckDB bronze.<table>, all text + lineage columns."""
    missing = [k for k in ("LATAM_BANK_AWS_ACCESS_KEY_ID", "LATAM_BANK_AWS_SECRET_ACCESS_KEY") if not os.environ.get(k, "").strip()]
    if missing:
        raise RuntimeError(f"Missing S3 credentials: {', '.join(missing)}")

    con.execute(f"SET threads = {THREADS}; SET memory_limit = '{MEMORY_LIMIT}';")
    con.execute("INSTALL httpfs; LOAD httpfs;")
    con.execute(
        "CREATE OR REPLACE SECRET s3 (TYPE S3, KEY_ID '%s', SECRET '%s', REGION '%s')"
        % (
            os.environ["LATAM_BANK_AWS_ACCESS_KEY_ID"],
            os.environ["LATAM_BANK_AWS_SECRET_ACCESS_KEY"],
            os.environ.get("AWS_REGION", "us-east-2"),
        )
    )
    con.execute("SET http_retries = 6; SET http_retry_wait_ms = 1000;")
    con.execute("CREATE SCHEMA IF NOT EXISTS bronze;")

    counts: dict[str, int] = {}
    for table in FLAT + PARTITIONED:
        path = f"data/{table}.csv" if table in FLAT else f"data/{table}/*/*/*/*.csv"
        hive = "" if table in FLAT else ", hive_partitioning = true"
        log(f"reading s3://{BUCKET}/{path} -> bronze.{table}...")
        con.execute(
            f"""
            CREATE OR REPLACE TABLE bronze.{table} AS
            SELECT * EXCLUDE (filename), filename AS _source_key, current_timestamp AS _ingested_at
            FROM read_csv('s3://{BUCKET}/{path}', all_varchar = true, filename = true{hive})
            """
        )
        row_count = con.execute(f"SELECT count(*) FROM bronze.{table}").fetchone()[0]
        counts[table] = row_count
        log(f"bronze.{table}: {row_count:,} rows loaded")
        if row_count == 0:
            raise RuntimeError(f"bronze.{table} is empty: nothing matched s3://{BUCKET}/{path}")
    return counts


def run_dbt() -> tuple[int, dict[str, int]]:
    """Execute dbt build against local DuckDB. Tests each model before building dependents."""
    log(f"running dbt build in {DBT_DIR}...")
    cmd = [
        "dbt", "build", "--no-use-colors",
        "--project-dir", DBT_DIR, "--profiles-dir", DBT_DIR,
        "--target-path", "/tmp/dbt_target", "--log-path", "/tmp/dbt_logs",
    ]
    env = {
        **os.environ,
        "DUCKDB_PATH": DB_PATH,
        "DUCKDB_THREADS": str(THREADS),
        "DUCKDB_MEMORY_LIMIT": MEMORY_LIMIT,
    }
    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    output = []
    for line in proc.stdout:
        print(line, end="", flush=True)
        output.append(line)
    code = proc.wait()

    summary = {"pass": 0, "warn": 0, "error": 0, "skip": 0}
    match = re.search(r"Done\. PASS=(\d+) WARN=(\d+) ERROR=(\d+) SKIP=(\d+)", "".join(output))
    if match:
        summary = dict(zip(("pass", "warn", "error", "skip"), map(int, match.groups())))
    return code, summary


def publish_gold(run_id: str) -> dict[str, int]:
    """Connect to Cloud SQL PostgreSQL and publish ONLY gold.* tables atomically."""
    log("connecting to PostgreSQL (Cloud SQL) to publish gold.*...")
    con = duckdb.connect(DB_PATH)
    con.execute("INSTALL postgres; LOAD postgres;")
    con.execute(f"ATTACH '{_pg_dsn()}' AS pg (TYPE postgres)")

    # Purge residual bronze/silver tables from Cloud SQL to keep disk usage at absolute minimum
    log("purging any residual bronze and silver schemas from Cloud SQL...")
    _pg(con, "DROP SCHEMA IF EXISTS bronze CASCADE; DROP SCHEMA IF EXISTS silver CASCADE;")

    schema = PUBLISH_SCHEMA
    suffix = run_id[:8]
    _pg(con, f"CREATE SCHEMA IF NOT EXISTS {schema}")

    counts: dict[str, int] = {}
    for table, spec in GOLD.items():
        log(f"publishing gold.{table} to PostgreSQL...")
        _pg(con, f"DROP TABLE IF EXISTS {schema}.{table}__new; DROP TABLE IF EXISTS {schema}.{table}__old")
        con.execute(f"CREATE TABLE pg.{schema}.{table}__new AS SELECT * FROM gold.{table}")

        # Index creation
        statements = [
            f"CREATE UNIQUE INDEX ix_{table}_key_{suffix} ON {schema}.{table}__new ({', '.join(spec['key'])})"
        ]
        for n, columns in enumerate(spec["indexes"]):
            statements.append(f"CREATE INDEX ix_{table}_{n}_{suffix} ON {schema}.{table}__new ({', '.join(columns)})")
        _pg(con, "; ".join(statements))

        expected = con.execute(f"SELECT count(*) FROM gold.{table}").fetchone()[0]
        copied = con.execute(f"SELECT count(*) FROM pg.{schema}.{table}__new").fetchone()[0]
        if copied != expected:
            raise RuntimeError(f"{schema}.{table}__new has {copied} rows, expected {expected}; swap aborted")
        counts[table] = copied
        log(f"{schema}.{table}__new verified: {copied:,} rows")

    # Atomic swap for all gold tables in a single transaction
    swap = []
    for table in GOLD:
        swap += [
            f"ALTER TABLE IF EXISTS {schema}.{table} RENAME TO {table}__old",
            f"ALTER TABLE {schema}.{table}__new RENAME TO {table}",
            f"DROP TABLE IF EXISTS {schema}.{table}__old",
        ]
    _pg(con, "; ".join(swap))
    log(f"successfully published and swapped {len(GOLD)} tables in schema {schema}")
    con.close()
    return counts


def record_run(run_id: str, started: dt.datetime, status: str, detail: dict) -> None:
    """Record execution status and metrics in ops.etl_runs."""
    try:
        con = duckdb.connect()
        con.execute("INSTALL postgres; LOAD postgres;")
        con.execute(f"ATTACH '{_pg_dsn()}' AS pg (TYPE postgres)")
        _pg(
            con,
            "CREATE SCHEMA IF NOT EXISTS ops; "
            "CREATE TABLE IF NOT EXISTS ops.etl_runs (run_id text PRIMARY KEY, started_at timestamptz, "
            "finished_at timestamptz, status text, detail text)",
        )
        con.execute(
            "INSERT INTO pg.ops.etl_runs VALUES (?, ?, ?, ?, ?)",
            [run_id, started, dt.datetime.now(dt.timezone.utc), status, json.dumps(detail)],
        )
        con.close()
    except Exception as exc:
        log(f"warning: could not record run in ops.etl_runs: {exc}")


def main() -> int:
    run_id = uuid.uuid4().hex
    started = dt.datetime.now(dt.timezone.utc)
    log(f"starting ultra-lightweight ETL pipeline (run_id: {run_id[:8]})")
    detail: dict = {"publish_schema": PUBLISH_SCHEMA}
    status = "failed"

    try:
        # 1. Clean previous local database file
        Path(DB_PATH).unlink(missing_ok=True)
        con = duckdb.connect(DB_PATH)

        # 2. Extract & Load to local DuckDB (Bronze)
        detail["bronze_rows"] = extract_load_bronze(con)
        con.close()  # Close connection before dbt opens it (single writer)

        # 3. Transform & Test with dbt-duckdb (Silver, Gold & 121 tests)
        code, detail["dbt"] = run_dbt()
        if code != 0:
            raise RuntimeError(f"dbt build failed with summary: {detail['dbt']}. Nothing was published.")

        # 4. Publish only gold.* to Cloud SQL PostgreSQL
        detail["published_rows"] = publish_gold(run_id)
        status = "success"
    except Exception as exc:
        detail["error"] = _scrub(f"{type(exc).__name__}: {exc}")[:800]
        log(f"FAILED: {detail['error']}")
    finally:
        record_run(run_id, started, status, detail)

    log(f"pipeline finished with status: {status}")
    return 0 if status == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
