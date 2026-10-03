# backend/ — mock banking service (tool layer)

Vertical 3 de `../spec/ARCHITECTURE.md`. Servicio FastAPI separado en Railway. Es el "service/tool layer" que el reto exige para enforced de permisos — la política vive acá, no en el prompt del LLM. **Implementado** (workflow Opción A: disputas de transacciones, ver `../spec/WORKFLOW_DECISION.md`).

## Contrato (OpenAPI en `/docs`)

Dos superficies sobre el mismo servicio. La **raíz** es la del agente (no cambia); **`/v1`** es la de la aplicación web, a la que llega por su servidor (BFF), nunca desde el navegador. Diseño y decisiones en `../spec/BACKEND_API.md`; **el contrato (rutas, estados, errores, seguridad) en `../spec/API_CONTRACT.md`**, cuyo OpenAPI se guarda en `tests/contract/openapi.json` y una prueba falla si el código se desvía de él.

**`/v1` (aplicación web)**

| Endpoint | Auth | Qué hace |
|---|---|---|
| `POST /v1/auth/login` | — | Usuario y clave (argon2id). Cinco fallos bloquean la cuenta 15 minutos (429 + `Retry-After`). Misma respuesta si el usuario no existe. |
| `GET /v1/auth/demo-accounts` | — | Cuentas de demostración y su clave compartida. 404 salvo `DEMO_ACCOUNTS_ENABLED=true`. |
| `GET /v1/me` | Bearer | Perfil mínimo. |
| `GET /v1/meta/data` | Bearer | Cuándo corrió por última vez el pipeline con éxito (`ops.etl_runs`); `null` si no se sabe. |
| `GET /v1/me/summary` | Bearer | Inicio: saldos por moneda (depósitos y crédito por separado), 5 últimos movimientos, casos activos por estado. |
| `GET /v1/me/products` y `/{id}` | Bearer | Productos con el número enmascarado (`****1234`), saldo, límite, estado. |
| `GET /v1/me/transactions` | Bearer | Historial paginado por cursor (`?cursor=`), filtros `product_id`, `status`, `merchant`, `from`, `to`. Cada fila trae `case_id` y `dispute_status` si ya tiene caso. |
| `GET /v1/me/transactions/{id}` | Bearer | Detalle, con titularidad. |
| `POST /v1/disputes` | Bearer | Idempotente por (cliente, transacción): 201 si crea, **200 con el caso existente** si ya había uno. Acepta `Idempotency-Key`. |
| `GET /v1/disputes` | Bearer | Mis casos, más nuevos primero (`?status=`). |
| `GET /v1/disputes/{id}` | Bearer | Estado, evidencia y línea de tiempo. |
| `POST /v1/disputes/{id}/escalate` | Bearer | `open` o `auto_resolved` → `escalated`, una vez. |
| `POST /v1/disputes/{id}/resolve` | Bearer | `open` → `auto_resolved`, una vez (lo llama el agente cuando la política resuelve sin una persona). |

**Raíz (agente)** — sin cambios de forma: `POST /session`, `GET /me`, `GET /me/transactions` (lista simple), `GET /me/transactions/{id}`, y las rutas de disputas (las mismas que bajo `/v1`). `GET /health` (el proceso vive) y `GET /ready` (alcanza la base).

Garantías:
- **Identidad:** siempre deriva del JWT validado (`get_current_customer`); ningún parámetro propone un `customer_id`.
- **`gold.*` es de solo lectura** para este servicio. Las tablas `app.*` las crean **migraciones SQL versionadas** (`app/migrations`), aplicadas al arrancar bajo un candado, cada una en su transacción.
- **Un caso por (cliente, transacción)**, garantizado por un índice único, no por el código: dos solicitudes simultáneas crean un solo caso.
- **`is_fraud`/`fraud_score` no existen en `gold.transactions`** y no aparecen en ningún SELECT (invariante del pipeline).
- Sin mover dinero: las disputas solo explican, documentan y escalan.

## Estructura

- `app/main.py` — app FastAPI, lifespan (pool, migraciones, cuentas de demostración), `/health`, `/ready`.
- `app/auth.py` — `POST /session` (el del agente), emisión/validación JWT HS256, dependencia `get_current_customer`.
- `app/passwords.py`, `app/demo.py`, `app/migrate.py`, `app/migrations/*.sql` — hash argon2id, cuentas de demostración, migraciones.
- `app/db.py` — `BankStore` (asyncpg, SQL explícito, sin ORM).
- `app/routes/customers.py` (raíz, agente), `app/routes/v1.py` (web), `app/routes/disputes.py` (compartido por ambos) — endpoints deterministas.
- `tests/` — rutas con un store en memoria, y `test_store_postgres.py` con el **SQL real** contra PostgreSQL (necesita `PG_TEST_HOST`; el CI lo levanta).

## Ejecutar y probar

```bash
cp .env.example .env            # PG_* apuntando al Postgres de Railway (database `data`) + SESSION_JWT_SECRET
set -a; . ./.env; set +a
uvicorn app.main:app --reload   # desde esta carpeta; http://localhost:8000/docs
```

Tests:

```bash
python -m pytest                # desde backend/, con pytest + httpx instalados; sin PG_TEST_HOST se salta el SQL real
PG_TEST_HOST=localhost PG_TEST_PORT=5432 PG_TEST_USER=postgres PG_TEST_PASSWORD=... python -m pytest   # todo
```

Despliegue: `../.railway/railway.ts` (servicio `backend`, Dockerfile propio, watchPatterns `backend/**`, healthcheck `/health`).
