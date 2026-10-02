# ETL job image (Cloud Run Job): runs every pipeline stage in order, in one process.
# The same stages (data/pipeline, package latam_pipeline) run as separate tasks in Airflow
# (infra/airflow-gcp); this job is the single-container way to run them, and the fallback.
# Build context is the repository root:  docker build . -f infra/gcp/etl/Dockerfile
FROM python:3.12-slim

WORKDIR /app

# Same versions as the Airflow image (see spec/AIRFLOW_GCP.md).
RUN pip install --no-cache-dir "dbt-duckdb==1.11.0" "duckdb==1.5.6"

COPY data/pipeline /app/pipeline
RUN pip install --no-cache-dir /app/pipeline

COPY data/dbt/ /app/dbt/

CMD ["python", "-m", "latam_pipeline", "all"]
