# infra/gcp/: GCP infrastructure by environment

GCP Terraform split into **three environments** (`dev`, `qa`, `prod`) that share modules. Each environment has its own state, its own resources (all prefixed `factored-<environment>`) and defaults suited to its role. The deployment procedure for `prod` is in [`docs/DEPLOY.md`](../../docs/DEPLOY.md).

```text
infra/gcp/
├── envs/
│   ├── dev/    backend.tf provider.tf main.tf variables.tf outputs.tf terraform.tfvars.example
│   ├── qa/     (same contents; only the defaults in variables.tf change)
│   └── prod/
├── modules/
│   ├── foundation/         project APIs + Artifact Registry
│   ├── network/            VPC, subnet, Private Service Access, IAP firewall and optional NAT
│   ├── cloudsql/           Cloud SQL Postgres 18 (database `data`, user `app`)
│   ├── secrets/            Secret Manager: JWT, database password, LLM and S3 keys
│   ├── lakehouse/          GCS bucket for the bronze and silver Parquet
│   ├── cloud_run_service/  one Cloud Run service with its own service account
│   ├── edge/               global Application Load Balancer + Cloud Armor in front of the frontend and the agent
│   ├── airflow_vm/         the Airflow VM
│   └── etl_job/            the ETL Cloud Run Job
├── bootstrap/              GitHub identity federation (applied by hand, once)
├── sql/                    roles.sql: permissions of each service's database role
├── scripts/                setup-backend.sh · manage_db.sh · db_roles.sh · airflow_vm.sh · grant_access.sh · e2e.py
├── airflow/                Airflow image and the DAG that runs on the VM
└── etl/                    Dockerfile and run_pipeline.py of the job image
```

`main.tf` is identical in the three environments (so they do not diverge). What changes is `backend.tf` (the state prefix) and the defaults in `variables.tf`.

## What each environment deploys

`foundation` → `network` → `cloudsql`, `secrets`, `lakehouse` → services `backend`, `agent`, `frontend` and the `etl` job. A real `plan` against the project gives **54 resources in each environment** (7 are the network and two APIs).

| | dev | qa | prod |
|---|---|---|---|
| Cloud SQL | `db-f1-micro`, 20 GB | `db-g1-small`, 20 GB | `db-custom-2-7680`, 50 GB, point-in-time recovery |
| Database connectivity (`db_connectivity`) | `private_ip`: no public IP, over the VPC (`dev` used an open public IP before, and was changed after the security analysis) | `private_ip` | `private_ip` |
| Airflow (`enable_airflow`) | off | off | **on**: an `e2-standard-4` VM, stopped at night and started on demand (`scripts/airflow_vm.sh`) |
| Network ranges | `10.10.0.0/24` and `10.10.1.0/24` | `10.20.0.0/24` and `10.20.1.0/24` | `10.30.0.0/24` and `10.30.1.0/24` |
| Deletion protection (database and Cloud Run) | no | no | **yes** |
| Minimum instances (backend, agent) | 0 | 0 | 1 |
| Lake bucket | can be destroyed with data | can be destroyed with data | **no** |

The differences come from variables (`db_tier`, `use_cloud_sql_connector`, `db_deletion_protection`, `agent_min_instances`, ...). They can be changed in a `terraform.tfvars` without touching the code.

## Improvements over the earlier flat Terraform

- **Each service has its own service account** and can read only the secrets assigned to it. Before, all three used the default compute account, with access to every secret in the project.
- **The database password is in Secret Manager** and mounted as an environment variable. Before, it was written in clear text in each service's definition.
- **Its own network per environment** (`modules/network`): a VPC, an application subnet with Private Google Access, and Private Service Access so that Cloud SQL has a private IP. In qa and prod the database **has no public address**.
- **Three ways to reach the database** (`db_connectivity`): `public_ip` (the original stack), `connector` (the Cloud SQL connector over a socket, with no network list; the apps read `PG_HOST` as the libpq or asyncpg host and both accept a socket directory) and `private_ip`. It is changed with a variable.
- **Cloud Run uses Direct VPC egress** with `PRIVATE_RANGES_ONLY`: only traffic to private ranges goes through the VPC, and the rest leaves to the internet as usual, so **Cloud NAT is not needed** for the ETL (S3) or for the agent (OpenRouter).
- **State separated per environment** (`env/<environment>`, in `bitcoders-factored-hackathon-tfstate`) and GCS locking by default.
- The organizer's S3 keys are loaded by hand as a new secret version. A later `apply` does not revert it.
- A lake bucket with versioning and public access prohibited.
- The ETL account's `run.invoker` permission on its own job was removed, because it served no purpose.
- Default region `us-east4` (the closest to `us-east-2`, where the organizer's bucket is), instead of `us-central1`.

## Prerequisites (once per project)

1. A GCP project with billing, and `gcloud` and `terraform >= 1.6` installed. Authenticate: `gcloud auth login && gcloud config set project <PROJECT_ID>`.
2. Create the state bucket (shared by the three environments):
   ```bash
   PROJECT_ID=<PROJECT_ID> ./infra/gcp/scripts/setup-backend.sh
   ```
3. For CI deployment (with no stored key, using Workload Identity Federation): apply `infra/gcp/bootstrap` once (by hand, with an admin account) and copy its three outputs to repository **secrets** (`GCP_WORKLOAD_IDENTITY_PROVIDER`, `GCP_PLAN_SA` and `GCP_DEPLOY_SA`: the workflow log is public, and GitHub hides a secret but shows a variable), together with the variables `GCP_PROJECT_ID` and `GCP_STATE_BUCKET` (and optionally `GCP_REGION`). See `.github/workflows/gcp-deploy.yml`.

## Deploying an environment by hand

```bash
cd infra/gcp/envs/dev                      # or qa, prod
cp terraform.tfvars.example terraform.tfvars   # edit project_id and, if you want, the keys
terraform init        # the bucket and the prefix are already in backend.tf

# 1. APIs and the image registry
terraform apply -target=module.foundation

# 2. Build and push the images (from the repo root)
REG=us-east4-docker.pkg.dev/<PROJECT_ID>/factored-dev
gcloud auth configure-docker us-east4-docker.pkg.dev
for s in backend agent frontend; do docker build . -f $s/Dockerfile -t $REG/$s:latest && docker push $REG/$s:latest; done
docker build . -f infra/gcp/etl/Dockerfile -t $REG/etl:latest && docker push $REG/etl:latest

# 3. The rest
terraform apply
```

After the first `apply`, copy the organizer's S3 keys to Secret Manager (never to git or to Terraform variables):

```bash
printf '%s' "$LATAM_BANK_AWS_ACCESS_KEY_ID"     | gcloud secrets versions add factored-dev-latam-bank-aws-id     --data-file=-
printf '%s' "$LATAM_BANK_AWS_SECRET_ACCESS_KEY" | gcloud secrets versions add factored-dev-latam-bank-aws-secret --data-file=-
```

Run the ETL: `gcloud run jobs execute factored-dev-etl --region us-east4 --wait`.

## Through CI

`.github/workflows/gcp-deploy.yml`: a `push` to `main` builds the images and runs a **dev** `plan`. With `workflow_dispatch` you choose the environment (`dev`, `qa`, `prod`) and `plan` or `apply`, and optionally run the ETL. Because the job uses a GitHub `environment:`, a manual approval can be required for `prod` in the repository settings.

## End-to-end test

`scripts/e2e.py` runs 11 scenarios against a deployed agent (login, token rejections, and the policy paths: resolves, asks, escalates for amount, for an already posted transaction, for fraud, injection, another customer's data; in Spanish and Portuguese). It exits with code 0 only if all of them behave as expected:

```bash
AGENT_URL=$(terraform output -raw agent_uri) python infra/gcp/scripts/e2e.py
```

The customers are rows of the organizer's synthetic dataset, and the expectations assume the default USD 500 threshold.

## Entry and permissions (prod)

- **Entry:** `https://<ip>.sslip.io` (the `edge_domain` variable for your own domain; `edge_additional_domains` adds more names, each with its own managed certificate next to the main one, so a new name can be added without interrupting the current one). The deploy workflow reads both from the repository variables `EDGE_DOMAIN` and `EDGE_ADDITIONAL_DOMAINS` (the second as a JSON list, for example `["app.example.com"]`), so no domain is written in the code. Each name needs a DNS A record to the load balancer's address, without a proxy in front, before its certificate can be issued. An Application Load Balancer with a managed certificate and Cloud Armor (an IP rate limit and SQL injection, XSS and Log4j rules) sends `/` to the frontend and `/agent/*` to the agent, so the browser calls the agent on the same origin. With `edge_lockdown` the frontend and the agent accept traffic only from the load balancer. It is switched on in two phases: `enable_edge` creates the load balancer, and once its certificate is `ACTIVE` (15 to 60 minutes) `edge_lockdown` closes direct access. Cloud Armor rules take about 3 minutes to propagate.
- **A closed backend:** only the agent's service account is `run.invoker`, and the agent sends an ID token in `X-Serverless-Authorization`. Without credentials it answers 403.
- **One database role per service:** `backend_app` (reads `gold`, owns `app`) and `agent_app` (owns `agent`, no access to `gold`). Deployment order: `apply` (creates the users), then `scripts/db_roles.sh` (applies `sql/roles.sql` from the VM), then `apply` with `service_db_users=true`. The pipeline grants `SELECT` on `gold` to the backend after every publication (`GOLD_READER_ROLES`).
- **Deployment from GitHub with no stored key:** `bootstrap/` creates the Workload Identity pool and two service accounts (a read-only plan account, and deployment only from `main`).

## Security

The Checkov and Trivy findings, what was fixed, what is accepted and how to repeat the scans are in `docs/SECURITY.md`. A summary of what applies to this folder: mandatory SSL and logging in Cloud SQL, a database with no public IP in the three environments, flow logs on the subnet, and each deployment's plan is scanned with Checkov before it is applied.

## Saving costs

```bash
ENVIRONMENT=dev ./infra/gcp/scripts/manage_db.sh pause    # the database stops billing for compute
ENVIRONMENT=dev ./infra/gcp/scripts/manage_db.sh resume   # it is back in ~60 s with the data
ENVIRONMENT=dev ./infra/gcp/scripts/manage_db.sh status
```

Cloud Run at 0 instances costs almost nothing, and Cloud SQL is the only permanent cost.

### The demo sleeps by itself and wakes on request (`enable_waker`)

With `enable_waker` (on in `prod`) nobody has to run those commands. The `waker` Cloud Run service (`waker/`, module `modules/waker`) stops Cloud SQL after `waker_idle_minutes` (15) without traffic to the frontend or the agent, and starts it when someone asks. The backend and the agent run with no minimum instance, so the whole demo is asleep except what cannot be: the load balancer, Cloud Armor and the disks.

```text
┌──────────────────────────────────┐
│ Cloud Scheduler, every 5 min     │
└────────────────┬─────────────────┘
                 ▼  POST /sleep-if-idle (ID token)
┌──────────────────────────────────┐        ┌──────────────────────┐
│ waker  (Cloud Run, min 0)        │───────►│ Cloud SQL            │
│  GET /status · POST /wake        │ ALWAYS │ activation policy    │
└────────────────▲─────────────────┘ NEVER  │ ALWAYS / NEVER       │
                 │  /waker/*                 └──────────────────────┘
┌────────────────┴─────────────────┐
│ load balancer + Cloud Armor      │◄── a visitor of the app (the waiting screen in frontend/)
└──────────────────────────────────┘◄── the landing's "Live demo" (site/)
```

- **Waking.** Opening the app while it sleeps shows a waiting screen that wakes it by itself and shows two steps: the database, and the services (the screen waits until `/meta/demo-scenarios` answers, which starts the agent and the backend from zero and builds the scenarios' cache, about half a minute). Only then does the app appear, so the first login never shows "scenarios not available". On the landing, the "Live demo" links wake it first and open the app when it is ready. Cloud SQL takes about a minute.
- **An open session.** While a tab is visible and in use (a click, a key or a scroll in the last 20 minutes) it sends a request to the agent every 4 minutes, which counts as use, so the demo does not sleep under someone reading. When a tab comes back to the front after a minute or more and the demo went to sleep meanwhile, the waiting screen covers the app, which stays mounted, so the session is not lost.
- **Sleeping.** Every 5 minutes (`waker_check_schedule`) the idle check looks at the request count of the frontend and the agent (Cloud Monitoring). It does nothing if the demo was woken less than `waker_idle_minutes` ago, if there was any request in that time, or if the Airflow VM is running. If the check cannot read a metric, the database stays awake.
- **What the waker may do.** A custom role with `cloudsql.instances.get`, `cloudsql.instances.update` and `compute.instances.get`, plus `roles/monitoring.viewer`. `/wake` is public and idempotent; `/sleep-if-idle` accepts only an ID token of the scheduler's service account. Cloud Armor's per-IP rate limit protects both.
- **Terraform does not undo it.** `modules/cloudsql` ignores `activation_policy` and `user_labels` after creation (the waker stamps the time of the last wake in a label), so an `apply` does not wake a sleeping database. The workflow starts the database before it applies, because the backend and the agent connect to it on start and Cloud Run starts the new revision to check it.
- **Airflow.** `airflow_vm.sh start` starts the database first. The VM keeps the database awake while it runs.
- **Switch it off:** `enable_waker=false` (the minimum instances go back to `backend_min_instances` and `agent_min_instances`). If the database is asleep at that moment, `manage_db.sh resume` wakes it.
- **Needs once, by hand:** apply `bootstrap/` again (the deploy account gets `roles/cloudscheduler.admin` and `roles/iam.roleAdmin`), and, for the landing, set the repository variable `WAKER_ALLOWED_ORIGINS` to a JSON list with the landing's origin.
- **CPU billed per request** (`run_cpu_idle`, on in `prod`): the backend, agent, frontend and waker pay for CPU only while a request runs. The default of Cloud Run (always allocated) bills an instance for its whole life, which for the waker (called every few minutes) would be the whole day. The one thing that waits for the next request is the backend's refresh of the demo scenarios, started after a response.
- **Cost, estimated** (public prices of `us-east4`, about 20 % either way): about US$9 a day awake all day, about US$2 a day asleep, about US$3 on a day with a few hours of use. Before the waker the demo cost about US$9 every day.

## State and what is missing

**Verified:** `terraform fmt` and `validate` pass in the three environments. **`prod` was applied** (edge with Cloud Armor, private backend, one database role per service, the Airflow VM and deployment from GitHub), and `scripts/e2e.py` passed 11 of 11 against it. The current code version was applied from GitHub on 2026-10-05 (workflow run 37258119421). The steps that follow an apply (database roles, secrets, new revisions, the end-to-end check) are in [`docs/DEPLOY.md`](../../docs/DEPLOY.md).

**Not verified:**
- **The current version has not been checked on `prod` after the apply.** The backend migrations (`0003` and `0005`) run on `prod`'s database at startup. `0003` closes duplicate cases per transaction, so the test data there should have been reviewed first.
- `dev` and `qa` were validated only with `plan`, and `connector` (the Cloud SQL connector) was not tested.

**Still to harden:**
- A budget with an alert, and monitoring. No alert, dashboard or uptime check is defined.
- **Human access to a private database:** from a laptop you cannot reach an instance with no public IP (not even with `cloud-sql-proxy`, which would have to be inside the VPC). You enter through IAP to the Airflow VM (the firewall in `modules/network` allows the IAP range for instances with the `iap` tag) and connect from there. See [`docs/ONBOARDING.md`](../../docs/ONBOARDING.md).
- The `typesafe-api-key` secret is still declared and empty, and nothing uses it any more. Removing it is an `apply` that destroys a secret, and it is left for a deliberate change.
- The `backend`, `agent` and `frontend` containers run as `root` (see [`docs/SECURITY.md`](../../docs/SECURITY.md)).

## An earlier stack

Before the environments were split, a deployment existed with the old names (`factored-hackathon`, `us-central1`) and unprefixed state. The current environments are **new** deployments and do not replace or destroy it. If it still exists, it is retired with `terraform destroy` from commit `62a97b1` and its state, after the new environment has been verified.

The landing, the pitch video's bucket and the app's DNS record are not here: they are in [`../cloudflare`](../cloudflare/README.md), with their own state and workflow.
