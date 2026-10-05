# Path to production

[Index](README.md) · [Architecture](ARCHITECTURE.md) · [Security](SECURITY.md) · [Evaluation](EVALUATION.md) · [Criteria](CRITERIA.md) · [Deployment](DEPLOY.md)

*What it would take to bring this to a real bank, stated plainly. This is a prototype on synthetic data, not a production implementation. Each section separates what **exists today** from what is **missing**. Anything marked as a proposal is neither decided nor implemented.*

## Capacity and limits

**Today**
- **Cloud Run:** `backend` and `agent` run with 1 minimum instance in `prod` and 3 at most by default (`max_instances`), 1 CPU each. The frontend scales to zero.
- **Cloud SQL (`prod`):** `db-custom-2-7680` (2 CPUs, 7.5 GB), 50 GB, a single instance with no replica. Each service opens its own connection pool with asyncpg, at the library's default size.
- **Pipeline:** one `e2-standard-4` VM that processes the dataset's 23.5 million rows in a few minutes and stops at night. It is a closed snapshot, so there is no continuous load to size for.
- **Language model:** one classification call per message and one drafting call per resolved case. With `claude-haiku-4.5`, a call measured p50 1.2 s and p95 1.7 s, and 0.0005 USD per case ([Evaluation](EVALUATION.md)).

**Missing**
- **A load test.** Nobody measured how many simultaneous customers anything supports. The evaluation ran at concurrency 4 locally and says nothing about Cloud Run.
- **Sizing the connections.** With 3 instances per service and the default pool size, the database could run out of connections before Cloud Run runs out of instances.
- **A rate limit for the model.** A burst of messages becomes a burst of paid calls to a third party. Today only Cloud Armor limits by IP.
- **Database high availability.** A single instance with no replica is a single point of failure.

## Monitoring

**Today**
- Every request carries `X-Request-ID` and is logged as JSON, which Cloud Logging collects.
- `agent.trace_log` stores each agent step with its result and latency, with no customer text. `GET /admin/agent-metrics` and the console aggregate outcomes, containment, p50 and p95 latency, intents, languages and the verification result.
- `ops.etl_runs` records each pipeline run and `GET /meta/data` exposes it. The console shows freshness.
- `GET /ready` checks the database.

**Missing**
- **Alerts.** Nothing warns if the agent fails, if latency rises or if the pipeline did not run. There is also no budget with a cost alert (it is in the pending list of `infra/gcp/README.md`). No alert, dashboard or uptime check is defined in Terraform.
- **Availability probes and service objectives** (for example, a percentage of responses without `unavailable`).
- **Quality tracking in production.** The evaluation is offline. In production it would take sampling real conversations, measuring how many are escalated or abandoned, and reviewing the rejections of the model-draft checks (`llm_rejected_*` in the trace).
- **An immutable audit log** of the specialist's actions. Today a case's events only grow, but they live in the same database as the application.

## Access controls

**Today** (the detail is in [Security](SECURITY.md))
- Session with a signed JWT, with an expiry and a role. Identity always comes from the token, and every query is filtered by the customer.
- The backend is private, there is one database role per service, Cloud Armor is in front, and deployment uses no stored keys.

**Missing**
- **Real identity.** The chat accepts a customer and an ID number. A bank would need an identity provider with a second factor. The specialist's access is a user and a password in a manually loaded secret, with an attempt limit per process (not shared across instances).
- **Non-root containers** in `backend`, `agent` and `frontend`, and base images with vulnerabilities that have no published patch.
- **Human approval of the deployment to `prod`.** The GitHub `prod` environment has no required reviewers.
- **Secret rotation** (the session key, the model keys and the data-source keys) and separation of duties between whoever deploys and whoever applies permissions.

## Data retention

**Today no policy is applied.** What is stored and where:

| Data | Where | Contains customer text | Retention today |
|---|---|---|---|
| Conversations (what the customer wrote and what they were answered) | `agent.conversation_messages` | **Yes** | None: kept forever |
| Cases, events and handoffs | `app.disputes` and `app.dispute_events` | Yes, the message trimmed to 300 characters inside the handoff | None |
| Trace of agent steps | `agent.trace_log` | **No**, by design | None |
| Application logs | Cloud Logging | They do not include chat text | The service default |
| Pipeline data (bronze and silver) | Cloud Storage, Parquet | Synthetic | Moved to cheaper storage over time, never deleted |
| Database backups | Cloud SQL, with point-in-time recovery in `prod` | All of the above | The service default |

**Proposal, not decided** (the bank sets it, not the team): conversations for a short, bounded period with automatic deletion; cases and handoffs for the period that complaint regulation requires; and a mechanism to honor deletion on the customer's request. Any of the three needs a scheduled job that does not exist today. Database backups keep deleted data until they expire.

**Data that leaves the system.** With a model key, the customer's message and the transaction facts travel to OpenRouter and the model provider. In a real bank that would require a data-processing agreement, an agreed region and, probably, masking identifiers before sending. Today the agent also works without a model.

## Separating the application database from the pipeline's

**Today** everything lives in one instance and one database (`data`): the pipeline publishes `gold`, the backend writes `app` and the agent writes `agent`. There is one role per service and each sees only its own.

**Why separate them.** The pipeline rewrites all of `gold` on every run. A heavy load or an error there shares CPU, connections and backups with the customers' writes, and an incident in one forces a restore of the other. **Proposal:** a transactional database for `app` and `agent` (with a replica) and a separate query database for `gold`, which the pipeline publishes to and the backend reads from. The cost is one more instance and one more place to configure network and roles.

## Deployment and recovery

**Today:** everything is Terraform and the CI builds and scans the images. A person runs the `prod` applies, following [Deployment](DEPLOY.md). The database has point-in-time recovery in `prod`.

**Missing:** gradual rollout with rollback (today it is apply and wait), a **tested restore** (recovery was configured but not rehearsed), and a plan for when the model provider is down for more than a few minutes. The agent already falls back to fixed text and does not break, but quality drops: see 82% against 99% in Portuguese in the [Evaluation](EVALUATION.md).

## What would come first

1. Real identity with a second factor, and non-root containers.
2. Alerts, probes and a budget with a warning.
3. A retention policy agreed with the bank, and the job that applies it.
4. A load test and connection sizing.
5. Separating the application database from the pipeline's.
6. A review of real conversations and of the model's performance, before widening the scope to other flows.
