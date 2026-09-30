"""S3 -> data.bronze.* loader with file-level lineage.

Idempotent and incremental: every source file is recorded in
bronze._ingest_log (table, source_key, etag, row counts, timestamp) in the same
transaction that inserts its rows, so a re-run skips files that are already in
and a crash can never leave a file half-recorded. Every bronze row also carries
_source_key (the S3 object it came from) and _ingested_at.

Each source file is a snapshot, not a delta. Rows are inserted with
ON CONFLICT DO NOTHING on the table's natural PK; a file whose etag changed
after it was loaded is NOT silently merged — the load fails loudly and needs
full_refresh=True (truncate that table and its ledger rows, reload from S3).
rows_read (parsed from the CSV) and rows_inserted (actually new in Postgres)
are reported separately, and after each table the ledger total is reconciled
against the real row count of the table.

Bucket/credentials come from env vars set on the Airflow service in
.railway/railway.ts, never hardcoded here.
"""
import io
import logging
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

import boto3
import polars as pl
import psycopg2
from botocore.config import Config as BotoConfig
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
        # "adaptive" retries transient body-read failures (IncompleteRead /
        # ProtocolError) that "legacy" mode's default retry policy doesn't
        # cover — seen under concurrent GETs on the larger partitioned tables
        # (transactions, digital_events).
        config=BotoConfig(retries={"max_attempts": 6, "mode": "adaptive"}),
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
            # Created here, in the single task that runs before the 13
            # parallel loads, so they never race to create it.
            cur.execute(LEDGER_DDL)
        target_conn.commit()
    finally:
        target_conn.close()

    return {"database": TARGET_DATABASE, "schemas": ["bronze", "silver", "gold"]}


LEDGER_DDL = """
CREATE TABLE IF NOT EXISTS bronze._ingest_log (
    table_name    TEXT        NOT NULL,
    source_key    TEXT        NOT NULL,
    etag          TEXT        NOT NULL,
    size_bytes    BIGINT,
    rows_read     INTEGER     NOT NULL,
    rows_inserted INTEGER     NOT NULL,
    loaded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (table_name, source_key)
)
"""


def _list_objects(s3, spec: TableSpec) -> list[tuple[str, str, int]]:
    """(key, etag, size) for every source file of the table."""
    if not spec.partitioned:
        key = f"data/{spec.name}.csv"
        head = s3.head_object(Bucket=BUCKET, Key=key)
        return [(key, head["ETag"].strip('"'), head["ContentLength"])]

    objects: list[tuple[str, str, int]] = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=BUCKET, Prefix=f"data/{spec.name}/"):
        for obj in page.get("Contents", []):
            if obj["Key"].endswith(".csv"):
                objects.append((obj["Key"], obj["ETag"].strip('"'), obj["Size"]))
    return objects


def _ensure_table(conn, spec: TableSpec) -> None:
    pk_sql = ", ".join(f'"{c}"' for c in spec.pk_columns)
    cols_sql = ",\n            ".join(f'"{c}" TEXT' for c in spec.columns)
    with conn.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS bronze")
        cur.execute(LEDGER_DDL)
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS bronze."{spec.name}" (
                {cols_sql},
                "_source_key"  TEXT,
                "_ingested_at" TIMESTAMPTZ,
                PRIMARY KEY ({pk_sql})
            )
            """
        )
        # Tables created before lineage existed get the columns added in place
        # (nullable, metadata-only, instant even on the 15M-row table).
        cur.execute(
            f'ALTER TABLE bronze."{spec.name}" '
            'ADD COLUMN IF NOT EXISTS "_source_key" TEXT, '
            'ADD COLUMN IF NOT EXISTS "_ingested_at" TIMESTAMPTZ'
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


def _get_object_bytes(s3, key: str, attempts: int = 4) -> bytes:
    # botocore's retry config (see _s3_client) only covers request-level
    # failures — a body read that starts streaming and then drops
    # (IncompleteRead/ProtocolError) happens after the 200 OK, so it isn't
    # retried automatically. Re-issuing get_object from scratch is.
    last_exc = None
    for attempt in range(1, attempts + 1):
        try:
            return s3.get_object(Bucket=BUCKET, Key=key)["Body"].read()
        except Exception as exc:  # noqa: BLE001 - deliberately broad, see above
            last_exc = exc
            logger.warning("s3 get_object retry %d/%d for %s: %s", attempt, attempts, key, exc)
            time.sleep(min(2**attempt, 10))
    raise last_exc


def _load_key(conn, s3, spec: TableSpec, key: str, etag: str, size: int) -> dict:
    """Load one source file and record it in the ledger, atomically."""
    body = _get_object_bytes(s3, key)
    df = _read_csv(body, spec)
    rows_read = df.height
    rows_inserted = 0

    with conn.cursor() as cur:
        if rows_read > 0:
            # quote_style="always" so an empty field round-trips through COPY
            # as an actual empty string, not NULL (Postgres COPY CSV treats an
            # unquoted blank as NULL).
            csv_text = df.write_csv(include_header=False, quote_style="always")

            stage = f"stage_{spec.name}_{uuid.uuid4().hex[:12]}"
            cols_sql = ", ".join(f'"{c}"' for c in spec.columns)
            pk_sql = ", ".join(f'"{c}"' for c in spec.pk_columns)
            cur.execute(f'CREATE TEMP TABLE "{stage}" (LIKE bronze."{spec.name}") ON COMMIT DROP')
            cur.copy_expert(f'COPY "{stage}" ({cols_sql}) FROM STDIN WITH (FORMAT csv)', io.StringIO(csv_text))
            cur.execute(
                f"""
                INSERT INTO bronze."{spec.name}" ({cols_sql}, "_source_key", "_ingested_at")
                SELECT {cols_sql}, %s, now() FROM "{stage}"
                ON CONFLICT ({pk_sql}) DO NOTHING
                """,
                (key,),
            )
            rows_inserted = cur.rowcount

        cur.execute(
            """
            INSERT INTO bronze._ingest_log (table_name, source_key, etag, size_bytes, rows_read, rows_inserted)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (table_name, source_key) DO NOTHING
            """,
            (spec.name, key, etag, size, rows_read, rows_inserted),
        )
    conn.commit()
    return {"rows_read": rows_read, "rows_inserted": rows_inserted}


# Independent partitions (one file = one day, no cross-file dependency), so
# each worker gets its own S3 client + Postgres connection and a file is
# never shared — psycopg2 connections aren't thread-safe. I/O-bound (S3 GET,
# network round trip to Postgres), so threads help despite the GIL.
_LOAD_WORKERS = int(os.environ.get("S3_LOAD_WORKERS", "4"))


def _load_key_isolated(spec: TableSpec, key: str, etag: str, size: int) -> dict:
    s3 = _s3_client()
    conn = _pg_connect()
    try:
        return _load_key(conn, s3, spec, key, etag, size)
    finally:
        conn.close()


def _read_ledger(conn, table_name: str) -> dict[str, str]:
    with conn.cursor() as cur:
        cur.execute("SELECT source_key, etag FROM bronze._ingest_log WHERE table_name = %s", (table_name,))
        return dict(cur.fetchall())


def _full_refresh(conn, spec: TableSpec) -> None:
    with conn.cursor() as cur:
        cur.execute(f'TRUNCATE bronze."{spec.name}"')
        cur.execute("DELETE FROM bronze._ingest_log WHERE table_name = %s", (spec.name,))
    conn.commit()
    logger.warning("full_refresh: truncated bronze.%s and cleared its ledger rows", spec.name)


def _table_has_rows(conn, spec: TableSpec) -> bool:
    with conn.cursor() as cur:
        cur.execute(f'SELECT EXISTS (SELECT 1 FROM bronze."{spec.name}" LIMIT 1)')
        return cur.fetchone()[0]


def _reconcile(conn, spec: TableSpec) -> tuple[int, int]:
    """(rows really in the table, rows the ledger says were inserted)."""
    with conn.cursor() as cur:
        cur.execute(f'SELECT count(*) FROM bronze."{spec.name}"')
        in_table = cur.fetchone()[0]
        cur.execute("SELECT coalesce(sum(rows_inserted), 0) FROM bronze._ingest_log WHERE table_name = %s", (spec.name,))
        in_ledger = int(cur.fetchone()[0])
    return in_table, in_ledger


def load_table(table_name: str, full_refresh: bool = False, spec: TableSpec | None = None) -> dict:
    """Load one table. `spec` overrides the registry lookup (used to exercise the
    loader against a scratch table without touching a real bronze table)."""
    from lib.raw_tables import ALL_TABLES

    spec = spec or next(t for t in ALL_TABLES if t.name == table_name)
    s3 = _s3_client()

    conn = _pg_connect()
    try:
        _ensure_table(conn, spec)
        if full_refresh:
            _full_refresh(conn, spec)
        ledger = _read_ledger(conn, spec.name)
        if not ledger and _table_has_rows(conn, spec):
            raise RuntimeError(
                f"bronze.{spec.name} has rows but no ledger entries: they were loaded before file-level "
                "lineage existed and carry no _source_key. Re-run the DAG with full_refresh=true to rebuild "
                "the table from S3."
            )
    finally:
        conn.close()

    objects = _list_objects(s3, spec)
    pending: list[tuple[str, str, int]] = []
    for key, etag, size in objects:
        known_etag = ledger.get(key)
        if known_etag is None:
            pending.append((key, etag, size))
        elif known_etag != etag:
            raise RuntimeError(
                f"bronze.{spec.name}: {key} changed in S3 after it was loaded "
                f"(etag {known_etag} -> {etag}). Loading it again would silently drop the corrections "
                "(ON CONFLICT DO NOTHING). Re-run with full_refresh=true."
            )
    files_skipped = len(objects) - len(pending)

    rows_read = 0
    rows_inserted = 0
    if pending:
        if not spec.partitioned or len(pending) == 1:
            conn = _pg_connect()
            try:
                for key, etag, size in pending:
                    result = _load_key(conn, s3, spec, key, etag, size)
                    rows_read += result["rows_read"]
                    rows_inserted += result["rows_inserted"]
                    logger.info("bronze.%s <- %s (%d read, %d inserted)", spec.name, key, result["rows_read"], result["rows_inserted"])
            finally:
                conn.close()
        else:
            with ThreadPoolExecutor(max_workers=_LOAD_WORKERS) as pool:
                futures = {pool.submit(_load_key_isolated, spec, key, etag, size): key for key, etag, size in pending}
                for future in as_completed(futures):
                    result = future.result()
                    rows_read += result["rows_read"]
                    rows_inserted += result["rows_inserted"]
                    logger.info("bronze.%s <- %s (%d read, %d inserted)", spec.name, futures[future], result["rows_read"], result["rows_inserted"])

    conn = _pg_connect()
    try:
        in_table, in_ledger = _reconcile(conn, spec)
    finally:
        conn.close()
    if in_table != in_ledger:
        raise RuntimeError(
            f"bronze.{spec.name} reconciliation failed: table has {in_table} rows but the ledger accounts "
            f"for {in_ledger}. Something changed the table outside the loader."
        )

    return {
        "table": spec.name,
        "files_total": len(objects),
        "files_loaded": len(pending),
        "files_skipped": files_skipped,
        "rows_read": rows_read,
        "rows_inserted": rows_inserted,
        "rows_skipped": rows_read - rows_inserted,
        "rows_in_bronze": in_table,
    }
