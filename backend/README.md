# backend/: mock banking service (tool layer)

Vertical 3 of `../docs/ARCHITECTURE.md`. A separate FastAPI service (Cloud Run). It is the "service/tool layer" the challenge requires for permission enforcement: the policy lives here, not in the LLM's prompt. **Implemented** (workflow option A: transaction disputes, see `../docs/WORKFLOW.md`).

## Contract (OpenAPI at `/docs`)

Two surfaces on the same service. The **root** is the one the agent uses (the browser does not call the backend: it goes to the agent). **`/v1`** is a surface designed for a web application, which the current UI does not use. The design and decisions are in `../docs/API.md`, and **the contract (routes, states, errors, security) is in `../docs/API.md`**, whose OpenAPI document is stored in `tests/contract/openapi.json`. A test fails if the code drifts from it.

**Root (the one the agent uses)**

| Endpoint | Auth | What it does |
|---|---|---|
| `POST /session` | none | Test login: validates `customer_id` + `document_number` against `gold.customers` and issues an HS256 JWT with `role=customer` (exp ~2h, `SESSION_TTL_MINUTES`). A sandbox session, with no real IdP behind it. |
| `POST /admin/session` | none | Specialist login with `ADMIN_USERS` (bcrypt hashes in Secret Manager). It issues a `role=admin` JWT (`ADMIN_TTL_MINUTES`, default 8h). Five failures per IP+user lock it for 60s in memory. The limit is per process and only suitable for the demo. |
| `GET /health` | none | Liveness for the Cloud Run healthcheck. |
| `GET /me` | Bearer | Minimal profile (name, country). It never exposes income, credit_score or document_number. |
| `GET /me/transactions?status=&merchant=&days=&limit=` | Bearer | Own transactions. It always filters by the token's `customer_id` (the query does not accept customer_id). `amount_usd_effective` = `coalesce(amount_usd, amount if currency='USD')`, because 57% of `amount_usd` is null on USD rows (see `../docs/DATA.md`). `days` anchors to the snapshot edge (the dataset's last transaction), not to `now()`. |
| `GET /me/transactions/{id}` | Bearer | Detail with an ownership check, and 404 if it is someone else's. |
| `GET /me/disputes` | Bearer | A minimal list of own cases, ordered by creation descending. |
| `POST /disputes` | Bearer | Creates an `open` case in `app.disputes`. It validates ownership of the transaction first, and 404 if it is someone else's. Evidence: a snapshot of the transaction. |
| `GET /disputes/{case_id}` | Bearer | State + evidence + events (used by the agent's `verify` node). 404 if the case is not the token's. |
| `POST /disputes/{case_id}/escalate` | Bearer | Marks `escalated` and stores the structured handoff in the evidence + an append-only event. |
| `POST /disputes/{case_id}/resolve` | Bearer | Marks `auto_resolved` after the agent's verification. It stores `no_charge_confirmed` or `reversal_confirmed` and the system event. It cannot be applied to escalated cases. |
| `GET /admin/disputes?status=&customer_id=&limit=&offset=` | Admin | A paginated inbox with customer, language and handoff reason. `status=active` includes `escalated` + `in_progress`. |
| `GET /admin/disputes/{case_id}` | Admin | Detail, structured handoff, conversation_id and audited events. |
| `POST /admin/disputes/{case_id}/transition` | Admin | `claim`: `open\|escalated → in_progress`. `close`: `in_progress → closed` with a required resolution and note. Each transition adds an event with the admin and the note. A human never sets `auto_resolved`. |
| `GET /admin/metrics?window=<hours>` | Admin | Totals by state, safe automatic resolution with its denominator, escalations, human closures, and handoff language and reason. With no cases, the rate is `null` (not defined). |
| `GET /meta/data` | Admin | `gold.*` counts, the snapshot's time edge and the last run of `ops.etl_runs`. |
| `GET /meta/demo-scenarios` | none | A public selector for the demo: only the scenario, customer_id, document_number, first_name and es/pt hints. It never exposes fraud fields. Cached for 5 minutes. |

Guarantees:
- **Identity:** it always derives from the validated JWT (`get_current_customer`). The LLM and the chat cannot propose a `customer_id`. A case with no linked transaction represents an escalation that is not yet identified, and it does not enable reads of third parties.
- **Roles:** admin endpoints require `role=admin`, and customer tokens keep `sub=customer_id`. The admin login is a sandbox, not an IdP, and `ADMIN_USERS` must live in Secret Manager.
- **`gold.*` is read-only** for this service. The `app.*` tables are created by **versioned SQL migrations** (`app/migrations`), applied at startup under a lock, each in its own transaction.
- Migration `0005` (the CHECK on `app.disputes.status` allows `in_progress`, and the transaction is optional) and `0004`/`0005` repair handoffs and JSON events that earlier versions stored as text.
- **One case per (customer, transaction)**, guaranteed by a unique index (migration `0003`): reporting the same transaction again returns that case, and two simultaneous requests create only one. A case without a transaction is never a duplicate of another.
- `backend_app` needs `USAGE` + `SELECT` on `ops.etl_runs` for freshness. `roles.sql` grants that access and default privileges without opening `agent.*`.

**`/v1`**: the surface designed for a web application (the current UI does not use it, because it calls the agent. It is kept and covered by tests and by the contract):

| Endpoint | Auth | What it does |
|---|---|---|
| `POST /v1/auth/login` | none | Username and password (argon2id). Five failures lock the account for 15 minutes (429 + `Retry-After`). The same response if the user does not exist. |
| `GET /v1/auth/demo-accounts` | none | Demo accounts and their shared password. 404 unless `DEMO_ACCOUNTS_ENABLED=true`. |
| `GET /v1/me`, `/v1/me/summary`, `/v1/me/products` and `/{id}` | Bearer | Profile, summary (balances by currency, deposits and credit kept apart), products with the number masked (`****1234`). |
| `GET /v1/me/transactions` and `/{id}` | Bearer | History paginated by cursor (`?cursor=`), filters `product_id`, `status`, `merchant`, `from`, `to`. Each row carries `case_id`, `dispute_status` and `response_meaning` (the response code's reason, ISO 8583 standard: an assumption, since the organizer does not define it). |
| `GET /v1/disputes`, `/v1/disputes/{id}` and `POST /v1/disputes…` | Bearer | The same dispute routes as the root. |

Every endpoint with a session validates the role: an `admin` token does not open customer routes and the reverse.
- **`is_fraud` and `fraud_score` do not exist in `gold.transactions`** and do not appear in any SELECT (a pipeline invariant).
- No money moves: disputes only explain, document and escalate.

## Structure

- `app/main.py`: the FastAPI app, lifespan (pool, migrations, demo accounts), `/health`, `/ready`.
- `app/auth.py`: `POST /session` (the agent's), HS256 JWT issuing and validation, the `get_current_customer` dependency.
- `app/passwords.py`, `app/demo.py`, `app/migrate.py`, `app/migrations/*.sql`, `app/observability.py`, `app/response_codes.py`: argon2id hashing, demo accounts, migrations, `X-Request-ID` and JSON logs, and the meaning of the response codes.
- `app/db.py`: `BankStore` (asyncpg, explicit SQL, no ORM).
- `app/routes/customers.py` (root, agent and web), `app/routes/disputes.py` (shared by the root and `/v1`), `app/routes/v1.py`, `app/routes/admin_disputes.py`, `app/routes/meta.py`: deterministic endpoints.
- `tests/`: routes with an in-memory store. `test_store_postgres.py` runs the **real SQL** against PostgreSQL (it needs `PG_TEST_HOST`, and CI starts one). `tests/contract/openapi.json` + `test_openapi_contract.py` are the contract the code cannot stop honoring without a test failing.

## Running and testing

```bash
cp .env.example .env            # PG_* pointing at the local Postgres (`docker-compose.dev.yml`) (database `data`) + SESSION_JWT_SECRET
set -a; . ./.env; set +a
uvicorn app.main:app --reload   # from this folder; http://localhost:8000/docs
```

Tests:

```bash
python -m pytest                # from backend/, with pytest + httpx installed. Without PG_TEST_HOST the real SQL is skipped
PG_TEST_HOST=localhost PG_TEST_PORT=5432 PG_TEST_USER=postgres PG_TEST_PASSWORD=... python -m pytest   # everything
```

## Admin access (sandbox)

Generate each hash outside the repo and store the full string `user:hash[,user:hash...]` in `ADMIN_USERS` (in GCP, Secret Manager, never in Git). An example for generating a bcrypt hash:

```bash
python -c "import bcrypt; print(bcrypt.hashpw(b'CHANGE_THIS_PASSWORD', bcrypt.gensalt()).decode())"
```

The user types the original password, and only the hash is stored. In GCP, `admin-users` is a separate manual secret per environment (`factored-dev-admin-users`, `factored-qa-admin-users`, `factored-prod-admin-users`). Replace the `NOT_SET` placeholder with a new version before enabling access. Do not use a real production password: this prototype has no IdP and no distributed rate limit.

Deployment: Cloud Run, see `../infra/gcp/envs/`.
