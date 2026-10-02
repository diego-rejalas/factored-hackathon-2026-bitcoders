# backend/ — mock banking service (tool layer)

Vertical 3 de `../spec/ARCHITECTURE.md`. Servicio FastAPI separado en Railway. Es el "service/tool layer" que el reto exige para enforced de permisos — la política vive acá, no en el prompt del LLM. **Implementado** (workflow Opción A: disputas de transacciones, ver `../spec/WORKFLOW_DECISION.md`).

## Contrato (OpenAPI en `/docs`)

FastAPI expone el esquema completo en `/openapi.json` y la UI interactiva en `/docs`. Resumen:

| Endpoint | Auth | Qué hace |
|---|---|---|
| `POST /session` | — | Login de prueba: valida `customer_id` + `document_number` contra `gold.customers` y emite JWT HS256 (exp ~2h, `SESSION_TTL_MINUTES`). Sesión sandbox, no hay IdP real detrás. |
| `GET /health` | — | Liveness para el healthcheck de Railway. |
| `GET /me` | Bearer | Perfil mínimo (nombre, país). Jamás expone income/credit_score/document_number. |
| `GET /me/transactions?status=&merchant=&days=&limit=` | Bearer | Movimientos propios; siempre filtra por el `customer_id` del token (el query no acepta customer_id). `amount_usd_effective` = `coalesce(amount_usd, amount si currency='USD')` — 57% de `amount_usd` es nulo en filas USD (ver `../spec/DATA_FINDINGS.md`). `days` ancla al borde del snapshot (última transacción del dataset), no a `now()`. |
| `GET /me/transactions/{id}` | Bearer | Detalle con verificación de titularidad → 404 si es ajena. |
| `POST /disputes` | Bearer | Crea caso `open` en `app.disputes`; valida titularidad de la transacción primero → 404 si es ajena. Evidencia: snapshot de la transacción. |
| `GET /disputes/{case_id}` | Bearer | Estado + evidencia + eventos (lo usa el nodo `verify` del agent). 404 si el caso no es del token. |
| `POST /disputes/{case_id}/escalate` | Bearer | Marca `escalated` y guarda el handoff estructurado en la evidencia + evento append-only. |

Garantías:
- **Identidad:** siempre deriva del JWT validado (`get_current_customer`); el LLM/chat no puede proponer `customer_id`.
- **`gold.*` es read-only** para este servicio; las tablas operacionales (`app.disputes`, `app.dispute_events`) se crean en startup con `CREATE TABLE IF NOT EXISTS` (documentado como limitación, no es una migración real).
- **`is_fraud`/`fraud_score` no existen en `gold.transactions`** y no aparecen en ningún SELECT (invariante del pipeline).
- Sin mover dinero: las disputas solo explican, documentan y escalan.

## Estructura

- `app/main.py` — app FastAPI, lifespan (pool + DDL), `/health`.
- `app/auth.py` — `POST /session`, emisión/validación JWT HS256, dependencia `get_current_customer`.
- `app/db.py` — `BankStore` (asyncpg, SQL explícito, sin ORM).
- `app/routes/customers.py`, `app/routes/disputes.py` — endpoints deterministas.
- `tests/` — suite DB-less (store fake en memoria).

## Ejecutar y probar

```bash
cp .env.example .env            # PG_* apuntando al Postgres de Railway (database `data`) + SESSION_JWT_SECRET
set -a; . ./.env; set +a
uvicorn app.main:app --reload   # desde esta carpeta; http://localhost:8000/docs
```

Tests (no requieren Postgres):

```bash
python -m pytest                # desde backend/, con pytest + httpx instalados
```

Despliegue: `../.railway/railway.ts` (servicio `backend`, Dockerfile propio, watchPatterns `backend/**`, healthcheck `/health`).
