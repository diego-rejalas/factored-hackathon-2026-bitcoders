"""LATAM Bank pipeline on GCP, one Airflow task per stage.

  start -> extract_bronze -> export_bronze -> dbt_build -> export_silver -> publish_gold -> record_run

The stages are the functions of data/pipeline (package latam_pipeline), the same ones the Cloud Run job
runs. They share one DuckDB file on the VM's data disk, and DuckDB allows a single writer per file, so
the tasks run in sequence. Splitting them gives each stage its own log, its own retries and a visible
place in the UI; a failed dbt build stops the run before anything reaches the serving database.

`record_run` always runs, and writes the outcome of the run to ops.etl_runs.
"""
import os
from datetime import datetime, timedelta

from airflow.exceptions import AirflowFailException
from airflow.sdk import DAG, TriggerRule, get_current_context, task

from latam_pipeline import stages
from latam_pipeline.config import Settings

with DAG(
    dag_id="latam_bank_gcp",
    description="S3 -> DuckDB bronze -> dbt silver/gold -> Parquet lakehouse -> Postgres gold",
    schedule=None,  # static snapshot: triggered on demand
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,  # one run at a time: the DuckDB file has a single writer
    default_args={"retries": 1, "retry_delay": timedelta(seconds=60)},
    tags=["etl", "duckdb", "dbt", "gcp"],
):

    @task
    def start() -> str:
        """Fix the run id; reject a run on a data disk that is nearly full."""
        import shutil

        settings = Settings.from_env()
        from pathlib import Path

        Path(settings.work_dir).mkdir(parents=True, exist_ok=True)
        free_gb = shutil.disk_usage(settings.work_dir).free / 1e9
        stages.log(f"data disk free: {free_gb:.0f} GB")
        needed = float(os.environ.get("PIPELINE_MIN_FREE_GB", "20"))
        if free_gb < needed:
            raise RuntimeError(f"only {free_gb:.0f} GB free on the data disk; the pipeline needs about {needed:.0f} GB")
        return get_current_context()["run_id"]

    @task
    def extract_bronze(pipeline_run_id: str) -> dict:
        return stages.extract_bronze(Settings.from_env())

    @task
    def export_bronze(rows: dict) -> dict:
        return stages.export_bronze(Settings.from_env())

    @task(retries=0)
    def dbt_build(_exported: dict) -> dict:
        # No retry: a failing test is a data problem, and running it again changes nothing.
        return stages.dbt_build(Settings.from_env())

    @task
    def export_silver(_dbt: dict) -> dict:
        return stages.export_silver(Settings.from_env())

    @task
    def publish_gold(pipeline_run_id: str, _exported: dict) -> dict:
        return stages.publish_gold(Settings.from_env(), pipeline_run_id)

    @task(trigger_rule=TriggerRule.ALL_DONE, retries=0)
    def record_run(pipeline_run_id: str, rows=None, dbt=None, published=None) -> None:
        """Runs whether the pipeline succeeded or not, so ops.etl_runs also shows the failures.

        A task cannot query Airflow's metadata database (Airflow 3), so success is read from what
        publish_gold returned: if it returned nothing, an upstream task failed. Which one is in the UI.
        The task then fails on purpose, so the run is shown as failed (see the end of this function).
        """
        context = get_current_context()
        # If the very first task failed there is no pipeline run id: fall back to Airflow's own.
        pipeline_run_id = pipeline_run_id or context["run_id"]
        status = "success" if published else "failed"
        detail = {"airflow_run_id": pipeline_run_id, "bronze_rows": rows, "dbt": dbt, "published_rows": published}
        if status == "failed":
            detail["note"] = "an upstream task failed; see the task logs in the Airflow UI"
        stages.record_run(pipeline_run_id, context["dag_run"].start_date, status, detail)
        # This task always runs and is the last one, so if it succeeded the whole run would show as
        # successful in the UI even after a failure upstream. Fail it once the failure is on record.
        if status == "failed":
            raise AirflowFailException("pipeline failed; the outcome is recorded in ops.etl_runs")

    started = start()
    rows = extract_bronze(started)
    exported_bronze = export_bronze(rows)
    dbt_result = dbt_build(exported_bronze)
    exported_silver = export_silver(dbt_result)
    published = publish_gold(started, exported_silver)
    record_run(started, rows, dbt_result, published)
