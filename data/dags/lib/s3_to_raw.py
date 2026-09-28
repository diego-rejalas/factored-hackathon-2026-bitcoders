"""S3 -> raw.* loader. Idempotent: safe to re-run a partition or the whole
table without duplicating rows (ON CONFLICT DO NOTHING on the table's natural
PK — see spec/ARCHITECTURE.md, "Escalabilidad").

Bucket/credentials come from env vars set on the Airflow service in
.railway/railway.ts, never hardcoded here.
"""
import csv
import io
import logging
import os

import boto3
import psycopg2
import psycopg2.extras

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


def _pg_connect():
    return psycopg2.connect(
        host=os.environ["PG_HOST"],
        port=os.environ.get("PG_PORT", "5432"),
        user=os.environ["PG_USER"],
        password=os.environ["PG_PASSWORD"],
        dbname=os.environ["PG_DATABASE"],
    )


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
    pk = spec.columns[0]
    cols_sql = ",\n            ".join(f'"{c}" TEXT' for c in spec.columns)
    with conn.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS raw")
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS raw."{spec.name}" (
                {cols_sql},
                PRIMARY KEY ("{pk}")
            )
            """
        )
    conn.commit()


def _load_key(conn, s3, spec: TableSpec, key: str) -> int:
    body = s3.get_object(Bucket=BUCKET, Key=key)["Body"].read().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(body))
    rows = [tuple(row.get(c, "") for c in spec.columns) for row in reader]
    if not rows:
        return 0

    cols_sql = ", ".join(f'"{c}"' for c in spec.columns)
    pk = spec.columns[0]
    sql = f'INSERT INTO raw."{spec.name}" ({cols_sql}) VALUES %s ON CONFLICT ("{pk}") DO NOTHING'
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(cur, sql, rows, page_size=1000)
    conn.commit()
    return len(rows)


def load_table(table_name: str) -> dict:
    from lib.raw_tables import ALL_TABLES

    spec = next(t for t in ALL_TABLES if t.name == table_name)
    s3 = _s3_client()
    conn = _pg_connect()
    try:
        _ensure_table(conn, spec)
        keys = _list_keys(s3, spec)
        total = 0
        for key in keys:
            n = _load_key(conn, s3, spec, key)
            total += n
            logger.info("raw.%s <- %s (%d rows)", spec.name, key, n)
        return {"table": spec.name, "files": len(keys), "rows_upserted": total}
    finally:
        conn.close()
