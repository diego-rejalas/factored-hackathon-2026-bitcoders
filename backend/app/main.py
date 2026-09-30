"""LATAM Bank tool layer (skeleton).

Deterministic endpoints the agent calls as tools; permissions are enforced here,
not in a prompt. This skeleton only proves the wiring (service up, database
reachable, pipeline output visible). There is deliberately nothing that returns
customer data yet: that arrives together with the test-session authentication.
"""
from fastapi import FastAPI, HTTPException

from app import db
from app.schemas import DataMeta, Health, LastRun, TableCount

app = FastAPI(
    title="LATAM Bank tool layer",
    version="0.1.0",
    description="Mock banking tool layer over the gold tables. Skeleton: no customer data yet.",
)

GOLD_TABLES = ["customers", "products", "transactions", "complaints", "call_center_interactions"]


@app.get("/health", response_model=Health)
def health() -> Health:
    return Health(status="ok")


@app.get("/health/db", response_model=Health)
def health_db() -> Health:
    try:
        with db.connect() as conn:
            conn.execute("SELECT 1")
    except Exception as exc:  # noqa: BLE001 - any failure means the database is not usable
        raise HTTPException(status_code=503, detail=f"database unreachable: {type(exc).__name__}") from None
    return Health(status="ok")


@app.get("/meta/data", response_model=DataMeta)
def data_meta() -> DataMeta:
    """Row counts of the gold tables and the last successful pipeline run (aggregates only)."""
    try:
        with db.connect() as conn:
            # Table names come from the constant list above, never from the request.
            gold = [
                TableCount(table=t, rows=conn.execute(f"SELECT count(*) FROM gold.{t}").fetchone()[0])
                for t in GOLD_TABLES
            ]
            row = conn.execute(
                "SELECT run_id, status, started_at, finished_at FROM ops.etl_runs "
                "WHERE status = 'success' ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"database unreachable: {type(exc).__name__}") from None
    last = LastRun(run_id=row[0], status=row[1], started_at=row[2], finished_at=row[3]) if row else None
    return DataMeta(gold=gold, last_successful_run=last)
