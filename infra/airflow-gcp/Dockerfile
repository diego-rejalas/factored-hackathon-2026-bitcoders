# Airflow for the GCP deployment: runs the pipeline stages (data/pipeline) as separate tasks.
# Build context is the repository root:  docker build . -f infra/airflow-gcp/Dockerfile
ARG AIRFLOW_VERSION=3.3.0
ARG PYTHON_VERSION=3.12

FROM apache/airflow:${AIRFLOW_VERSION}-python${PYTHON_VERSION}

ARG AIRFLOW_VERSION
ARG PYTHON_VERSION
# Same versions that ran the pipeline in production (see spec/AIRFLOW_GCP.md).
ARG DUCKDB_VERSION=1.5.6
ARG DBT_DUCKDB_VERSION=1.11.0

# dbt gets its own virtualenv: its dependencies conflict with Airflow's constraints file (that is why
# the Railway deployment ran dbt as a separate service). DuckDB is pinned to the same version in both
# environments, because the DuckDB file written by the extract task is read by dbt.
# No system packages are needed: DuckDB and dbt-duckdb ship as wheels, and DuckDB's own postgres
# extension speaks the protocol itself (no libpq, no compiler).
RUN python -m venv /opt/airflow/dbt-venv \
    && /opt/airflow/dbt-venv/bin/pip install --no-cache-dir "dbt-duckdb==${DBT_DUCKDB_VERSION}" "duckdb==${DUCKDB_VERSION}"

# The pipeline stages, installed against Airflow's own constraints so nothing breaks Airflow.
COPY --chown=airflow:root data/pipeline /opt/airflow/pipeline
RUN pip install --no-cache-dir \
      --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-${PYTHON_VERSION}.txt" \
      "duckdb==${DUCKDB_VERSION}" /opt/airflow/pipeline

# DuckDB extensions fetched now, so a task never depends on extensions.duckdb.org at run time.
RUN python -c "import duckdb; c = duckdb.connect(); c.execute('INSTALL httpfs'); c.execute('INSTALL postgres')" \
    && /opt/airflow/dbt-venv/bin/python -c "import duckdb; c = duckdb.connect(); c.execute('INSTALL httpfs'); c.execute('INSTALL postgres')"

# dbt project and DAGs are baked into the image: a deploy is a new image tag, never a git pull on the VM.
COPY --chown=airflow:root data/dbt /opt/airflow/dbt-project
COPY --chown=airflow:root infra/airflow-gcp/dags /opt/airflow/dags

ENV DBT_BIN=/opt/airflow/dbt-venv/bin/dbt \
    DBT_DIR=/opt/airflow/dbt-project \
    PIPELINE_WORK_DIR=/opt/airflow/data/work \
    DUCKDB_PATH=/opt/airflow/data/work/latam.duckdb
