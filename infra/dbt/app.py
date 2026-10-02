"""Thin HTTP wrapper around dbt so it can run as its own Railway service.

Airflow's ingestion DAG (data/dags/) calls POST /run after loading bronze.*,
so dbt only runs once ingestion has actually finished — a cron on this
service alone couldn't guarantee that ordering.
"""
import subprocess
import threading

from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI(title="dbt runner")

DBT_PROJECT_DIR = "/app/dbt"
DBT_PROFILES_DIR = "/app/dbt"

# One dbt invocation at a time: two concurrent builds would rebuild the same
# tables and race on the rename swap. A second request is refused, not queued.
_run_lock = threading.Lock()


def _run_dbt(*args: str) -> dict:
    result = subprocess.run(
        # The default profile target is DuckDB (used by the GCP ETL job); this service builds on Postgres.
        ["dbt", *args, "--project-dir", DBT_PROJECT_DIR, "--profiles-dir", DBT_PROFILES_DIR, "--target", "postgres"],
        capture_output=True,
        text=True,
    )
    return {
        "command": ["dbt", *args],
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/run")
def run():
    """bronze.* -> silver.* -> gold.*, testing each model as it is built.

    `dbt build` runs a model and then its tests before anything downstream
    starts, so a failing silver test stops the gold tables that depend on it
    from being rebuilt with bad data (the old `dbt run` + `dbt test` published
    first and tested after). Returns the outcome in the body rather than
    raising, so the caller (Airflow) can read stdout/stderr either way.
    """
    if not _run_lock.acquire(blocking=False):
        return JSONResponse(status_code=409, content={"ok": False, "error": "a dbt build is already running"})
    try:
        build = _run_dbt("build")
        return {"ok": build["exit_code"] == 0, "step": "build", **build}
    finally:
        _run_lock.release()
