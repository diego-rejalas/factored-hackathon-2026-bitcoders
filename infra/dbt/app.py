"""Thin HTTP wrapper around dbt so it can run as its own Railway service.

Airflow's ingestion DAG (data/dags/) calls POST /run after loading raw.*,
so dbt only runs once ingestion has actually finished — a cron on this
service alone couldn't guarantee that ordering.
"""
import subprocess

from fastapi import FastAPI

app = FastAPI(title="dbt runner")

DBT_PROJECT_DIR = "/app/dbt"
DBT_PROFILES_DIR = "/app/dbt"


def _run_dbt(*args: str) -> dict:
    result = subprocess.run(
        ["dbt", *args, "--project-dir", DBT_PROJECT_DIR, "--profiles-dir", DBT_PROFILES_DIR],
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
def run() -> dict:
    """raw.* -> clean.*, then test. Returns non-2xx-worthy info in the body
    (exit_code) rather than raising, so the caller (Airflow) can inspect
    stdout/stderr regardless of success or failure."""
    run_result = _run_dbt("run")
    if run_result["exit_code"] != 0:
        return {"ok": False, "step": "run", **run_result}

    test_result = _run_dbt("test")
    return {"ok": test_result["exit_code"] == 0, "step": "test", "run": run_result, "test": test_result}
