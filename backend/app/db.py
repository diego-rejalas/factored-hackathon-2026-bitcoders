"""Postgres access for the tool layer. Reads gold.* (and ops.etl_runs) only.

The service connects as a read-only role (see README), so even a bug here cannot
change data. Connection settings come from the environment set in
.railway/railway.ts, never hardcoded.
"""
import os

import psycopg


def connect() -> psycopg.Connection:
    return psycopg.connect(
        host=os.environ["DB_HOST"],
        port=os.environ.get("DB_PORT", "5432"),
        dbname=os.environ.get("DB_NAME", "data"),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        connect_timeout=5,
        # A runaway query must not hold the database: cap it on the server side.
        options="-c statement_timeout=15000 -c default_transaction_read_only=on",
    )
