# Security

*The application's controls and the results of scanning the infrastructure with Checkov and Trivy.*

[Index](README.md) · [Architecture](ARCHITECTURE.md) · [API](API.md)

## Application controls

| Control | Where |
|---|---|
| Identity always comes from a signed JWT with an expiry and a role (`customer` or `admin`). The agent never accepts a `customer_id` typed in the chat | backend and agent |
| Every query is filtered by the customer in the token. Someone else's resource returns 404, not 403, so it does not confirm that it exists | backend |
| Policy (threshold, fraud, ambiguity) is deterministic code, not a prompt | `agent/app/guardrail.py` |
| A model's draft passes checks before it is sent | `agent/app/grounding.py` |
| `is_fraud` and `fraud_score` do not exist in `gold` or in any response schema (a contract test checks this) | backend |
| Passwords use argon2id (demo accounts) and bcrypt (specialist console), with lockout after failed attempts and the same response for an unknown user and a wrong password | backend |
| The backend is private. Only service accounts with `run.invoker` call it, with their ID token | infrastructure |
| Each service has its own service account, its own secrets and its own database role | infrastructure |
| Cloud Armor with WAF rules and a rate limit in front of the frontend and the agent | infrastructure |
| Cloud SQL with a private IP and mandatory SSL. The Airflow VM has no external IP and is reached through IAP | infrastructure |
| Deployment from GitHub uses identity federation, with no stored keys | infrastructure |

The chat login still accepts customer plus ID number. It is a sandbox and is presented as one, not as real identity.

## What each tool covers

| | Checkov | Trivy |
|---|---|---|
| Terraform | Yes | Yes |
| Dockerfiles and GitHub Actions workflows | Yes | Yes |
| Vulnerabilities in the built images | No | **Yes** |
| Dependencies in lock files | No | Yes |
| Secrets in the repository | No | Yes |

## What was found and what was done

| Finding | Verdict | Action |
|---|---|---|
| Cloud SQL without mandatory SSL | Real | `ssl_mode = ENCRYPTED_ONLY` in all three environments |
| `dev` Cloud SQL with a public IP open to `0.0.0.0/0` | Real | `dev` moves to a private IP, like qa and prod |
| No logging of connections, waits, checkpoints or DDL | Real | Audit options enabled in all three environments |
| Subnet without flow logs | Real | 50% sampling |
| ETL container running as `root` | Real | User `etl` (uid 10001). The full pipeline was tested as non-root |
| Airflow image without `USER` | Real, minor | Explicit `USER airflow` |
| Workflows with write permissions by default | Real | `permissions: contents: read` at the top level |
| Airflow image with 25 critical and 208 high | Real | `slim` base and updated dependencies: 17 critical and 148 high, from 2.81 GB to 1.34 GB |
| The organizer's S3 keys | Only in the local, **unversioned** `.env` (checked) | None: there are no secrets in the repository or in the images |

## Accepted decisions, with the reason

Each one is commented in `.checkov.yaml` and `.trivyignore.yaml`.

- **Google-managed encryption keys instead of customer-managed** (CKV_GCP_37, 38, 84): a customer-supplied key turns a lost key into lost data, and KMS adds a dependency that is not needed here.
- **Instance role for the Compute service agent** (CKV_GCP_42): it needs it to stop the Airflow VM on a schedule. It is a Google agent, not a workload account.
- **No `log_hostname`, `log_duration` or `pgaudit`**: the first adds a DNS query per connection, the second logs every statement, and `pgaudit` logs nothing until the extension is created.
- **No access log for the lake bucket**: it would need a second bucket just for logs. The data is synthetic and the bucket is private.
- **CKV_DOCKER_2 (HEALTHCHECK)**: Cloud Run ignores that instruction and uses its own probes.

## Still open

- The `backend`, `agent` and `frontend` containers run as `root`. Each Dockerfile needs a non-root `USER`.
- The base images (Python on Debian 13.7 and Airflow on Debian 12.15) have 45 and 153 system packages with high vulnerabilities **with no published fix**. A newer base image resolves this once the patch exists.
- Real auditing with `pgaudit` and an access log for the lake were not done.

## Why Terraform is not scanned from source

Checkov and Trivy read the HCL without evaluating it. They do not resolve `dynamic` blocks or conditionals on variables, so they report as missing options that the real configuration does set (the SSL mode and the Cloud SQL logs). Scanning the source flagged 8 rules in the Cloud SQL module as failed in every environment.

So in CI, Checkov reviews only Dockerfiles and workflows, with a baseline (`.checkov.baseline`) of earlier findings: new ones fail the CI and known ones do not. The deployment workflow (`gcp-deploy.yml`) generates the plan, scans it with Checkov in `terraform_plan` mode and applies **that same plan**.

## What the CI enforces

| Gate | Fails when |
|---|---|
| Checkov on Dockerfiles and workflows | a **new** finding appears |
| Trivy `config` | a HIGH or CRITICAL finding appears that is not listed in `.trivyignore.yaml` |
| Trivy `fs` | a secret is committed |
| Trivy `image` (Airflow and ETL) | there is a CRITICAL vulnerability **with an available fix**. Those without one do not count because they would block every build |
| Checkov on the plan in `gcp-deploy` | the resolved plan breaks a rule that is not skipped |

## Reproducing it locally

```bash
# Dockerfiles and workflows (uses .checkov.yaml and .checkov.baseline)
uv venv /tmp/ck && uv pip install --python /tmp/ck/bin/python checkov && /tmp/ck/bin/checkov

# Trivy from its official image
docker run --rm -v "$PWD:/src" aquasec/trivy:latest config /src --severity HIGH,CRITICAL --ignorefile /src/.trivyignore.yaml --skip-dirs /src/frontend/node_modules
docker run --rm -v "$PWD:/src" aquasec/trivy:latest fs /src --scanners secret --skip-files /src/.env
```

Two Checkov traps: it loads only the `.checkov.yaml` in the current directory, and with several directories in the configuration it writes a baseline in each, which is why the configuration uses a single directory.
