"""LATAM Bank pipeline: S3 -> Postgres bronze (DuckDB) -> dbt (silver, gold, tests).

  bootstrap -> extract_load x 13 (DuckDB, S3 to bronze, in parallel) -> dbt_build -> record_run

DuckDB reads the CSVs from S3 and writes them into Postgres in one statement per
table (data/dags/lib/extract_load.py). dbt runs as its own service and is called
over HTTP only after every table loaded, so it never transforms a half-loaded
bronze. `dbt build` tests each model before building what depends on it: if a
silver test fails, gold is not rebuilt and keeps the last valid data.
"""
import os
import re
from datetime import datetime, timedelta

import requests
from airflow.exceptions import AirflowException
from airflow.sdk import DAG, get_current_context, task

from lib.extract_load import ALL_TABLES, bootstrap, extract_load, record_run

with DAG(
    dag_id="latam_bank_pipeline",
    description="S3 -> Postgres bronze (DuckDB) -> dbt silver/gold",
    schedule=None,  # static snapshot: triggered on demand, no freshness to keep
    start_date=datetime(2026, 1, 1),
    catchup=False,
    # Six tables at a time keeps memory bounded (each DuckDB session is capped).
    max_active_tasks=6,
    default_args={"retries": 2, "retry_delay": timedelta(seconds=30)},
    tags=["etl", "duckdb", "dbt"],
):

    @task(task_id="bootstrap")
    def bootstrap_task() -> dict:
        return bootstrap()

    bootstrap_done = bootstrap_task()

    loads = []
    for table in ALL_TABLES:

        @task(task_id=f"extract_load_{table}")
        def _extract_load(table_name: str = table) -> dict:
            return extract_load(table_name)

        load = _extract_load()
        bootstrap_done >> load
        loads.append(load)

    @task(task_id="dbt_build", retries=0)
    def dbt_build(_loaded) -> dict:
        resp = requests.post(f"http://{os.environ['DBT_SERVICE_URL']}/run", timeout=1800)
        resp.raise_for_status()
        result = resp.json()
        counts = {"pass": 0, "warn": 0, "error": 0, "skip": 0}
        match = re.search(r"Done\. PASS=(\d+) WARN=(\d+) ERROR=(\d+) SKIP=(\d+)", result.get("stdout", ""))
        if match:
            counts = dict(zip(counts, map(int, match.groups())))
        if not result.get("ok"):
            raise AirflowException(f"dbt build failed {counts}; gold keeps its last valid data. Output tail: {result.get('stdout', '')[-1500:]}")
        return counts

    @task(task_id="record_run")
    def record(rows, dbt_counts) -> None:
        context = get_current_context()
        record_run(
            run_id=context["run_id"],
            started=context["dag_run"].start_date,
            status="success",
            detail={"bronze_rows": {r["table"]: r["rows"] for r in rows}, "dbt": dbt_counts},
        )

    built = dbt_build(loads)
    record(loads, built)
