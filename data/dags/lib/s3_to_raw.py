"""S3 -> data.bronze.* loader. Idempotent: safe to re-run a partition or the whole
table without duplicating rows (ON CONFLICT DO NOTHING on the table's natural
PK — see spec/ARCHITECTURE.md, "Escalabilidad").

Each source file is a snapshot, not a delta: a re-run of the same key inserts
nothing new (rows_inserted == 0), it does not apply corrections to an existing
row. rows_read (parsed from the CSV) and rows_inserted (actually new in
Postgres) are reported separately — collapsing them into one counter hid
which rows were skipped as duplicates vs. genuinely new.

Bucket/credentials come from env vars set on the Airflow service in
.railway/railway.ts, never hardcoded here.
"""
import io
import logging
import os
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

import boto3
import polars as pl
import psycopg2
from psycopg2 import sql

from lib.raw_tables import TableSpec

logger = logging.getLogger(__name__)

BUCKET = os.environ.get("LATAM_BANK_S3_BUCKET", "factored-datathon-2026-s3-157725502942-us-east-2-an")


def _s3_client():
    return boto3.client(
        "s3",
        region_name=os.environ.get("AWS_REGION", "us-east-2"),
        aws_access_key_id=os.environ["LATAM_BANK_AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["LATAM_BANK_AWS_SECRET_ACCESS_KEY"],
    )


TARGET_DATABASE = os.environ.get("PG_DATABASE", "data")
ADMIN_DATABASE = os.environ.get("PG_ADMIN_DATABASE", TARGET_DATABASE)


def _pg_connect(database: str = TARGET_DATABASE):
    return psycopg2.connect(
        host=os.environ["PG_HOST"],
        port=os.environ.get("PG_PORT", "5432"),
        user=os.environ["PG_USER"],
        password=os.environ["PG_PASSWORD"],
        dbname=database,
    )


def bootstrap_data_platform() -> dict:
    """Create the application database and its medallion schemas if absent.

    Railway provisions a PostgreSQL server with its own initial database. The
    ingestion service uses that connection only to create the application
    database named by PG_DATABASE, then all pipeline work happens in it.
    """
    admin_conn = _pg_connect(ADMIN_DATABASE)
    try:
        admin_conn.autocommit = True
        with admin_conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (TARGET_DATABASE,))
            if cur.fetchone() is None:
                cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(TARGET_DATABASE)))
                logger.info("created database %s", TARGET_DATABASE)
    finally:
        admin_conn.close()

    target_conn = _pg_connect()
    try:
        with target_conn.cursor() as cur:
            for schema in ("bronze", "silver", "gold"):
                cur.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema)))
        target_conn.commit()
    finally:
        target_conn.close()

    return {"database": TARGET_DATABASE, "schemas": ["bronze", "silver", "gold"]}


def _list_keys(s3, spec: TableSpec) -> list[str]:
    if not spec.partitioned:
        return [f"data/{spec.name}.csv"]

    keys: list[str] = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=BUCKET, Prefix=f"data/{spec.name}/"):
        for obj in page.get("Contents", []):
            if obj["Key"].endswith(".csv"):
                keys.append(obj["Key"])
    return keys


def _ensure_table(conn, spec: TableSpec) -> None:
    pk_sql = ", ".join(f'"{c}"' for c in spec.pk_columns)
    cols_sql = ",\n            ".join(f'"{c}" TEXT' for c in spec.columns)
    with conn.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS bronze")
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS bronze."{spec.name}" (
                {cols_sql},
                PRIMARY KEY ({pk_sql})
            )
            """
        )
    conn.commit()


def _read_csv(body: bytes, spec: TableSpec) -> pl.DataFrame:
    """Parse one CSV file, TEXT-typed and column-aligned to spec.columns.

    Reads with infer_schema_length=0 so every column stays Utf8 (bronze is
    all-text by design — real casts happen once, in dbt staging). Missing
    values become "" (not NULL): dbt's stg_*.sql owns the "" -> NULL cast, so
    bronze must hold literal empty strings to match that contract.
    """
    # utf-8-sig strips a leading BOM that polars' own decoder doesn't expect.
    text = body.decode("utf-8-sig")
    df = pl.read_csv(io.BytesIO(text.encode("utf-8")), infer_schema_length=0)
    missing = [c for c in spec.columns if c not in df.columns]
    if missing:
        df = df.with_columns([pl.lit("").alias(c) for c in missing])
    return df.select(spec.columns).fill_null("")


def _load_key(conn, s3, spec: TableSpec, key: str) -> dict:
    body = s3.get_object(Bucket=BUCKET, Key=key)["Body"].read()
    df = _read_csv(body, spec)
    rows_read = df.height
    if rows_read == 0:
        return {"rows_read": 0, "rows_inserted": 0}

    # quote_style="always" so an empty field round-trips through COPY as an
    # actual empty string, not NULL (Postgres COPY CSV treats an unquoted
    # blank as NULL).
    csv_text = df.write_csv(include_header=False, quote_style="always")

    stage = f"stage_{spec.name}_{uuid.uuid4().hex[:12]}"
    cols_sql = ", ".join(f'"{c}"' for c in spec.columns)
    pk_sql = ", ".join(f'"{c}"' for c in spec.pk_columns)
    with conn.cursor() as cur:
        cur.execute(f'CREATE TEMP TABLE "{stage}" (LIKE bronze."{spec.name}") ON COMMIT DROP')
        cur.copy_expert(f'COPY "{stage}" ({cols_sql}) FROM STDIN WITH (FORMAT csv)', io.StringIO(csv_text))
        cur.execute(
            f"""
            INSERT INTO bronze."{spec.name}" ({cols_sql})
            SELECT {cols_sql} FROM "{stage}"
            ON CONFLICT ({pk_sql}) DO NOTHING
            """
        )
        rows_inserted = cur.rowcount
    conn.commit()
    return {"rows_read": rows_read, "rows_inserted": rows_inserted}


# Independent partitions (one file = one day, no cross-file dependency), so
# each worker gets its own S3 client + Postgres connection and a file is
# never shared — psycopg2 connections aren't thread-safe. I/O-bound (S3 GET,
# network round trip to Postgres), so threads help despite the GIL.
_LOAD_WORKERS = int(os.environ.get("S3_LOAD_WORKERS", "8"))


def _load_key_isolated(spec: TableSpec, key: str) -> dict:
    s3 = _s3_client()
    conn = _pg_connect()
    try:
        return _load_key(conn, s3, spec, key)
    finally:
        conn.close()


def load_table(table_name: str) -> dict:
    from lib.raw_tables import ALL_TABLES

    spec = next(t for t in ALL_TABLES if t.name == table_name)
    s3 = _s3_client()
    conn = _pg_connect()
    try:
        _ensure_table(conn, spec)
    finally:
        conn.close()

    keys = _list_keys(s3, spec)
    rows_read = 0
    rows_inserted = 0

    if not spec.partitioned or len(keys) <= 1:
        conn = _pg_connect()
        try:
            for key in keys:
                result = _load_key(conn, s3, spec, key)
                rows_read += result["rows_read"]
                rows_inserted += result["rows_inserted"]
                logger.info("bronze.%s <- %s (%d read, %d inserted)", spec.name, key, result["rows_read"], result["rows_inserted"])
        finally:
            conn.close()
    else:
        with ThreadPoolExecutor(max_workers=_LOAD_WORKERS) as pool:
            futures = {pool.submit(_load_key_isolated, spec, key): key for key in keys}
            for future in as_completed(futures):
                key = futures[future]
                result = future.result()
                rows_read += result["rows_read"]
                rows_inserted += result["rows_inserted"]
                logger.info("bronze.%s <- %s (%d read, %d inserted)", spec.name, key, result["rows_read"], result["rows_inserted"])

    return {
        "table": spec.name,
        "files": len(keys),
        "rows_read": rows_read,
        "rows_inserted": rows_inserted,
        "rows_skipped": rows_read - rows_inserted,
    }
