# backend/ — mock banking service (tool layer)

Vertical 3 de `../spec/ARCHITECTURE.md`. Servicio FastAPI separado en Railway. Es el "service/tool layer" que el reto exige para enforced de permisos: la política vive acá, no en el prompt del LLM. El agente (PydanticAI) lo consume como herramientas tipadas contra los modelos de `app/schemas.py`.

## Estado: cascarón

Solo prueba el cableado: servicio arriba, base de datos alcanzable, salida del pipeline visible.

| Endpoint | Qué hace |
|---|---|
| `GET /health` | el servicio está vivo |
| `GET /health/db` | puede conectarse a Postgres (503 si no) |
| `GET /meta/data` | conteos de las tablas `gold.*` y última corrida exitosa del pipeline (`ops.etl_runs`); solo agregados |
| `GET /docs` | OpenAPI generado por FastAPI (el contrato) |

**No hay ningún endpoint que devuelva datos de clientes.** Eso llega junto con la autenticación por sesión de prueba (un `customer_id` nunca prueba identidad) y la verificación de titularidad transacción-producto.

## Base de datos

Se conecta con un rol de **solo lectura** (`backend_ro`: `SELECT` sobre `gold` y `ops`) y cada sesión arranca con `default_transaction_read_only=on` y un `statement_timeout` de 15 s: aunque un endpoint tuviera un bug, no puede escribir ni colgar la base. Variables: `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` (ver `.railway/railway.ts`; la contraseña no está en el repo).

## Desarrollo

```bash
pip install -r requirements-dev.txt
python -m pytest            # desde backend/
uvicorn app.main:app --reload
```

Despliegue gestionado en `../.railway/railway.ts` (no `railway.toml`, deprecado).
