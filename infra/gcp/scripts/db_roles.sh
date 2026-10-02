#!/usr/bin/env bash
# Applies infra/gcp/sql/roles.sql to the environment's database as the owner. The database has no public IP, so
# the statements run from the Airflow VM (reached through IAP), inside the scheduler container, which already
# holds the owner's connection settings.
#
#   ENVIRONMENT=prod ./infra/gcp/scripts/db_roles.sh
#
# The VM must be on (airflow_vm.sh start).

set -euo pipefail

ENVIRONMENT="${ENVIRONMENT:-prod}"
PROJECT="${PROJECT:-bitcoders-factored-hackathon}"
ZONE="${ZONE:-us-east4-a}"
VM="factored-${ENVIRONMENT}-airflow"
SQL="$(dirname "$0")/../sql/roles.sql"

REMOTE_PY='
import os, sys, psycopg2
conn = psycopg2.connect(host=os.environ["PG_HOST"], port=os.environ["PG_PORT"], dbname=os.environ["PG_DATABASE"],
                        user=os.environ["PG_USER"], password=os.environ["PG_PASSWORD"], sslmode="require")
conn.autocommit = False
with conn, conn.cursor() as cur:
    cur.execute(open("/tmp/roles.sql").read())
    cur.execute("select rolname, rolsuper, rolcreaterole, rolcreatedb, pg_has_role(rolname, '"'"'cloudsqlsuperuser'"'"', '"'"'member'"'"') from pg_roles where rolname in ('"'"'backend_app'"'"', '"'"'agent_app'"'"') order by 1")
    for name, sup, crole, cdb, cs in cur.fetchall():
        print(f"{name}: superuser={sup} createrole={crole} createdb={cdb} cloudsqlsuperuser={cs}")
print("roles.sql applied")
'

gcloud compute scp "$SQL" "${VM}:/tmp/roles.sql" --zone "$ZONE" --project "$PROJECT" --tunnel-through-iap --quiet
gcloud compute ssh "$VM" --zone "$ZONE" --project "$PROJECT" --tunnel-through-iap --quiet --command "
    sudo docker cp /tmp/roles.sql airflow-scheduler-1:/tmp/roles.sql &&
    sudo docker exec -i airflow-scheduler-1 python -c '$REMOTE_PY';
    rm -f /tmp/roles.sql"
