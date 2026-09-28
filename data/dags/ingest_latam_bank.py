"""S3 (LATAM Bank dataset) -> data.bronze.* -> dbt (silver.* -> gold.*).

Each table loads independently and in parallel; dbt only runs after all of
them succeed, so it never transforms a half-loaded bronze.*. See
spec/ARCHITECTURE.md (Vertical 1 y 2) for why dbt is a separate HTTP service
instead of a task in this same container.
"""
import os
from datetime import datetime

import requests
from airflow.exceptions import AirflowException
from airflow.sdk import DAG, task

from lib.raw_tables import ALL_TABLES
from lib.s3_to_raw import bootstrap_data_platform, load_table

with DAG(
    dag_id="ingest_latam_bank",
    description="S3 -> data.bronze.* -> dbt (silver.* -> gold.*)",
    schedule=None,  # manual/triggered for now; revisit once a workflow is chosen
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["ingestion", "dbt"],
):

    @task(task_id="bootstrap_data_platform")
    def bootstrap_data_platform_task() -> dict:
        return bootstrap_data_platform()

    bootstrap_task = bootstrap_data_platform_task()
    load_tasks = []
    for spec in ALL_TABLES:

        @task(task_id=f"load_{spec.name}")
        def _load(table_name: str = spec.name) -> dict:
            return load_table(table_name)

        load_task = _load()
        bootstrap_task >> load_task
        load_tasks.append(load_task)

    @task(task_id="run_dbt")
    def run_dbt(*_upstream_results) -> dict:
        url = f"http://{os.environ['DBT_SERVICE_URL']}/run"
        resp = requests.post(url, timeout=900)
        resp.raise_for_status()
        result = resp.json()
        if not result.get("ok"):
            raise AirflowException(f"dbt run/test failed: {result}")
        return result

    run_dbt(load_tasks)
