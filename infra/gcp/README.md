# infra/gcp/ — despliegue primario en GCP (migración completa)

Desde la migración completa (rama `feat/app-layer`), **GCP es el despliegue
primario**: Cloud Run + Cloud SQL ejecutan el mismo código que probamos en
local, el pipeline corre como Cloud Run Job sin Airflow, y el frontend vive en
GCP (Next.js standalone con `AGENT_URL` en runtime). Railway queda como
legacy: `.railway/railway.ts` ya no se aplica (no corras `railway config
plan/apply` contra él salvo teardown controlado).

```text
┌────────────────────────────────────────────────────────────────┐
│ Cloud Run: frontend ──► Cloud Run: agent ──► Cloud Run: backend│
│ (Next.js, AGENT_URL)      (guardrail)          (tool layer)    │
│                              │                      │           │
│                              ▼                      ▼           │
│              Cloud SQL Postgres (data): gold.*, app.*,          │
│              agent.trace_log (Modo Just-in-Time / Hibernable)   │
│                              ▲                                  │
│ Cloud Run Job: etl ── S3 (DuckDB + dbt-duckdb en RAM)           │
│ (publica solo gold.*, purga tablas crudas, sin servicio dbt)    │
└────────────────────────────────────────────────────────────────┘
```

Qué reutiliza y qué replica:

| Pieza | En GCP | Cambios de código |
|---|---|---|
| backend / agent | Cloud Run, **mismos Dockerfiles** de `backend/` y `agent/` | Ninguno |
| frontend | Cloud Run, `frontend/Dockerfile` (Next.js standalone); `AGENT_URL` es env de runtime | Solo `output: standalone` + URL por prop |
| Pipeline | Cloud Run **Job** (`etl/`) con DuckDB + `dbt-duckdb` en RAM: procesa 23.5M filas en ~2.5 min y publica solo `gold.*` | Cero servicios dbt sueltos; esquemas crudos eliminados de Postgres |
| Postgres | Cloud SQL for PostgreSQL 16 (DB `data`, solo ~150 MB de Gold) | Hibernación Just-in-Time (`./manage_db.sh pause/resume`) |
| Secretos | Secret Manager (JWT autogenerado; keys OpenRouter/TypeSafe/S3 se copian) | Ninguno |
| CI/CD | `.github/workflows/gcp-deploy.yml`: push → build (4 imágenes) + plan; `workflow_dispatch` → apply (+ ETL) | — |

## Prerequisitos (una vez)

1. Proyecto GCP con billing habilitado + `gcloud` y `terraform >= 1.6` instalados.
2. Autenticarte: `gcloud auth login && gcloud config set project <PROJECT_ID>`.
3. **Bucket de estado de Terraform** (CI y locales comparten estado):
   ```bash
   gcloud storage buckets create gs://<PROJECT_ID>-tfstate --location=us-central1 --uniform-bucket-level-access
   ```
4. Para el deploy por CI: secret `GCP_SA_KEY` (JSON de una service account con
   rol `Editor` del proyecto) y variables `GCP_PROJECT_ID`, `GCP_STATE_BUCKET`
   en el repo — ver `.github/workflows/gcp-deploy.yml`. Para deploy local no
   hacen falta (usa tus credenciales de `gcloud`).

## Despliegue

```bash
cd infra/gcp
cp terraform.tfvars.example terraform.tfvars   # y edita project_id/region/keys

# 1) Construir y subir las 4 imágenes (desde la raíz del repo)
docker build . -f backend/Dockerfile         -t <REGION>-docker.pkg.dev/<PROJECT_ID>/factored-hackathon/backend:latest  --platform linux/amd64
docker build . -f agent/Dockerfile           -t <REGION>-docker.pkg.dev/<PROJECT_ID>/factored-hackathon/agent:latest    --platform linux/amd64
docker build . -f infra/gcp/etl/Dockerfile   -t <REGION>-docker.pkg.dev/<PROJECT_ID>/factored-hackathon/etl:latest      --platform linux/amd64
docker build . -f frontend/Dockerfile        -t <REGION>-docker.pkg.dev/<PROJECT_ID>/factored-hackathon/frontend:latest --platform linux/amd64
gcloud auth configure-docker <REGION>-docker.pkg.dev
docker push --all-tags <REGION>-docker.pkg.dev/<PROJECT_ID>/factored-hackathon

# 2) Terraform
terraform init -backend-config="bucket=<PROJECT_ID>-tfstate"
terraform plan
terraform apply

# 3) Copiar las credenciales S3 del organizador (estaban en Railway, no en el repo)
echo -n "<LATAM_BANK_AWS_ACCESS_KEY_ID>"     | gcloud secrets versions add latam-bank-aws-id     --data-file=-
echo -n "<LATAM_BANK_AWS_SECRET_ACCESS_KEY>" | gcloud secrets versions add latam-bank-aws-secret --data-file=-

# 4) Cargar los datos
gcloud run jobs execute etl --region=<REGION> --wait
```

Con eso el stack queda sirviendo. `terraform output` imprime las URLs
(`frontend_uri`, `agent_uri`, `backend_uri`, `cloudsql_public_ip`). El deploy
por CI hace lo mismo: push a `main`/`feat/app-layer` construye y planifica;
`workflow_dispatch` con `terraform_action=apply` (+`run_etl`) despliega.

## Smoke

1. Elegir un cliente real del dataset (el job ya cargó `gold.*`):
   ```bash
   gcloud sql connect factored-hackathon --user=app --database=data \
     -c "select customer_id, document_number from gold.customers where document_number is not null limit 5"
   ```
2. Probar el agent:
   ```bash
   pip install httpx
   AGENT_URL=<agent_uri> CUSTOMER_ID=<...> DOCUMENT_NUMBER=<...> python smoke.py
   ```
3. Abrir `<frontend_uri>` y usar la UI (login → disputa). Para apuntar el
   frontend a otro entorno basta cambiar `AGENT_URL` del servicio.

## Gestión Just-in-Time (Ahorro de Costos en GCP)

Para evitar el cobro fijo de Cloud SQL mientras no se esté probando o presentando:

```bash
# 1. Pausar la base de datos (Gasto cae a ~$0.05 USD/día por disco)
./manage_db.sh pause

# 2. Despertar la base de datos (En ~60 segundos vuelve a estar operativa)
./manage_db.sh resume

# 3. Ver estado actual
./manage_db.sh status
```

## Teardown de Railway (transición)

Solo cuando el stack GCP esté verificado con datos y smoke en verde:

```bash
# revisar qué se destruiría y luego aplicar
railway config plan   # con .railway/railway.ts tal cual
railway config apply  # destruye el proyecto factored-hackathon (Postgres incluido)
```

Las credenciales S3 del organizador viven en la service de Railway: cópialas a
Secret Manager (paso 3) **antes** de destruir.

## Límites y hardening (documentados, aceptados a escala hackathon)

- **Cloud SQL con IP pública + password** (sin redes autorizadas ni SSL
  forzado): cero cambios de código en backend/agent. Endurecer: redes
  autorizadas, `ssl_mode=ENCRYPTED_ONLY` + `PGSSLMODE=require`, o IP privada
  con Serverless VPC connector.
- **dbt y backend con invoker `allUsers`**: paridad con el modelo de confianza
  de Railway (dominio privado sin auth). Endurecer: ingress `internal` +
  VPC connector, u OIDC ID tokens entre servicios.
- **Estado de Terraform en GCS** con lock por defecto; el estado contiene
  secretos generados (passwords) — restringir el bucket a los dueños.
- **Costo**: Cloud Run a 0 instancias ≈ $0; Cloud SQL `db-f1-micro` + 20 GB es
  el único costo always-on (orden de decenas de USD/mes). `terraform destroy`
  lo baja todo (`db_deletion_protection=false` por defecto; ponerlo en `true`
  cuando el stack tenga datos que importen).
- **Pipeline sin Airflow**: el Job ejecuta los mismos pasos del DAG;
  `ops.etl_runs` registra `runner: cloud-run-job`. Para orquestación/UI de
  DAGs en GCP, el camino natural sería Composer (fuera de alcance ahora).
