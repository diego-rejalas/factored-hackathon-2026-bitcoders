# Probar todo en local

Una base con datos de ejemplo, el backend y el agente en Docker, y el frontend en tu máquina (recarga al editar). No necesita nube, ni claves, ni la base real. Verificado el 2026-10-02: login, chat y caso registrado en un navegador real, y los 11 escenarios de `infra/gcp/scripts/e2e.py`.

## 1. Backend, agente y base

```bash
docker compose -f docker-compose.dev.yml up --build
```

| Servicio | Dirección | Qué es |
|---|---|---|
| backend | http://localhost:8000/docs | API (`/v1` para la web, la raíz para el agente) |
| agente | http://localhost:8001/health | el asistente |
| base | `localhost:5433`, usuario `postgres`, clave `dev`, base `data` | PostgreSQL 18 |

La base se crea la primera vez desde `backend/dev/gold_fixture.sql`. `docker compose -f docker-compose.dev.yml down -v` la tira y la próxima vez vuelve a empezar de cero (los casos creados se pierden).

**Los datos no son los del organizador:** son tres clientes inventados con los mismos `customer_id`, documentos y montos que usa `e2e.py`, para poder probar cada ruta de la política.

## 2. Frontend

```bash
cd frontend
cp -n .env.example .env.local        # NEXT_PUBLIC_AGENT_URL=http://localhost:8001
PNPM_MANAGE_PACKAGE_MANAGER_VERSIONS=false pnpm install
PNPM_MANAGE_PACKAGE_MANAGER_VERSIONS=false pnpm dev
```

Abre http://localhost:3000. Debe ser el puerto **3000**: el agente solo acepta ese origen (`CORS_ALLOWED_ORIGINS`). Si Next elige otro porque está ocupado, el navegador bloqueará las llamadas.

`PNPM_MANAGE_PACKAGE_MANAGER_VERSIONS=false` evita que pnpm intente descargar su propia versión (`packageManager` fija la 11.1.3), cosa que falla en algunas redes.

## 3. Qué probar

El login de la pantalla (sandbox) pide `customer_id` y documento:

| Cliente | customer_id | Documento | Mensaje | Resultado |
|---|---|---|---|---|
| Ana | `CLI-00MT1OY089RA` | `17521506` | `No reconozco la transferencia de 4189.18 dólares` | **Escala** (sobre USD 500) |
| Ana | | | `No reconozco la transferencia de 6783.64 dólares` | **Escala** (cobro ya aprobado) |
| Bruno | `CLI-0064RNKCVQCN` | `0863503738` | `No reconozco el cobro de 256.10` | **Se resuelve** (rechazado, no hubo cobro) |
| Carla | `CLI-00232W4ZDQPP` | `57064351` | `No reconozco el cobro de 389.87` | **Se resuelve** (revertido) |

Cualquiera: `Me robaron la tarjeta, no fui yo` → escala por sospecha de fraude.

## 4. Probar el backend `/v1` solo

Usuario y clave (las cuentas de demostración): `ana.demo`, `bruno.demo` y `carla.demo`, clave `Demo-Local-2026`.

```bash
curl -s localhost:8000/v1/auth/demo-accounts
TOKEN=$(curl -s -X POST localhost:8000/v1/auth/login -H 'content-type: application/json' \
  -d '{"username":"ana.demo","password":"Demo-Local-2026"}' | python3 -c 'import json,sys; print(json.load(sys.stdin)["session_token"])')
curl -s localhost:8000/v1/me/summary  -H "Authorization: Bearer $TOKEN"
curl -s localhost:8000/v1/me/products -H "Authorization: Bearer $TOKEN"
curl -s "localhost:8000/v1/me/transactions?limit=3" -H "Authorization: Bearer $TOKEN"   # next_cursor para la página siguiente
curl -s localhost:8000/v1/disputes    -H "Authorization: Bearer $TOKEN"
```

Los escenarios del agente, de una vez: `AGENT_URL=http://localhost:8001 python3 infra/gcp/scripts/e2e.py`.

## 5. Con un LLM de verdad

Sin clave el agente responde con su texto determinista. Para que redacte con el modelo:

```bash
OPENROUTER_API_KEY=sk-or-... docker compose -f docker-compose.dev.yml up --build
```

## Tests

```bash
# Backend: rutas con un store en memoria, y el SQL real si hay un PostgreSQL
cd backend && PG_TEST_HOST=localhost PG_TEST_PORT=5433 PG_TEST_USER=postgres PG_TEST_PASSWORD=dev python -m pytest
cd agent && python -m pytest
```
(el primero necesita la base del paso 1 arriba; sin `PG_TEST_HOST` se salta el SQL real).
