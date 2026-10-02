#!/usr/bin/env bash
# Script de gestión operativa Just-in-Time para Cloud SQL en GCP
# Permite pausar (hibernar) la base de datos para reducir el costo a ~$0.05 USD/día,
# y reactivarla en 60 segundos antes de una presentación o prueba.

set -euo pipefail

# Environment of the stack (dev, qa or prod). INSTANCE and REGION can be overridden, for example
# INSTANCE=factored-hackathon REGION=us-central1 for the stack deployed before the environment split.
ENVIRONMENT="${ENVIRONMENT:-dev}"
INSTANCE="${INSTANCE:-factored-${ENVIRONMENT}}"
PROJECT="${GCP_PROJECT_ID:-bitcoders-factored-hackathon}"

usage() {
    echo "Uso: $0 {pause|resume|status}"
    echo ""
    echo "  pause   - Apaga la máquina virtual e IP de Cloud SQL (Gasto cae a ~$0.05 USD/día por disco)."
    echo "  resume  - Enciende la base de datos en ~60 segundos con todos los datos intactos."
    echo "  status  - Muestra el estado actual y la política de activación de la instancia."
    exit 1
}

if [ $# -lt 1 ]; then
    usage
fi

ACTION="$1"

case "$ACTION" in
    pause)
        echo "==> Pausando Cloud SQL ($INSTANCE en $PROJECT)..."
        gcloud sql instances patch "$INSTANCE" \
            --project="$PROJECT" \
            --activation-policy=NEVER \
            --quiet
        echo "✔ Instancia pausada exitosamente. El cómputo y la IP ya no generan cargos."
        ;;
    resume)
        echo "==> Reanudando Cloud SQL ($INSTANCE en $PROJECT)..."
        gcloud sql instances patch "$INSTANCE" \
            --project="$PROJECT" \
            --activation-policy=ALWAYS \
            --quiet
        echo "✔ Instancia reanudada exitosamente. Lista para atender peticiones en <5 ms."
        ;;
    status)
        echo "==> Estado actual de Cloud SQL ($INSTANCE en $PROJECT):"
        gcloud sql instances describe "$INSTANCE" \
            --project="$PROJECT" \
            --format="table(name,state,settings.activationPolicy,settings.dataDiskSizeGb,ipAddresses[0].ipAddress)"
        ;;
    *)
        usage
        ;;
esac
