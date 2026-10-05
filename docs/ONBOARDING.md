# Team onboarding: access to GCP and the data

[Index](README.md) · [Architecture](ARCHITECTURE.md) · [Deployment](DEPLOY.md)

> **Project:** `bitcoders-factored-hackathon` · **Region:** `us-east4` · **Environment:** `prod` (`dev` and `qa` follow the same naming scheme: `factored-<environment>`).
>
> The scripts in `infra/gcp/scripts/` read `ENVIRONMENT=dev|qa|prod` (default `dev`). For `prod`, put it in front: `ENVIRONMENT=prod ./infra/gcp/scripts/...`.

How to authenticate and reach the PostgreSQL database, the lakehouse in Cloud Storage and the Cloud Run services. The project owner grants access (`infra/gcp/scripts/grant_access.sh`).

---

## 1. Prerequisites on your computer

Install these basic tools (if you do not have them yet):
1. **Google Cloud CLI (`gcloud`):** [installation instructions](https://cloud.google.com/sdk/docs/install).
2. **A database client:** [DBeaver](https://dbeaver.io/) (recommended), DataGrip, pgAdmin or `psql`.
3. **Cloud SQL Auth Proxy** (only for `dev`; in `prod` the database is private):
   * **macOS (Homebrew):** `brew install cloud-sql-proxy`
   * **Linux:**
     ```bash
     curl -o cloud-sql-proxy https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.14.0/cloud-sql-proxy.linux.amd64
     chmod +x cloud-sql-proxy
     sudo mv cloud-sql-proxy /usr/local/bin/
     ```
   * **Windows:** download the executable from [Google Cloud SQL Proxy](https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.14.0/cloud-sql-proxy.x64.exe).

---

## 2. Authenticate with Google Cloud

Open a terminal and sign in with the Google account that was given access:

```bash
# 1. Sign in to GCP
gcloud auth login

# 2. Enable local application credentials (needed to query the lakehouse and Storage)
gcloud auth application-default login

# 3. Set the active project
gcloud config set project bitcoders-factored-hackathon
```

---

## 3. The database (`data`)

In `prod` Cloud SQL has a **private IP only**. There is no public IP and no authorized-networks list, so the Auth Proxy from your computer **cannot reach it**. You get in through the Airflow VM, which is inside the network and is reached through IAP (it has no external IP).

```bash
# 1. Start the VM (it stops by itself at 03:00) and wait about a minute
ENVIRONMENT=prod ./infra/gcp/scripts/airflow_vm.sh start

# 2. Run a query from the scheduler container, which already has the pipeline's credentials
gcloud compute ssh factored-prod-airflow --zone us-east4-a --project bitcoders-factored-hackathon \
    --tunnel-through-iap --command "sudo docker exec airflow-scheduler-1 python -c \"import os,psycopg2; c=psycopg2.connect(host=os.environ['PG_HOST'],dbname=os.environ['PG_DATABASE'],user=os.environ['PG_USER'],password=os.environ['PG_PASSWORD'],sslmode='require'); cur=c.cursor(); cur.execute('select count(*) from gold.transactions'); print(cur.fetchone())\""

# 3. When you are done
ENVIRONMENT=prod ./infra/gcp/scripts/airflow_vm.sh stop
```

That account is the pipeline's (it writes `gold`), so use it only to query. A graphical client (DBeaver, DataGrip) cannot reach the database in `prod`. To explore data without touching the VM, use the lakehouse (section 4).

If the project owner gave you access to `dev`, that database and its scripts (`manage_db.sh`) follow their own configuration. Ask the owner how to connect.

#### Schemas
* `gold.*`: business tables for the service (`customers`, `products`, `transactions`, `complaints`, `call_center_interactions`).
* `ops.etl_runs`: history of pipeline runs.
* `agent.trace_log` and `agent.conversation_messages`: the agent's trace (with no customer text) and the conversation history.
* `app.*`: dispute cases and their events.

---

## 4. The lakehouse (Cloud Storage, Parquet)

**Bronze** (raw data) and **Silver** (standardized and typed) are stored as Parquet with ZSTD compression in `gs://factored-prod-lakehouse-bitcoders-factored-hackathon` (`bronze/<table>/`, `silver/<table>/` and `docs/`). It needs neither the VM nor the database. You read it from your machine with DuckDB.

```python
import duckdb

con = duckdb.connect()
con.execute("INSTALL httpfs; LOAD httpfs;")
con.execute("CREATE SECRET (TYPE GCS, PROVIDER CREDENTIAL_CHAIN);")

bucket = "gs://factored-prod-lakehouse-bitcoders-factored-hackathon"
print(con.execute(f"SELECT * FROM '{bucket}/silver/customers/customers.parquet' LIMIT 5").df())
print(con.execute(f"SELECT * FROM read_parquet('{bucket}/silver/transactions/**/*.parquet') LIMIT 5").df())
```

---

## 5. The services (Cloud Run)

The UI and the agent are served through the load balancer (with Cloud Armor in front). The backend is **private**, and only the agent calls it, with its own identity.

```bash
cd infra/gcp/envs/prod && terraform output edge_url      # https://<domain>/  and  /agent/*
gcloud beta run services logs tail factored-prod-agent --region us-east4 --project bitcoders-factored-hackathon
gcloud beta run services logs tail factored-prod-backend --region us-east4 --project bitcoders-factored-hackathon
```

| Service | How to reach it | What it is |
|---|---|---|
| `factored-prod-frontend` | `/` on the load balancer | Customer chat and the `/admin` console |
| `factored-prod-agent` | `/agent/*` on the load balancer (`POST /agent/chat`) | Agent and guardrail |
| `factored-prod-backend` | Private (identity token) | Banking tools API |

---

## 6. FAQ and troubleshooting

* **Error: `connection refused` or a timeout when connecting to PostgreSQL:**
  * In `dev`, make sure the Cloud SQL Proxy is running in a terminal.
  * In `dev`, check whether the database is hibernating (`./infra/gcp/scripts/manage_db.sh status`; if it shows `NEVER`, run `resume`). In `prod` the proxy cannot reach it: see section 3.
* **Error: `password authentication failed for user`:**
  * Check that you are entering the exact user and password you were given when your access was set up.
* **Error: `Bucket not found` when querying GCS:**
  * Check that you ran `gcloud auth application-default login`, so that DuckDB and the client libraries pick up your local credentials.
