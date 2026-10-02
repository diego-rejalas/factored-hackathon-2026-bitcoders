#!/usr/bin/env bash
# Fetches the dbt documentation (lineage graph, columns, tests) that the pipeline stores after each run.
#
#   ENVIRONMENT=prod ./infra/gcp/scripts/lineage.sh            # download the latest and open it
#   ENVIRONMENT=prod ./infra/gcp/scripts/lineage.sh <run>      # a given run (the 8-character id in the bucket)
#   ./infra/gcp/scripts/lineage.sh list                        # the stored runs
#
# The page is one file (static_index.html): open it in any browser. It describes the data model, not
# customers, but the bucket is private, so it is downloaded with your own Google credentials.

set -euo pipefail

ENVIRONMENT="${ENVIRONMENT:-prod}"
PROJECT="${PROJECT:-bitcoders-factored-hackathon}"
BUCKET="gs://factored-${ENVIRONMENT}-lakehouse-${PROJECT}"
OUT="${OUT:-docs/lineage}"
WHICH="${1:-latest}"

if [ "$WHICH" = "list" ]; then
    gcloud storage ls "${BUCKET}/docs/runs/" --project "$PROJECT"
    exit 0
fi

SRC="${BUCKET}/docs/latest"
[ "$WHICH" != "latest" ] && SRC="${BUCKET}/docs/runs/${WHICH}"

mkdir -p "$OUT"
gcloud storage cp "${SRC}/*" "$OUT/" --project "$PROJECT"
echo "downloaded to ${OUT}/static_index.html"
command -v xdg-open >/dev/null && xdg-open "${OUT}/static_index.html" >/dev/null 2>&1 || true
