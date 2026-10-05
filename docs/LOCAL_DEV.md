# Running everything locally

[Index](README.md) · [Workflow](WORKFLOW.md) · [Architecture](ARCHITECTURE.md) · [Data](DATA.md) · [API](API.md)

A database with sample data, the backend and the agent in Docker, and the frontend on your machine (it reloads on edit). It needs no cloud, no keys and not the real database. Verified on 2026-10-04 in a real browser (customer and specialist console) and with the 11 scenarios of `infra/gcp/scripts/e2e.py`.

## 1. Backend, agent and database

```bash
docker compose -f docker-compose.dev.yml up --build
```

| Service | Address | What it is |
|---|---|---|
| backend | http://localhost:8000/docs | API (`/v1` for the web, the root for the agent) |
| agent | http://localhost:8001/health | the assistant |
| database | `localhost:5433`, user `postgres`, password `dev`, database `data` | PostgreSQL 18 |

The database is created the first time from `backend/dev/gold_fixture.sql`. `docker compose -f docker-compose.dev.yml down -v` drops it, and the next start begins from scratch (created cases are lost).

**The data is not the organizer's.** It is three invented customers with the same `customer_id`, documents and amounts that `e2e.py` uses, so every policy path can be tested.

## 2. Frontend

```bash
cd frontend
cp -n .env.example .env.local        # NEXT_PUBLIC_AGENT_URL=http://localhost:8001
PNPM_MANAGE_PACKAGE_MANAGER_VERSIONS=false pnpm install
PNPM_MANAGE_PACKAGE_MANAGER_VERSIONS=false pnpm dev      # or: pnpm build && pnpm start
```

Open http://localhost:3000. It must be port **3000**: the agent accepts only that origin (`CORS_ALLOWED_ORIGINS`). If Next picks another port because 3000 is busy, the browser blocks the calls.

`PNPM_MANAGE_PACKAGE_MANAGER_VERSIONS=false` stops pnpm from trying to download its own version (`packageManager` pins 11.1.3), which fails on some networks.

> **To see the "Mis casos" (My cases) panel, use the built version** (`pnpm build && pnpm start`). In development mode React mounts every component twice and the panel's `<dialog>` closes immediately. This is an artifact of `pnpm dev`, not of the product.

## 3. What to try

**Customer (`/`).** In the form, "Escenarios para demostración" (demo scenarios) fills in `customer_id` and document and suggests the message. By hand:

| Customer | customer_id | Document | Message | Result |
|---|---|---|---|---|
| Ana | `CLI-00MT1OY089RA` | `17521506` | `No reconozco la transferencia de 4189.18 dólares` | **Escalates** (over USD 500), with its case |
| Ana | | | `No reconozco la transferencia de 6783.64 dólares` | **Escalates** (already approved charge) |
| Bruno | `CLI-0064RNKCVQCN` | `0863503738` | `No reconozco el cobro de 256.10` | **Resolves** (declined; states the reason, code 51) |
| Carla | `CLI-00232W4ZDQPP` | `57064351` | `No reconozco el cobro de 389.87` | **Resolves** (reversed) |

With any of them: `Me robaron la tarjeta, no fui yo` escalates for suspected fraud. **Mis casos** shows the customer's cases, and the sidebar (**Recientes**) shows earlier conversations, which are stored in the local database and can be reopened.

**Specialist (`/admin`).** User `ops-demo`, password `Admin-Local-2026` (local only). The inbox shows what was escalated. You can **take** a case and **close** it (note and resolution required), and see the **metrics**. First escalate a case as a customer so the inbox has something in it.

## 4. Trying the backend `/v1` on its own

Username and password (the demo accounts): `ana.demo`, `bruno.demo` and `carla.demo`, password `Demo-Local-2026`.

```bash
curl -s localhost:8000/v1/auth/demo-accounts
TOKEN=$(curl -s -X POST localhost:8000/v1/auth/login -H 'content-type: application/json' \
  -d '{"username":"ana.demo","password":"Demo-Local-2026"}' | python3 -c 'import json,sys; print(json.load(sys.stdin)["session_token"])')
curl -s localhost:8000/v1/me/summary  -H "Authorization: Bearer $TOKEN"
curl -s localhost:8000/v1/me/products -H "Authorization: Bearer $TOKEN"
curl -s "localhost:8000/v1/me/transactions?limit=3" -H "Authorization: Bearer $TOKEN"   # next_cursor for the next page
curl -s localhost:8000/v1/disputes    -H "Authorization: Bearer $TOKEN"
```

All the agent scenarios at once: `AGENT_URL=http://localhost:8001 python3 infra/gcp/scripts/e2e.py`.

## 5. With a real LLM

Without a key the agent answers with its deterministic text. To have it draft with the model:

```bash
OPENROUTER_API_KEY=sk-or-... docker compose -f docker-compose.dev.yml up --build
```

The model is set by `OPENROUTER_MODEL` (default `anthropic/claude-haiku-4.5`, the one the [evaluation](EVALUATION.md) measured). If you keep the key in `agent/.env`, add `--env-file agent/.env` to the command. Recreating the containers without it silently turns the model off.

## Tests

```bash
# Backend: routes with an in-memory store, and the real SQL (including the console's) if there is a PostgreSQL
cd backend && PG_TEST_HOST=localhost PG_TEST_PORT=5433 PG_TEST_USER=postgres PG_TEST_PASSWORD=dev python -m pytest
cd agent && python -m pytest
```

The first needs the database from step 1 above. Without `PG_TEST_HOST` the real SQL is skipped.
