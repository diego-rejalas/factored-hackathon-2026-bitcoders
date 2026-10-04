# backend/ — mock banking service (tool layer)

Vertical 3 de `../docs/ARCHITECTURE.md`. Servicio FastAPI separado (Cloud Run). Es el "service/tool layer" que el reto exige para enforced de permisos — la política vive acá, no en el prompt del LLM. **Implementado** (workflow Opción A: disputas de transacciones, ver `../docs/WORKFLOW.md`).

## Contrato (OpenAPI en `/docs`)

Dos superficies sobre el mismo servicio. La **raíz** es la que usa el agente (el navegador no llama al backend: va al agente); **`/v1`** es una superficie pensada para una aplicación web, que la interfaz actual no usa. Diseño y decisiones en `../docs/API.md`; **el contrato (rutas, estados, errores, seguridad) en `../docs/API.md`**, cuyo OpenAPI se guarda en `tests/contract/openapi.json` y una prueba falla si el código se desvía de él.

**Raíz (la que usa el agente)**

| Endpoint | Auth | Qué hace |
|---|---|---|
| `POST /session` | — | Login de prueba: valida `customer_id` + `document_number` contra `gold.customers` y emite JWT HS256 con `role=customer` (exp ~2h, `SESSION_TTL_MINUTES`). Sesión sandbox, no hay IdP real detrás. |
| `POST /admin/session` | — | Login de especialista con `ADMIN_USERS` (hashes bcrypt en Secret Manager); emite JWT `role=admin` (`ADMIN_TTL_MINUTES`, default 8h). Cinco fallos por IP+usuario bloquean 60s en memoria; límite por proceso, solo adecuado para la demo. |
| `GET /health` | — | Liveness para el healthcheck de Cloud Run. |
| `GET /me` | Bearer | Perfil mínimo (nombre, país). Jamás expone income/credit_score/document_number. |
| `GET /me/transactions?status=&merchant=&days=&limit=` | Bearer | Movimientos propios; siempre filtra por el `customer_id` del token (el query no acepta customer_id). `amount_usd_effective` = `coalesce(amount_usd, amount si currency='USD')` — 57% de `amount_usd` es nulo en filas USD (ver `../docs/DATA.md`). `days` ancla al borde del snapshot (última transacción del dataset), no a `now()`. |
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
- **`gold.*` es read-only** para este servicio; las tablas `app.*` las crean **migraciones SQL versionadas** (`app/migrations`), aplicadas al arrancar bajo un candado, cada una en su transacción.
- La migración `0005` (el CHECK de `app.disputes.status` permite `in_progress`, la transacción es opcional) y `0004`/`0005` reparan handoffs y eventos JSON que versiones previas guardaron como texto.
- **Un caso por (cliente, transacción)**, garantizado por un índice único (migración `0003`): reportar la misma transacción otra vez devuelve ese caso, y dos solicitudes simultáneas crean uno solo. Un caso sin transacción nunca es duplicado de otro.
- `backend_app` necesita `USAGE` + `SELECT` en `ops.etl_runs` para frescura; `roles.sql` concede ese acceso y privilegios por defecto sin abrir `agent.*`.

**`/v1`** — la superficie pensada para una aplicación web (no la usa la interfaz actual, que llama al agente; se conserva y está cubierta por pruebas y por el contrato):

| Endpoint | Auth | Qué hace |
|---|---|---|
| `POST /v1/auth/login` | — | Usuario y clave (argon2id). Cinco fallos bloquean la cuenta 15 minutos (429 + `Retry-After`). Misma respuesta si el usuario no existe. |
| `GET /v1/auth/demo-accounts` | — | Cuentas de demostración y su clave compartida. 404 salvo `DEMO_ACCOUNTS_ENABLED=true`. |
| `GET /v1/me`, `/v1/me/summary`, `/v1/me/products` y `/{id}` | Bearer | Perfil, resumen (saldos por moneda, depósitos y crédito por separado), productos con el número enmascarado (`****1234`). |
| `GET /v1/me/transactions` y `/{id}` | Bearer | Historial paginado por cursor (`?cursor=`), filtros `product_id`, `status`, `merchant`, `from`, `to`; cada fila trae `case_id`, `dispute_status` y `response_meaning` (el motivo del código de respuesta, estándar ISO 8583: un supuesto, el organizador no lo define). |
| `GET /v1/disputes`, `/v1/disputes/{id}` y `POST /v1/disputes…` | Bearer | Las mismas rutas de disputas de la raíz. |

Todo endpoint con sesión valida el rol: un token `admin` no abre rutas de cliente y al revés.
- **`is_fraud`/`fraud_score` no existen en `gold.transactions`** y no aparecen en ningún SELECT (invariante del pipeline).
- Sin mover dinero: las disputas solo explican, documentan y escalan.

## Estructura

- `app/main.py` — app FastAPI, lifespan (pool, migraciones, cuentas de demostración), `/health`, `/ready`.
- `app/auth.py` — `POST /session` (el del agente), emisión/validación JWT HS256, dependencia `get_current_customer`.
- `app/passwords.py`, `app/demo.py`, `app/migrate.py`, `app/migrations/*.sql` — hash argon2id, cuentas de demostración, migraciones.
- `app/db.py` — `BankStore` (asyncpg, SQL explícito, sin ORM).
- `app/routes/customers.py` (raíz, agente y web), `app/routes/disputes.py` (compartido por la raíz y `/v1`), `app/routes/v1.py`, `app/routes/admin_disputes.py`, `app/routes/meta.py` — endpoints deterministas.
- `app/passwords.py`, `app/demo.py`, `app/migrate.py`, `app/migrations/*.sql`, `app/observability.py`, `app/response_codes.py` — hash argon2id, cuentas de demostración, migraciones, `X-Request-ID` y registros JSON, significado de los códigos de respuesta.
- `tests/` — rutas con un store en memoria; `test_store_postgres.py` con el **SQL real** contra PostgreSQL (necesita `PG_TEST_HOST`; el CI lo levanta); `tests/contract/openapi.json` + `test_openapi_contract.py`, el contrato que el código no puede dejar de cumplir sin que falle una prueba.

## Ejecutar y probar

```bash
cp .env.example .env            # PG_* apuntando al Postgres local (`docker-compose.dev.yml`) (database `data`) + SESSION_JWT_SECRET
set -a; . ./.env; set +a
uvicorn app.main:app --reload   # desde esta carpeta; http://localhost:8000/docs
```

Tests:

```bash
python -m pytest                # desde backend/, con pytest + httpx instalados; sin PG_TEST_HOST se salta el SQL real
PG_TEST_HOST=localhost PG_TEST_PORT=5432 PG_TEST_USER=postgres PG_TEST_PASSWORD=... python -m pytest   # todo
```

## Acceso administrativo (sandbox)

Genera cada hash fuera del repo y guarda la cadena completa `usuario:hash[,usuario:hash...]` en `ADMIN_USERS` (en GCP, Secret Manager; nunca en Git). Ejemplo para generar un hash bcrypt:

```bash
python -c "import bcrypt; print(bcrypt.hashpw(b'CAMBIA_ESTA_CLAVE', bcrypt.gensalt()).decode())"
```

El usuario introduce la contraseña original; solo el hash se almacena. En GCP, `admin-users` es un secreto manual separado por ambiente (`factored-dev-admin-users`, `factored-qa-admin-users`, `factored-prod-admin-users`). Sustituye el placeholder `NOT_SET` con una nueva versión antes de habilitar el acceso. No uses una contraseña real de producción: este prototipo no tiene IdP ni rate-limit distribuido.

Despliegue: Cloud Run, ver `../infra/gcp/envs/`.
