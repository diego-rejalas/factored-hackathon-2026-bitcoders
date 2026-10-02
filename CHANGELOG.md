# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Data Lakehouse Preservation for Bronze & Silver (`infra/gcp/etl/`)**:
  - Implemented persistent export of raw `bronze.*` and typed `silver.*` datasets in compressed columnar Parquet format (ZSTD) to Google Cloud Storage (`gs://<lakehouse_bucket>/`).
  - Added configurable `LAKE_STORAGE_URI` supporting local offline directory exports (`./data/lake/`) and cloud buckets.
  - Mirrored date-based Hive partitioning (`year=YYYY/month=MM/day=DD/`) for transactional tables and digital events, with flat Parquet files for dimension tables.
- **Terraform Lakehouse Infrastructure (`infra/gcp/main.tf`, `infra/gcp/variables.tf`)**:
  - Declared `google_storage_bucket.lakehouse` with Standard storage class and 30-day Nearline transition lifecycle.
  - Granted `roles/storage.objectAdmin` to `etl-job` Service Account and injected bucket URI into Cloud Run Job environment.
  - Enabled `storage.googleapis.com` API and added `lakehouse_bucket` output.
- **Enterprise Architecture Assessment & TCO Scaling Specification (`spec/ENTERPRISE_ARCHITECTURE_EVALUATION.md`)**:
  - Created comprehensive architectural assessment evaluating enterprise viability (FinTech/Neobank vs. Tier-1 Corporate Bank).
  - Modeled granular TCO projections across 3 phases (MVP ~$34/mo, Scale-Up ~$820/mo, Tier-1 ~$17,000/mo) with unit economics per MAU and transaction.
  - Documented failure modes, regulatory compliance requirements (PCI-DSS, PII tokenization), and 3-phase migration roadmap.
- **Banking Backend Microservice (`backend/`)**:
  - FastAPI service providing authenticated REST endpoints for customer lookup, cards, transactions, and dispute creation.
  - Deterministic role-based permission enforcement outside LLM prompt context.
  - Database access layer connecting exclusively to `gold.*` schemas in PostgreSQL.
- **AI Agent & Guardrails (`agent/`)**:
  - LangGraph conversational orchestrator (`understand -> decide -> act -> verify -> escalate`).
  - Deterministic guardrail layer enforcing session verification, dispute threshold checks ($500), and policy gates before tool execution.
  - Structured handoff mechanism when cases require human intervention.
  - Comprehensive audit tracing writing execution steps and tool responses to PostgreSQL (`agent.trace_log`).
- **Responsive Chat Interface (`frontend/`)**:
  - Next.js 14 application with React, Tailwind CSS, and standalone output.
  - Multilingual support for Spanish and Portuguese.
  - Interactive dispute simulation flow with realtime message state and escalation banners.
- **Just-in-Time Database Hibernation Script (`infra/gcp/manage_db.sh`)**:
  - 1-click management to pause (`NEVER`), resume (`ALWAYS`), and inspect Cloud SQL state.
  - Reduces idle cloud spend from ~$0.51/day to ~$0.05/day by freezing compute and public IP charges.
- **CI/CD Automation (`.github/workflows/gcp-deploy.yml`)**:
  - Multi-image Docker build and Artifact Registry push.
  - Terraform plan on pull requests and automated apply/ETL triggering on dispatch.

### Changed
- **Ultra-Lightweight In-RAM Data Pipeline (`infra/gcp/etl/`)**:
  - Migrated ETL process to run entirely within ephemeral RAM using DuckDB and embedded `dbt-duckdb`.
  - Reads 23.5 million records across 13 datasets from AWS S3 via HTTPFS into `/tmp/latam.duckdb`.
  - Executes 18 dbt models (13 Silver views + 5 Gold tables) and enforces 121 automated quality tests locally before publishing.
  - Implemented atomic publication of only `gold.*` tables to Cloud SQL with primary keys and B-tree indexes.
  - Purges residual `bronze` and `silver` raw schemas from Cloud SQL, keeping PostgreSQL disk usage below 1 GB.
  - Reduced end-to-end execution time from 45+ minutes to ~2.5 minutes (~24x speedup).
- **Primary Cloud Infrastructure (`infra/gcp/`)**:
  - Shifted primary deployment from Railway to Google Cloud Platform (GCP).
  - Deployed Cloud Run services for `backend`, `agent`, and `frontend` configured with zero minimum instances for cost-efficiency.
  - Parameterized Cloud SQL activation policy via Terraform variable `db_activation_policy`.

### Removed
- **Standalone `dbt` Cloud Run Web Service**:
  - Removed HTTP FastAPI runner for dbt to eliminate unnecessary infrastructure and network streaming overhead.
  - Deleted legacy `infra/dbt/Dockerfile` build step from deployment workflows.

### Security
- **Hardened Permission & Leakage Boundaries**:
  - Ground-truth fraud labels (`is_fraud`) completely isolated from LLM context and tool access.
  - Banking access tokens and API secrets managed via Google Secret Manager.
  - Scrubbing of database and AWS credentials from ETL execution logs.
