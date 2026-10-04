# backend/ — mock banking service (tool layer)

Vertical 3 de `../spec/ARCHITECTURE.md`. Servicio FastAPI separado en Railway. Es el "service/tool layer" que el reto exige para enforced de permisos — la política vive acá, no en el prompt del LLM. **Implementado** (workflow Opción A: disputas de transacciones, ver `../spec/WORKFLOW_DECISION.md`).

## Contrato (OpenAPI en `/docs`)

FastAPI expone el esquema completo en `/openapi.json` y la UI interactiva en `/docs`. Resumen:

| Endpoint | Auth | Qué hace |
|---|---|---|
| `POST /session` | — | Login de prueba: valida `customer_id` + `document_number` contra `gold.customers` y emite JWT HS256 con `role=customer` (exp ~2h, `SESSION_TTL_MINUTES`). Sesión sandbox, no hay IdP real detrás. |
| `POST /admin/session` | — | Login de especialista con `ADMIN_USERS` (hashes bcrypt en Secret Manager); emite JWT `role=admin` (`ADMIN_TTL_MINUTES`, default 8h). Cinco fallos por IP+usuario bloquean 60s en memoria; límite por proceso, solo adecuado para la demo. |
| `GET /health` | — | Liveness para el healthcheck de Railway. |
| `GET /me` | Bearer | Perfil mínimo (nombre, país). Jamás expone income/credit_score/document_number. |
| `GET /me/transactions?status=&merchant=&days=&limit=` | Bearer | Movimientos propios; siempre filtra por el `customer_id` del token (el query no acepta customer_id). `amount_usd_effective` = `coalesce(amount_usd, amount si currency='USD')` — 57% de `amount_usd` es nulo en filas USD (ver `../spec/DATA_FINDINGS.md`). `days` ancla al borde del snapshot (última transacción del dataset), no a `now()`. |
| `GET /me/transactions/{id}` | Bearer | Detalle con verificación de titularidad → 404 si es ajena. |
| `GET /me/disputes` | Bearer | Lista mínima de casos propios, ordenados por creación descendente. |
| `POST /disputes` | Bearer | Crea caso `open` en `app.disputes`; valida titularidad de la transacción primero → 404 si es ajena. Evidencia: snapshot de la transacción. |
| `GET /disputes/{case_id}` | Bearer | Estado + evidencia + eventos (lo usa el nodo `verify` del agent). 404 si el caso no es del token. |
| `POST /disputes/{case_id}/escalate` | Bearer | Marca `escalated` y guarda el handoff estructurado en la evidencia + evento append-only. |
| `POST /disputes/{case_id}/resolve` | Bearer | Marca `auto_resolved` después de la verificación del agent; guarda `no_charge_confirmed` o `reversal_confirmed` y el evento del sistema. No se puede aplicar a casos escalados. |
| `GET /admin/disputes?status=&customer_id=&limit=&offset=` | Admin | Bandeja paginada con cliente, idioma y motivo del handoff; `status=active` incluye `escalated` + `in_progress`. |
| `GET /admin/disputes/{case_id}` | Admin | Detalle, handoff estructurado, conversation_id y eventos auditados. |
| `POST /admin/disputes/{case_id}/transition` | Admin | `claim`: `open|escalated → in_progress`; `close`: `in_progress → closed` con resolución y nota obligatorias. Cada transición agrega un evento con admin/nota. El humano nunca establece `auto_resolved`. |
| `GET /admin/metrics?window=<hours>` | Admin | Totales por estado, resolución automática segura con denominador, escalamientos, cierres humanos e idioma/motivo del handoff. Sin casos, la tasa es `null` (no definida). |
| `GET /meta/data` | Admin | Conteos de `gold.*`, borde temporal del snapshot y última corrida de `ops.etl_runs`. |
| `GET /meta/demo-scenarios` | — | Selector público para la demo: solo escenario, customer_id, document_number, first_name y pistas es/pt; nunca expone campos de fraude. Cache de 5 minutos. |

Garantías:
- **Identidad:** siempre deriva del JWT validado (`get_current_customer`); el LLM/chat no puede proponer `customer_id`. Un caso sin transacción vinculada representa una escalación aún no identificada; no habilita lecturas de terceros.
- **Roles:** endpoints admin exigen `role=admin`; los tokens de cliente conservan `sub=customer_id`. El login administrativo es sandbox, no un IdP; `ADMIN_USERS` debe vivir en Secret Manager.
- **`gold.*` es read-only** para este servicio; las tablas operacionales se crean en startup y reciben una migración idempotente y acotada. No existe un framework general de migraciones.
- La actualización idempotente del CHECK de `app.disputes.status` permite `in_progress` y repara handoffs/eventos JSON que fueron guardados como strings por versiones previas.
- `backend_app` necesita `USAGE` + `SELECT` en `ops.etl_runs` para frescura; `roles.sql` concede ese acceso y privilegios por defecto sin abrir `agent.*`.
- **`is_fraud`/`fraud_score` no existen en `gold.transactions`** y no aparecen en ningún SELECT (invariante del pipeline).
- Sin mover dinero: las disputas solo explican, documentan y escalan.

## Estructura

- `app/main.py` — app FastAPI, lifespan (pool + DDL), `/health`.
- `app/auth.py` — `POST /session`, emisión/validación JWT HS256, dependencia `get_current_customer`.
- `app/db.py` — `BankStore` (asyncpg, SQL explícito, sin ORM).
- `app/routes/customers.py`, `app/routes/disputes.py`, `app/routes/admin_disputes.py`, `app/routes/meta.py` — endpoints deterministas.
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

## Acceso administrativo (sandbox)

Genera cada hash fuera del repo y guarda la cadena completa `usuario:hash[,usuario:hash...]` en `ADMIN_USERS` (en GCP, Secret Manager; nunca en Git). Ejemplo para generar un hash bcrypt:

```bash
python -c "import bcrypt; print(bcrypt.hashpw(b'CAMBIA_ESTA_CLAVE', bcrypt.gensalt()).decode())"
```

El usuario introduce la contraseña original; solo el hash se almacena. En GCP, `admin-users` es un secreto manual separado por ambiente (`factored-dev-admin-users`, `factored-qa-admin-users`, `factored-prod-admin-users`). Sustituye el placeholder `NOT_SET` con una nueva versión antes de habilitar el acceso. No uses una contraseña real de producción: este prototipo no tiene IdP ni rate-limit distribuido.

Despliegue: `../.railway/railway.ts` (servicio `backend`, Dockerfile propio, watchPatterns `backend/**`, healthcheck `/health`).
