# ETL job image (Cloud Run Job): runs every pipeline stage in order, in one process.
# The same stages (data/pipeline, package latam_pipeline) run as separate tasks in Airflow
# (infra/gcp/airflow); this job is the single-container way to run them, and the fallback.
# Build context is the repository root:  docker build . -f infra/gcp/etl/Dockerfile
FROM python:3.12-slim

WORKDIR /app

# Same versions as the Airflow image (see docs/ARCHITECTURE.md).
RUN pip install --no-cache-dir "dbt-duckdb==1.11.0" "duckdb==1.5.6"

COPY data/pipeline /app/pipeline
RUN pip install --no-cache-dir /app/pipeline

COPY data/dbt/ /app/dbt/

# Not root. Everything the job writes (the DuckDB file, dbt's target and logs, the Parquet staging
# area) goes under /tmp; the DuckDB extensions are fetched now so a run never depends on the network
# for them.
RUN useradd --create-home --uid 10001 etl
USER etl
RUN python -c "import duckdb; c = duckdb.connect(); c.execute('INSTALL httpfs'); c.execute('INSTALL postgres')"

CMD ["python", "-m", "latam_pipeline", "all"]
