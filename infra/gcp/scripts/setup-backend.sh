#!/usr/bin/env bash
# Creates the GCS bucket that holds the Terraform state of every environment (dev, qa, prod).
# Run once per GCP project, before the first `terraform init`.
#
#   PROJECT_ID=my-project ./infra/gcp/scripts/setup-backend.sh
#
# Each environment keeps its own state under the prefix factored/<env> (see envs/<env>/backend.tf).
# The state holds generated secrets (database password, JWT key): keep the bucket private.

set -euo pipefail

PROJECT_ID="${PROJECT_ID:?Set PROJECT_ID to the GCP project}"
REGION="${REGION:-us-east4}"
BUCKET="${BUCKET:-${PROJECT_ID}-tfstate}"

echo "==> Terraform state bucket: gs://${BUCKET} (${REGION}, project ${PROJECT_ID})"

if gcloud storage buckets describe "gs://${BUCKET}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
    echo "    already exists"
else
    gcloud storage buckets create "gs://${BUCKET}" \
        --project="${PROJECT_ID}" \
        --location="${REGION}" \
        --uniform-bucket-level-access \
        --public-access-prevention
fi

# Applied also to a bucket that already existed: the state holds generated secrets, and
# versioning lets you recover an earlier state after a bad apply.
gcloud storage buckets update "gs://${BUCKET}" --project="${PROJECT_ID}" \
    --versioning --public-access-prevention

echo
echo "Ready. Then, for each environment:"
echo "  cd infra/gcp/envs/dev"
echo "  terraform init -backend-config=\"bucket=${BUCKET}\""
