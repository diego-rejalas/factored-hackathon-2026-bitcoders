ARG AIRFLOW_VERSION=3.3.0
ARG PYTHON_VERSION=3.12

FROM apache/airflow:${AIRFLOW_VERSION}-python${PYTHON_VERSION}

ARG AIRFLOW_VERSION
ARG PYTHON_VERSION

# Install extra Python packages for custom DAGs. Constrained against Airflow's own
# constraints file so a transitive dependency bump can't silently break Airflow.
# https://airflow.apache.org/docs/docker-stack/build.html
COPY infra/airflow/requirements.txt /requirements.txt
RUN pip install --no-cache-dir \
      --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-${PYTHON_VERSION}.txt" \
      -r /requirements.txt

# DAG + dbt content lives in data/ (data engineering logic), separate from this
# deployment config (infra/airflow/) — build context is the repo root so both
# are reachable here. Baked in at build time (simple, rebuild-on-change) rather
# than the market-standard git-sync sidecar / separately-deployed dbt image —
# right tradeoff at this scale, documented as the scaling path in
# spec/ARCHITECTURE.md, not implemented now.
COPY data/dags/ /opt/airflow/dags/
COPY data/dbt/ /opt/airflow/dbt/

COPY --chmod=0755 infra/airflow/docker-entrypoint.sh /opt/airflow/railway-entrypoint.sh

# Run as root so the entrypoint can chown a freshly-mounted Railway volume
# (owned by root by default) before writing to it. The base image's own
# /entrypoint (invoked at the end of our script) drops back to the airflow
# user via gosu once it takes over, same as it does for AIRFLOW_HOME.
USER root

ENTRYPOINT ["/opt/airflow/railway-entrypoint.sh"]
