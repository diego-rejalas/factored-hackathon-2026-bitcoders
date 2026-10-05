# LATAM Bank dispute assistant

<p align="center">
  <img src="https://skillicons.dev/icons?i=python,fastapi,nextjs,ts,postgres,duckdb,airflow,docker,terraform,gcp,githubactions&perline=11" alt="Python, FastAPI, Next.js, TypeScript, PostgreSQL, DuckDB, Airflow, Docker, Terraform, Google Cloud, GitHub Actions" />
</p>

A banking customer-service assistant that resolves safe transaction disputes on its own and hands everything else to a person with the case already prepared. Built for the **Factored AI & Data Hackathon 2026** by team *bitcoders*, on the synthetic LATAM Bank dataset.

- **The customer** describes a charge they do not recognize, in Spanish or Portuguese. The agent finds the transaction, applies a deterministic policy and answers with verified facts.
- **It resolves alone** what is clear and under USD 500 (a declined or reversed transaction). **It escalates** an approved charge, suspected fraud, a high amount or an ambiguous case, with a structured handoff.
- **A specialist** picks up escalated cases in the `/admin` console, with the evidence, the audit trail and the agent's trace.
- Policy, permissions and identity live in code. The language model is optional and only drafts the reply.

## How it works

**The agent.** Policy is code and the model only helps: it classifies, drafts the reply and takes a second look for fraud, but it never decides.

![Agent flow](docs/diagrams/agent-flow.svg)

**The data pipeline.** From the organizer's S3 bucket to the `gold` tables the backend reads, with a test gate before anything is published.

![Pipeline flow](docs/diagrams/pipeline-flow.svg)

**The deployment.** Everything runs on Google Cloud and is defined in Terraform.

![GCP architecture](docs/diagrams/gcp-architecture.svg)

## Documentation

Everything is in [`docs/`](docs/README.md).

| | |
|---|---|
| [Workflow](docs/WORKFLOW.md) | What it resolves alone, when it escalates and what the person receives |
| [Architecture](docs/ARCHITECTURE.md) | How it is built and deployed on GCP |
| [Data](docs/DATA.md) | What the dataset says and its limits |
| [API](docs/API.md) | The contract between the UI, the agent and the backend |
| [Evaluation](docs/EVALUATION.md) | How the system was measured, and the results |
| [ML components](docs/ML_FINDINGS.md) | Intent classification and transaction ranking against their baselines (`ml/eval/`) |
| [Security](docs/SECURITY.md) | Controls and the Checkov and Trivy findings |
| [Path to production](docs/PRODUCTION.md) | What exists and what is missing for real production |
| [Deployment](docs/DEPLOY.md) | Deploying to production, step by step |
| [Criteria](docs/CRITERIA.md) | What the challenge asks for and what is left |
| [Local development](docs/LOCAL_DEV.md) | Running it on your machine |
| [Onboarding](docs/ONBOARDING.md) | Reaching the GCP database and data (team) |

The challenge statement is in [`docs/challenge/`](docs/challenge/) (organizer material, not edited).

## Repository layout

| Folder | Contents |
|---|---|
| `backend/` | Tool layer: FastAPI, ownership-based permissions, cases and the specialist console |
| `agent/` | Conversational agent: LangGraph, deterministic guardrail, traces and history |
| `frontend/` | Next.js: the customer chat and the `/admin` console |
| `data/` | Pipeline: stages in `pipeline/` and the dbt project in `dbt/` |
| `ml/eval/` | Held-out sets and evaluation of the ML components (intent and transaction ranking) |
| `agent/eval/` | End-to-end evaluation of the system and of the intent classifier |
| `infra/gcp/` | Terraform per environment (`dev`, `qa`, `prod`) and modules |
| `infra/gcp/airflow/` | The Airflow image and DAG that run on the VM |
| `docs/` | Documentation and diagrams |

## Tests

```bash
cd backend  && python -m pytest    # tool layer (the database is mocked; with PG_TEST_HOST it also runs against PostgreSQL)
cd agent    && python -m pytest    # agent and guardrail (backend and model mocked)
cd frontend && pnpm build          # UI build and type check
```

To run everything locally with sample data, see [`docs/LOCAL_DEV.md`](docs/LOCAL_DEV.md).
