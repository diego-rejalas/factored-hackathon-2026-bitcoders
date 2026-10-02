"""The pipeline stages. Same behaviour as the single script they were split from.

Order: extract_bronze -> export_bronze -> dbt_build -> export_silver -> publish_gold -> record_run.
Each stage is a plain function: it opens and closes its own DuckDB connection, so Airflow can run
every one as its own task. DuckDB allows a single writer per file, which is why the stages run in
sequence over `Settings.db_path` instead of in parallel.
"""
import datetime as dt
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import duckdb

from .config import ALL_TABLES, FLAT, GOLD, PARTITIONED, SECRET_ENV_NAMES, Settings, short_id, utcnow


# --------------------------------------------------------------------------- helpers


def scrub(text: str) -> str:
    """Never log database passwords or AWS secrets."""
    for name in SECRET_ENV_NAMES:
        secret = os.environ.get(name)
        if secret:
            text = text.replace(secret, "***")
    return text


def log(message: str) -> None:
    print(f"[{utcnow():%H:%M:%S}] [etl] {scrub(message)}", flush=True)


def pg_dsn() -> str:
    return (
        f"host={os.environ['PG_HOST']} port={os.environ.get('PG_PORT', '5432')} "
        f"dbname={os.environ['PG_DATABASE']} user={os.environ['PG_USER']} password={os.environ['PG_PASSWORD']}"
    )


def pg_execute(con: duckdb.DuckDBPyConnection, sql: str) -> None:
    """Run DDL on Postgres through the DuckDB postgres extension."""
    escaped = sql.replace("'", "''")
    con.execute(f"CALL postgres_execute('pg', '{escaped}')")


def _csv_path(settings: Settings, table: str) -> str:
    return f"{settings.source}/data/{table}.csv" if table in FLAT else f"{settings.source}/data/{table}/*/*/*/*.csv"


# --------------------------------------------------------------------------- 1. extract


def extract_bronze(settings: Settings, tables: list | None = None) -> dict[str, int]:
    """CSV files (S3 in production) -> bronze.<table> in the local DuckDB, all text plus lineage columns."""
    from_s3 = settings.source.startswith("s3://")
    if from_s3:
        missing = [
            k for k in ("LATAM_BANK_AWS_ACCESS_KEY_ID", "LATAM_BANK_AWS_SECRET_ACCESS_KEY") if not os.environ.get(k, "").strip()
        ]
        if missing:
            raise RuntimeError(f"Missing S3 credentials: {', '.join(missing)}")

    Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)
    # Each run starts from an empty file: bronze is a full reload, never an accumulation.
    Path(settings.db_path).unlink(missing_ok=True)

    con = duckdb.connect(settings.db_path)
    try:
        con.execute(f"SET threads = {settings.threads}; SET memory_limit = '{settings.memory_limit}';")
        if from_s3:
            con.execute("INSTALL httpfs; LOAD httpfs;")
            con.execute(
                "CREATE OR REPLACE SECRET s3 (TYPE S3, KEY_ID '%s', SECRET '%s', REGION '%s')"
                % (
                    os.environ["LATAM_BANK_AWS_ACCESS_KEY_ID"],
                    os.environ["LATAM_BANK_AWS_SECRET_ACCESS_KEY"],
                    settings.aws_region,
                )
            )
            con.execute("SET http_retries = 6; SET http_retry_wait_ms = 1000;")
        con.execute("CREATE SCHEMA IF NOT EXISTS bronze;")

        counts: dict[str, int] = {}
        for table in tables or ALL_TABLES:
            path = _csv_path(settings, table)
            hive = "" if table in FLAT else ", hive_partitioning = true"
            log(f"reading {path} -> bronze.{table}...")
            con.execute(
                f"""
                CREATE OR REPLACE TABLE bronze.{table} AS
                SELECT * EXCLUDE (filename), filename AS _source_key, current_timestamp AS _ingested_at
                FROM read_csv('{path}', all_varchar = true, filename = true{hive})
                """
            )
            row_count = con.execute(f"SELECT count(*) FROM bronze.{table}").fetchone()[0]
            counts[table] = row_count
            log(f"bronze.{table}: {row_count:,} rows loaded")
            if row_count == 0:
                raise RuntimeError(f"bronze.{table} is empty: nothing matched {path}")
        return counts
    finally:
        con.close()


# --------------------------------------------------------------------------- lakehouse (Parquet)


def upload_dir_to_gcs(local_dir: Path, gcs_uri: str) -> int:
    """Upload every file under local_dir to gcs_uri with the native Cloud Storage SDK."""
    from google.cloud import storage
    from google.cloud.storage import transfer_manager

    if not local_dir.exists():
        return 0

    clean = gcs_uri.replace("gs://", "").strip("/")
    parts = clean.split("/", 1)
    bucket_name = parts[0]
    prefix = parts[1].strip("/") + "/" if len(parts) > 1 and parts[1].strip() else ""

    bucket = storage.Client().bucket(bucket_name)
    filenames = [p.relative_to(local_dir).as_posix() for p in local_dir.rglob("*") if p.is_file()]
    if not filenames:
        log(f"no files found in {local_dir} to upload")
        return 0

    log(f"uploading {len(filenames)} files from {local_dir} to gs://{bucket_name}/{prefix} in parallel...")
    transfer_manager.upload_many_from_filenames(
        bucket,
        filenames,
        source_directory=str(local_dir),
        blob_name_prefix=prefix,
        max_workers=8,
        raise_exception=True,
    )
    log(f"successfully uploaded {len(filenames)} files to gs://{bucket_name}/{prefix}")
    # Free the local disk once the copy is in the bucket.
    shutil.rmtree(local_dir, ignore_errors=True)
    return len(filenames)


def _export_layer(settings: Settings, layer: str) -> dict[str, int]:
    """Write one layer (bronze or silver) as Parquet ZSTD to the lakehouse (gs:// or a local path)."""
    if not settings.lake_uri:
        log(f"lake storage URI not set; skipping {layer} Parquet export")
        return {}

    is_gcs = settings.lake_uri.startswith("gs://")
    local_base = Path(settings.work_dir) / "lakehouse" / layer if is_gcs else Path(settings.lake_uri) / layer
    local_base.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(settings.db_path, read_only=True)
    try:
        con.execute(f"SET threads = {settings.threads}; SET memory_limit = '{settings.memory_limit}';")
        counts: dict[str, int] = {}
        log(f"exporting {layer} layer in Parquet ZSTD to {local_base}...")
        for table in ALL_TABLES:
            relation = f"bronze.{table}" if layer == "bronze" else f"silver.stg_{table}"
            target = local_base / table
            target.mkdir(parents=True, exist_ok=True)
            if table in FLAT:
                file_path = (target / f"{table}.parquet").as_posix()
                con.execute(f"COPY {relation} TO '{file_path}' (FORMAT PARQUET, COMPRESSION ZSTD)")
            elif layer == "bronze":
                # bronze keeps year, month and day from the source's hive partitions
                con.execute(
                    f"""
                    COPY (SELECT * FROM {relation})
                    TO '{target.as_posix()}'
                    (FORMAT PARQUET, COMPRESSION ZSTD, PARTITION_BY (year, month, day), OVERWRITE_OR_IGNORE true)
                    """
                )
            else:
                con.execute(
                    f"""
                    COPY (
                        SELECT *,
                               coalesce(strftime(process_date, '%Y'), 'unknown') AS year,
                               coalesce(strftime(process_date, '%m'), 'unknown') AS month,
                               coalesce(strftime(process_date, '%d'), 'unknown') AS day
                        FROM {relation}
                    )
                    TO '{target.as_posix()}'
                    (FORMAT PARQUET, COMPRESSION ZSTD, PARTITION_BY (year, month, day), OVERWRITE_OR_IGNORE true)
                    """
                )
            counts[table] = con.execute(f"SELECT count(*) FROM {relation}").fetchone()[0]
            log(f"lakehouse {layer}.{table}: {counts[table]:,} rows exported")
    finally:
        con.close()

    if is_gcs:
        upload_dir_to_gcs(local_base, f"{settings.lake_uri}/{layer}")
    return counts


def export_bronze(settings: Settings) -> dict[str, int]:
    return _export_layer(settings, "bronze")


def export_silver(settings: Settings) -> dict[str, int]:
    return _export_layer(settings, "silver")


# --------------------------------------------------------------------------- 2. transform


DBT_SUMMARY = re.compile(r"Done\. PASS=(\d+) WARN=(\d+) ERROR=(\d+) SKIP=(\d+)")


def parse_dbt_summary(output: str) -> dict[str, int]:
    match = DBT_SUMMARY.search(output)
    if not match:
        return {"pass": 0, "warn": 0, "error": 0, "skip": 0}
    return dict(zip(("pass", "warn", "error", "skip"), map(int, match.groups())))


def dbt_build(settings: Settings) -> dict[str, int]:
    """dbt build on the local DuckDB: every model is tested before its dependents are built.

    Raises when dbt fails, so nothing downstream (silver export, publish) runs on bad data.
    """
    log(f"running dbt build in {settings.dbt_dir}...")
    work = Path(settings.work_dir)
    cmd = [
        settings.dbt_bin, "build", "--no-use-colors",
        "--project-dir", settings.dbt_dir, "--profiles-dir", settings.dbt_dir,
        "--target-path", str(work / "dbt_target"), "--log-path", str(work / "dbt_logs"),
    ]
    if settings.dbt_target:
        cmd += ["--target", settings.dbt_target]
    env = {
        **os.environ,
        "DUCKDB_PATH": settings.db_path,
        "DUCKDB_THREADS": str(settings.threads),
        "DUCKDB_MEMORY_LIMIT": settings.memory_limit,
    }
    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    output = []
    for line in proc.stdout:
        print(line, end="", flush=True)
        output.append(line)
    code = proc.wait()
    summary = parse_dbt_summary("".join(output))
    if code != 0:
        raise RuntimeError(f"dbt build failed with summary: {summary}. Nothing was published.")
    return summary


# --------------------------------------------------------------------------- 3. publish


def publish_gold(settings: Settings, run_id: str) -> dict[str, int]:
    """Publish only gold.* to Postgres: build <table>__new, verify the count, swap all tables at once."""
    log("connecting to PostgreSQL to publish gold.*...")
    # Not read_only: DuckDB passes read-only mode on to the attached Postgres, which then refuses DDL.
    con = duckdb.connect(settings.db_path)
    try:
        con.execute("INSTALL postgres; LOAD postgres;")
        con.execute(f"ATTACH '{pg_dsn()}' AS pg (TYPE postgres)")

        # The pipeline keeps only gold in the serving database: drop any bronze/silver left by an earlier design.
        log("purging any residual bronze and silver schemas from the serving database...")
        pg_execute(con, "DROP SCHEMA IF EXISTS bronze CASCADE; DROP SCHEMA IF EXISTS silver CASCADE;")

        schema = settings.publish_schema
        suffix = short_id(run_id)
        pg_execute(con, f"CREATE SCHEMA IF NOT EXISTS {schema}")

        counts: dict[str, int] = {}
        for table, spec in GOLD.items():
            log(f"publishing {schema}.{table} to PostgreSQL...")
            pg_execute(con, f"DROP TABLE IF EXISTS {schema}.{table}__new; DROP TABLE IF EXISTS {schema}.{table}__old")
            con.execute(f"CREATE TABLE pg.{schema}.{table}__new AS SELECT * FROM gold.{table}")

            statements = [
                f"CREATE UNIQUE INDEX ix_{table}_key_{suffix} ON {schema}.{table}__new ({', '.join(spec['key'])})"
            ]
            for n, columns in enumerate(spec["indexes"]):
                statements.append(f"CREATE INDEX ix_{table}_{n}_{suffix} ON {schema}.{table}__new ({', '.join(columns)})")
            pg_execute(con, "; ".join(statements))

            expected = con.execute(f"SELECT count(*) FROM gold.{table}").fetchone()[0]
            copied = con.execute(f"SELECT count(*) FROM pg.{schema}.{table}__new").fetchone()[0]
            if copied != expected:
                raise RuntimeError(f"{schema}.{table}__new has {copied} rows, expected {expected}; swap aborted")
            counts[table] = copied
            log(f"{schema}.{table}__new verified: {copied:,} rows")

        # One swap for every table, so readers never see a mix of old and new tables.
        swap = []
        for table in GOLD:
            swap += [
                f"ALTER TABLE IF EXISTS {schema}.{table} RENAME TO {table}__old",
                f"ALTER TABLE {schema}.{table}__new RENAME TO {table}",
                f"DROP TABLE IF EXISTS {schema}.{table}__old",
            ]
        pg_execute(con, "; ".join(swap))

        for role in settings.gold_reader_roles:
            _grant_read(con, schema, role)

        log(f"successfully published and swapped {len(GOLD)} tables in schema {schema}")
        return counts
    finally:
        con.close()


def _grant_read(con: duckdb.DuckDBPyConnection, schema: str, role: str) -> None:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", role):
        raise ValueError(f"invalid Postgres role name: {role!r}")
    pg_execute(
        con,
        f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN "
        f"GRANT USAGE ON SCHEMA {schema} TO {role}; GRANT SELECT ON ALL TABLES IN SCHEMA {schema} TO {role}; "
        f"END IF; END $$;",
    )


# --------------------------------------------------------------------------- 4. record


def record_run(run_id: str, started: dt.datetime, status: str, detail: dict) -> None:
    """Write the run to ops.etl_runs. Failing to record must never fail the pipeline."""
    try:
        con = duckdb.connect()
        con.execute("INSTALL postgres; LOAD postgres;")
        con.execute(f"ATTACH '{pg_dsn()}' AS pg (TYPE postgres)")
        pg_execute(
            con,
            "CREATE SCHEMA IF NOT EXISTS ops; "
            "CREATE TABLE IF NOT EXISTS ops.etl_runs (run_id text PRIMARY KEY, started_at timestamptz, "
            "finished_at timestamptz, status text, detail text)",
        )
        # Re-running the same run id (an Airflow retry or a cleared task) replaces its row.
        con.execute("DELETE FROM pg.ops.etl_runs WHERE run_id = ?", [run_id])
        con.execute(
            "INSERT INTO pg.ops.etl_runs VALUES (?, ?, ?, ?, ?)",
            [run_id, started, utcnow(), status, json.dumps(detail, default=str)],
        )
        con.close()
    except Exception as exc:  # noqa: BLE001
        log(f"warning: could not record run in ops.etl_runs: {exc}")
