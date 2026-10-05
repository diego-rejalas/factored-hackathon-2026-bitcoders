# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] - 2026-10-05

First submitted version for the Factored AI & Data Hackathon 2026. Everything below the dated entries of this release was developed before it and is listed as it was recorded.

### Added
- Production deployment on GCP from the GitHub workflow, a deployment runbook (`docs/DEPLOY.md`) and end-to-end checks against the load balancer (11 of 11 scenarios).
- Documentation in English: the root and `docs/` READMEs, the per-folder READMEs, and three diagrams (agent flow, data pipeline flow, GCP architecture).
- A dark theme and a redesigned header for the specialist console, Spanish names for states, intents and trace steps, and metrics that read as a product working.
- The Factored logo as the brand mark, a language toggle and a scenario dropdown on the login, and the login language carried into the chat.
- A check that replaces a model draft showing an internal state name with the fixed template, and a pitch plan (`docs/PITCH_VIDEO.md`).

### Fixed
- Metric bars never rendered (an inline span ignored its size), the history sidebar marked two rows as selected, and the sidebar avatar showed a question mark when the customer's name was unknown.
- The agent's default model in Terraform was not the one that was evaluated.


### Added
- **ML components with held-out evaluation (`ml/eval/`, `spec/ML_FINDINGS.md` §12)**:
  - Team-generated retained sets (seeded, reproducible, no PII, fraud columns stripped and asserted absent): `intent_set.jsonl` (840 messages, 60 per intent×language cell plus 120 adversaries — prompt injection, real ambiguity, typos, dispute-vocabulary traps; stratified dev/test) and `dispute_set.jsonl` (399 claims with controlled noise over a transaction pool matching the documented marginals, label = original `transaction_id`, 40 `unrelated` cases for the correct "no match" rate, **customer-disjoint train/test split**).
  - Evaluation harnesses: `eval_intent.py` (baseline vs structured-output LLM with confidence, temperature 0, 3-run variability, ECE, asymmetric-cost abstention threshold calibrated on dev only, latency/tokens and provider/configured cost p50/p95, failures exported) and `eval_ranker.py` (deterministic `narrow_candidates` baseline vs interpretable weighted ranker vs light GBM trained on train; top-1/top-3 by noise type and currency, correct-empty and false-empty rates, and the integration-faithful "reorder the baseline pool" view).
  - Component A integration (`agent/app/intents.py`, `agent/app/graph.py`): `classify_detailed` returns `{intent, language, confidence, source, abstain}`; abstention below `INTENT_MIN_CONFIDENCE` (default 0.5) escalates in `decide` **by code rule, always after the deterministic fraud override**; classifier language replaces the substring detector with it as fallback; `trace_log` records component, prompt version, confidence, classifier latency and node latency; missing API key or invalid JSON falls back to the unchanged baseline behavior. Tests in `agent/tests/test_intents.py` (11, no LLM).
  - Component B integration (`agent/app/ranking.py`, stdlib): `rank_candidates(claim, transactions)` **only reorders** ambiguous pools (2+) so the likeliest option is proposed first — 60% top-1 vs 4% under date order on the held-out split; 0/1/2+ decisions, corroboration and the empty-pool path remain the deterministic policy (the ranker orders, it never authorizes). GBM variant documented but not integrated (scikit-learn dependency plus a worse standalone "no match" rate). Tests in `agent/tests/test_ranking.py` (7).
  - Reports with every failure included (`ml/eval/reports/`), per hackathon line-68 requirements; LLM candidate run is one command away once the team `OPENROUTER_API_KEY` is available.

### Changed
- **Specialist Admin Console (backend + agent + frontend)**:
  - `POST /admin/session` in `backend/` issuing `role=admin` JWTs from `ADMIN_USERS` bcrypt hashes (Secret Manager), with an in-memory per-IP+username rate limit (5 failures → 60s lockout) that fails closed on malformed hashes.
  - Admin disputes API: paginated inbox (`status=active` groups `escalated`+`in_progress`), case detail with structured handoff and conversation id, and audited `claim → in_progress` / `close → closed` transitions (non-empty note mandatory; close requires a resolution code; humans never set `auto_resolved`).
  - Outcome metrics from `app.disputes` with explicit numerators/denominators (safe automated resolution, escalations per handoff, human closures, language/reason breakdowns); rates are null ("not defined") without data, matching `spec/CRITERIA.md` wording.
  - Agent proxies (`/admin/*`, `/meta/data`) with fail-fast admin prechecks plus backend re-validation, and agent-owned endpoints `/admin/agent-metrics` and `/admin/conversations/{id}/trace` aggregating `agent.trace_log` (outcomes, containment proxy, p50/p95 per node, intents, languages, verify success).
  - `/admin` frontend: inbox with filters and customer context, handoff detail (verified facts, actions, evidence including unresolved candidate options, open questions), agent trace timeline, case audit timeline, guarded claim/close actions, and composed backend+agent metrics with data freshness (`ops.etl_runs`, snapshot edge).
- **Customer case history**: `GET /me/disputes` and per-case event timelines surfaced through the agent in a "Mis casos" drawer; cases verified by the safe path appear as `auto_resolved`.
- **Deterministic demo scenarios**: public `GET /meta/demo-scenarios` picks customers that guarantee the four demo paths (auto-resolved, ambiguous, fraud, threshold) using the same snapshot-edge anchor as agent searches, with es/pt hints and no fraud columns.
- **Enriched chat contract**: `POST /chat` now optionally returns `candidates`, `case`, `reason` and `language` for structured UI cards; existing consumers keep working.
- **Trust-first frontend redesign**: light banking theme with tokenized CSS, IBM Plex Sans/Mono via `next/font`, es/pt i18n, clickable candidate cards, verified-case and handoff cards, and WCAG 2.2 AA-audited responsive layouts (375/768/1440, `aria-live`, keyboard-operable scroll regions, `prefers-reduced-motion`).
- **Infra for the console**: `backend_app` read grants on `ops.etl_runs` (plus default privileges), `admin-users` manual secret in all GCP environments, and `GUARDRAIL_MAX_USD` propagated to the backend for scenario consistency.
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
- **Safe automated resolution is now a verified terminal state (`agent/app/graph.py`, `backend/app/routes/disputes.py`)**:
  - The agent's `verify` node closes the safe path through a guarded `POST /disputes/{id}/resolve` (`open → auto_resolved` with `no_charge_confirmed`/`reversal_confirmed`), re-reading the case instead of trusting the LLM; a resolve failure escalates rather than reporting success.
  - Guardrail escalations (fraud, threshold, posted-charge, unresolved ambiguity) now persist a dispute for the human inbox — linked to the verified candidate when one exists, unlinked (`transaction_id` nullable via migration) when none was identified; out-of-scope requests still create no case.
  - Per-turn graph state (candidates, case, handoff, clarify rounds) is reset between turns so a new dispute never reuses the previous case.
- **Dispute schema migration (`backend/app/db.py`)**: idempotent startup migration widens the `status` CHECK to include `in_progress`, makes `transaction_id` nullable for unlinked escalations, repairs legacy JSON-stringified handoff/event payloads into objects, and clears `resolved_at` on non-closed active cases.
- **Escalations no longer stamp `resolved_at`**: the timestamp is set only on real closure (`closed`/`auto_resolved`), so the admin UI shows "Pendiente" while a case awaits human action.
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

### Fixed
- **Double-encoded JSON evidence against real Postgres (`backend/app/db.py`)**: handoff and event payloads passed through the asyncpg jsonb codec as pre-serialized strings were stored as JSON strings (invisible to `->>`/`->` access); dicts are now passed directly, and the startup migration repairs affected rows.
- **Demo scenario hints in Portuguese** reused a Spanish date phrase ("del 2026-…"); es/pt example descriptions are now built per language.

### Removed
- **Standalone `dbt` Cloud Run Web Service**:
  - Removed HTTP FastAPI runner for dbt to eliminate unnecessary infrastructure and network streaming overhead.
  - Deleted legacy `infra/dbt/Dockerfile` build step from deployment workflows.

### Security
- **Role isolation between customer and admin surfaces**: customer tokens are rejected on `/admin/*` and admin tokens on customer/chat endpoints (both in the backend dependency and the agent fail-fast precheck); legacy customer JWTs without a `role` claim remain valid as `customer`.
- **Admin login hardening**: bcrypt comparison runs against a constant dummy hash for unknown usernames, malformed configured hashes fail closed (401, never a 500), and credentials live only in Secret Manager (`admin-users` manual secret, Terraform never overwrites operator-provided versions).
- **Hardened Permission & Leakage Boundaries**:
  - Ground-truth fraud labels (`is_fraud`) completely isolated from LLM context and tool access.
  - Banking access tokens and API secrets managed via Google Secret Manager.
  - Scrubbing of database and AWS credentials from ETL execution logs.
