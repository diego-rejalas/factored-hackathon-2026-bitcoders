"""ETL job: S3 -> DuckDB (bronze) -> dbt build (silver, gold, tests) -> Postgres (gold).

One process that runs to completion. DuckDB reads the organizer's CSVs straight
from S3, dbt (dbt-duckdb) builds and tests silver and gold inside the same
DuckDB file, and only when every test passed are the gold tables published to
Postgres, the serving database the backend reads. A failed run leaves Postgres
on the last valid gold.

Everything is read from the environment (see .railway/railway.ts):
    LATAM_BANK_AWS_ACCESS_KEY_ID / LATAM_BANK_AWS_SECRET_ACCESS_KEY / AWS_REGION
    PG_HOST / PG_PORT / PG_USER / PG_PASSWORD / PG_DATABASE
    PUBLISH_SCHEMA (default "gold"; set it to something else for a dry run)
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
DBT_DIR = os.environ.get("DBT_DIR", str(Path(__file__).resolve().parent / "dbt"))
PUBLISH_SCHEMA = os.environ.get("PUBLISH_SCHEMA", "gold")

# data/<name>.csv
FLAT = ["customers", "products", "branches", "service_agents", "marketing_campaigns", "daily_exchange_rates"]
# data/<name>/year=YYYY/month=MM/day=DD/<name>_YYYYMMDD.csv
PARTITIONED = [
    "transactions", "complaints", "call_center_interactions", "call_transcripts",
    "satisfaction_surveys", "campaign_sends", "digital_events",
]

# Published tables: the first key is unique; each other entry becomes a plain
# index. These are the lookups the backend tool layer runs.
GOLD = {
    "customers": {"key": ["customer_id"], "indexes": []},
    "products": {"key": ["product_id"], "indexes": [["customer_id"]]},
    "transactions": {
        "key": ["transaction_id"],
        "indexes": [["customer_id", "transaction_date"], ["product_id"]],
    },
    "complaints": {"key": ["complaint_id"], "indexes": [["customer_id"]]},
    "call_center_interactions": {"key": ["interaction_id"], "indexes": [["customer_id"]]},
}


def _scrub(text: str) -> str:
    """Error messages from ATTACH or S3 can echo the connection string; never log a secret."""
    for name in ("PG_PASSWORD", "LATAM_BANK_AWS_SECRET_ACCESS_KEY", "LATAM_BANK_AWS_ACCESS_KEY_ID"):
        secret = os.environ.get(name)
        if secret:
            text = text.replace(secret, "***")
    return text


def log(message: str) -> None:
    print(f"[{dt.datetime.now(dt.timezone.utc):%H:%M:%S}] {_scrub(message)}", flush=True)


def _pg_dsn() -> str:
    return (
        f"host={os.environ['PG_HOST']} port={os.environ.get('PG_PORT', '5432')} "
        f"dbname={os.environ['PG_DATABASE']} user={os.environ['PG_USER']} password={os.environ['PG_PASSWORD']}"
    )


def _attach_postgres(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("INSTALL postgres; LOAD postgres;")
    con.execute(f"ATTACH '{_pg_dsn()}' AS pg (TYPE postgres)")


def _pg(con: duckdb.DuckDBPyConnection, sql: str) -> None:
    """Run DDL on Postgres. Several statements in one call run as one transaction."""
    escaped = sql.replace("'", "''")
    con.execute(f"CALL postgres_execute('pg', '{escaped}')")


def extract_load(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    """S3 -> bronze.<table>, every column as text. Returns rows per table."""
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
    con.execute("CREATE SCHEMA IF NOT EXISTS bronze")

    counts: dict[str, int] = {}
    for table in FLAT + PARTITIONED:
        path = f"data/{table}.csv" if table in FLAT else f"data/{table}/*/*/*/*.csv"
        hive = "" if table in FLAT else ", hive_partitioning = true"
        # filename -> _source_key gives every row its S3 object (lineage);
        # all_varchar keeps bronze a faithful copy: casts happen once, in silver.
        con.execute(
            f"""
            CREATE OR REPLACE TABLE bronze.{table} AS
            SELECT * EXCLUDE (filename), filename AS _source_key, current_timestamp AS _ingested_at
            FROM read_csv('s3://{BUCKET}/{path}', all_varchar = true, filename = true{hive})
            """
        )
        counts[table] = con.execute(f"SELECT count(*) FROM bronze.{table}").fetchone()[0]
        log(f"bronze.{table}: {counts[table]:,} rows")
        if counts[table] == 0:
            raise RuntimeError(f"bronze.{table} is empty: nothing matched s3://{BUCKET}/{path}")
    return counts


def run_dbt() -> tuple[int, dict[str, int]]:
    """dbt build = each model is built and then tested before anything downstream."""
    cmd = [
        "dbt", "build", "--no-use-colors",
        "--project-dir", DBT_DIR, "--profiles-dir", DBT_DIR,
        "--target-path", "/tmp/dbt_target", "--log-path", "/tmp/dbt_logs",
    ]
    proc = subprocess.Popen(
        cmd, env={**os.environ, "DUCKDB_PATH": DB_PATH},
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
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


def publish(run_id: str) -> dict[str, int]:
    """Copy gold to Postgres and swap it in for all tables at once.

    Each table is built as <table>__new with its indexes; the swap is a single
    multi-statement call, so readers see either the previous gold or the new one.
    """
    con = duckdb.connect(DB_PATH)
    _attach_postgres(con)
    schema = PUBLISH_SCHEMA
    suffix = run_id[:8]
    _pg(con, f"CREATE SCHEMA IF NOT EXISTS {schema}")

    counts: dict[str, int] = {}
    for table, spec in GOLD.items():
        _pg(con, f"DROP TABLE IF EXISTS {schema}.{table}__new; DROP TABLE IF EXISTS {schema}.{table}__old")
        con.execute(f"CREATE TABLE pg.{schema}.{table}__new AS SELECT * FROM gold.{table}")
        # Index names are unique per schema, so they carry the run id.
        statements = [
            f"CREATE UNIQUE INDEX ix_{table}_key_{suffix} ON {schema}.{table}__new ({', '.join(spec['key'])})"
        ]
        for n, columns in enumerate(spec["indexes"]):
            statements.append(f"CREATE INDEX ix_{table}_{n}_{suffix} ON {schema}.{table}__new ({', '.join(columns)})")
        _pg(con, "; ".join(statements))

        expected = con.execute(f"SELECT count(*) FROM gold.{table}").fetchone()[0]
        copied = con.execute(f"SELECT count(*) FROM pg.{schema}.{table}__new").fetchone()[0]
        if copied != expected:
            raise RuntimeError(f"{schema}.{table}__new has {copied} rows, gold has {expected}; nothing was swapped")
        counts[table] = copied
        log(f"{schema}.{table}__new ready: {copied:,} rows")

    swap = []
    for table in GOLD:
        swap += [
            f"ALTER TABLE IF EXISTS {schema}.{table} RENAME TO {table}__old",
            f"ALTER TABLE {schema}.{table}__new RENAME TO {table}",
            f"DROP TABLE IF EXISTS {schema}.{table}__old",
        ]
    _pg(con, "; ".join(swap))
    log(f"published {len(GOLD)} tables to Postgres schema {schema}")
    con.close()
    return counts


def record_run(run_id: str, started: dt.datetime, status: str, detail: dict) -> None:
    """One row per run in ops.etl_runs: when it ran, whether it passed, and the counts."""
    con = duckdb.connect()
    _attach_postgres(con)
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


def main() -> int:
    run_id = uuid.uuid4().hex
    started = dt.datetime.now(dt.timezone.utc)
    detail: dict = {"publish_schema": PUBLISH_SCHEMA}
    status = "failed"
    try:
        Path(DB_PATH).unlink(missing_ok=True)
        con = duckdb.connect(DB_PATH)
        detail["bronze_rows"] = extract_load(con)
        con.close()  # dbt opens the same file: it is single-writer

        code, detail["dbt"] = run_dbt()
        if code != 0:
            raise RuntimeError(f"dbt build failed {detail['dbt']}: nothing was published, Postgres keeps the last valid gold")

        detail["published_rows"] = publish(run_id)
        status = "success"
    except Exception as exc:  # noqa: BLE001 - the job reports any failure the same way
        detail["error"] = _scrub(f"{type(exc).__name__}: {exc}")[:800]
        log(f"FAILED: {detail['error']}")
    finally:
        try:
            record_run(run_id, started, status, detail)
        except Exception as exc:  # noqa: BLE001 - recording must never hide the real outcome
            log(f"could not record the run in ops.etl_runs: {exc}")

    log(f"run {run_id[:8]} {status}")
    return 0 if status == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
