# ETL job image for the GCP hybrid ultra-lightweight stack.
# DuckDB reads S3 -> builds silver/gold & tests with dbt-duckdb in RAM -> publishes ONLY gold to Cloud SQL.
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    git \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    "duckdb>=1.1.0" \
    "dbt-duckdb>=1.8.0" \
    psycopg2-binary

COPY data/dbt/ /app/dbt/
COPY infra/gcp/etl/run_pipeline.py /app/run_pipeline.py

CMD ["python", "run_pipeline.py"]
