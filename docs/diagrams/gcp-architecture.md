# Architecture on Google Cloud and Cloudflare (prod, us-east4)

![Architecture on Google Cloud and Cloudflare](./gcp-architecture.png)

Generated with the `diagrams` library (mingrammer): `python gcp_architecture.py` (needs `pip install diagrams` and Graphviz). Output: `gcp-architecture.png` and `.svg`. The script embeds the icons in the SVG so that it renders anywhere.

## Legend
| No. | Component | What it is |
|---|---|---|
| 1 | Artifact Registry | Images versioned per commit |
| 2 | Secret Manager | Keys, JWT and passwords, with one access per service |
| 3 | Cloud Storage | Lakehouse: bronze and silver as Parquet |
| 4 | Cloud Logging and Monitoring | Logs and default metrics of the VM and the database. No alerts are defined |
| 5 | IAM | One service account per component |
| 6 | Cloud IAP + OS Login | The only access to the VM, with no public IP |
| 7 | frontend | The web UI (Next.js) |
| 8 | agent | The dispute policy (LangGraph) |
| 9 | backend | A FastAPI API, read-only on gold |
| 10 | etl Job | The same pipeline, launched on demand |
| 11 | Airflow 3 + dbt | An e2-standard-4 VM, a 7-task DAG, stopped at 03:00 |
| 12 | Cloud NAT | The VM's only way out to the internet |
| 13 | Cloud SQL | PostgreSQL 18, private IP, SSL. Only gold is published. Roles: `app` (pipeline), `backend_app` (reads gold), `agent_app` (audit) |
| 14 | Cloud Armor | SQL injection, XSS and Log4j rules, and a per-IP limit |
| 15 | Global ALB | The only public entry: `/` to the frontend and `/agent/*` to the agent. Direct access is closed. The backend accepts only the agent's account |
| 16 | Cloudflare DNS | The app's name, an A record to the ALB's address, with the proxy off so that Google can issue the certificate |
| 17 | Cloudflare Pages | The landing, a static export of `site/`, with the pitch slides and the link to the app |
| 18 | Cloudflare R2 | The pitch video. Pages ignores range requests and a bucket answers them, so the video can be skipped through |

## Limits
- Cloudflare is outside Google Cloud and has its own Terraform, `infra/cloudflare`, with its state in the same bucket under the prefix `cloudflare`. The landing's files are deployed with `wrangler`, not planned by Terraform.
- The bucket's public address is an `r2.dev` name: meant for development and rate-limited by Cloudflare. Enough for the evaluation; a custom domain is the production answer.
- Cloud Run does not literally live inside the subnet: it connects with Direct VPC egress, and it is drawn inside to show that relationship.
- The browser calls the agent on the ALB's own origin (`/agent/*`), which is why there is no direct frontend to agent arrow.
- A single environment (prod). OpenRouter uses a generic icon (there is no official one).
- The labels of some arrows may sit close to other elements: Graphviz lays the diagram out on its own.
