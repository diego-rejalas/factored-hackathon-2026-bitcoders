#!/usr/bin/env bash
# Operate the Airflow VM. It is meant to be OFF unless a pipeline run is under way: a nightly
# schedule stops it, and this script starts and stops it by hand.
#
#   ./infra/gcp/scripts/airflow_vm.sh start      # power on and wait until Airflow answers
#   ./infra/gcp/scripts/airflow_vm.sh tunnel     # open the UI at http://localhost:8080 (IAP, no public IP)
#   ./infra/gcp/scripts/airflow_vm.sh trigger    # start a pipeline run
#   ./infra/gcp/scripts/airflow_vm.sh stop       # power off (disks keep billing, compute does not)
#   status | ssh [command] | logs [service] | deploy
#
# Environment: ENVIRONMENT (default prod), GCP_PROJECT_ID, AIRFLOW_ZONE, AIRFLOW_VM.

set -euo pipefail

ENVIRONMENT="${ENVIRONMENT:-prod}"
PROJECT="${GCP_PROJECT_ID:-bitcoders-factored-hackathon}"
ZONE="${AIRFLOW_ZONE:-us-east4-a}"
VM="${AIRFLOW_VM:-factored-${ENVIRONMENT}-airflow}"
COMPOSE="sudo docker compose -f /opt/airflow/docker-compose.yml"

vm()  { gcloud compute instances "$@" "$VM" --zone "$ZONE" --project "$PROJECT"; }
ssh_vm() { gcloud compute ssh "$VM" --tunnel-through-iap --zone "$ZONE" --project "$PROJECT" --quiet -- "$@"; }

state() { vm describe --format="value(status)"; }

wait_ready() {
    echo "Waiting for Airflow (the first boot also installs Docker and can take several minutes)..."
    for _ in $(seq 1 60); do
        if ssh_vm "curl -fsS http://localhost:8080/api/v2/monitor/health" >/dev/null 2>&1; then
            echo "Airflow is up."
            return 0
        fi
        sleep 15
    done
    echo "Airflow did not answer in 15 minutes. Check: $0 logs" >&2
    return 1
}

case "${1:-}" in
    start)
        [ "$(state)" = "RUNNING" ] || vm start
        wait_ready
        ;;
    stop)
        vm stop
        ;;
    status)
        echo "VM $VM: $(state)"
        if [ "$(state)" = "RUNNING" ]; then
            ssh_vm "$COMPOSE ps --format 'table {{.Service}}\t{{.Status}}'" || true
        fi
        ;;
    tunnel)
        echo "Airflow UI: http://localhost:8080  (user: admin; password: Secret Manager, factored-${ENVIRONMENT}-airflow-admin-password)"
        gcloud compute start-iap-tunnel "$VM" 8080 --local-host-port=localhost:8080 --zone "$ZONE" --project "$PROJECT"
        ;;
    ssh)
        shift
        ssh_vm "$@"
        ;;
    trigger)
        ssh_vm "$COMPOSE exec -T scheduler airflow dags trigger latam_bank_gcp"
        ;;
    logs)
        ssh_vm "$COMPOSE logs --tail 150 ${2:-scheduler}"
        ;;
    deploy)
        # Pull the image tag in the VM's metadata and restart the stack (refresh.sh runs first).
        ssh_vm "sudo systemctl restart airflow && $COMPOSE ps"
        ;;
    *)
        sed -n '2,14p' "$0"
        exit 1
        ;;
esac
