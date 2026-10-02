# Airflow for the GCP deployment: runs the pipeline stages (data/pipeline) as separate tasks.
# Build context is the repository root:  docker build . -f infra/airflow-gcp/Dockerfile
ARG AIRFLOW_VERSION=3.3.0
ARG PYTHON_VERSION=3.12

# The slim base carries Airflow's core and none of the ~100 optional providers the full image bundles
# (litellm, snowflake, ...): fewer packages to patch, and nothing we do not use. The two providers the
# stack needs are added below: postgres (Airflow's metadata database driver) and standard (@task).
FROM apache/airflow:slim-${AIRFLOW_VERSION}-python${PYTHON_VERSION}

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
      "duckdb==${DUCKDB_VERSION}" \
      apache-airflow-providers-postgres apache-airflow-providers-standard \
      /opt/airflow/pipeline

# Patch-level security fixes over Airflow's constraint pins (found with Trivy). These are minor or patch
# bumps; the DAG run in CI and the pip check below are what shows nothing broke. cryptography has a
# fix only in a new major version and is left alone on purpose.
RUN pip install --no-cache-dir "PyJWT>=2.14.0" "anyio>=4.14.2" "pyasn1>=0.6.4" "urllib3>=2.8.0" "sqlparse>=0.6.0" \
    && pip check

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

# The base image already runs as airflow; say so explicitly so nothing here can leave the image as root.
USER airflow
