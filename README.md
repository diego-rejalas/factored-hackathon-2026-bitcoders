# factored-hackathon-2026-bitcoders

Prototipo de sistema de atención al cliente bancario AI-first para el Factored AI & Data Hackathon 2026.

## Empezar acá

1. `doc/Factored AI & Data Hackathon 2026.md` — enunciado del reto (leer primero).
2. `spec/CRITERIA.md` — checklist de todo lo que hay que cumplir para la entrega.
3. `spec/DATA_FINDINGS.md` — hallazgos reales del dataset (S3), antes de asumir nada de los datos.
4. `spec/ARCHITECTURE.md` — arquitectura por verticales, diagramas, decisiones tomadas y por qué.

## Estructura del repo

| Carpeta | Rol / vertical | Estado |
|---|---|---|
| `etl/` | Pipeline completo en un job: DuckDB lee S3, `dbt build`, publica `gold` a Postgres | Desplegado en Railway |
| `data/dbt/` | Lógica — dbt sobre DuckDB (`bronze.*` → `silver.*` → `gold.*`), 121 tests | Implementado |
| `backend/` | Backend — microservicio de banca (tool layer, permisos) | Implementado |
| `agent/` | AI engineer — agente + guardrail (LangGraph) | Implementado |
| `frontend/` | Chat UI — Next.js (Cloud Run en GCP; standalone con `AGENT_URL` runtime) | Implementado |
| `.railway/railway.ts` | Infra legacy (pre-migración) — ya no se aplica; referencia histórica | Legacy |
| `infra/gcp/` | Infra — **despliegue primario en GCP** (Cloud Run + Cloud SQL + Job ETL, Terraform) | Definido (Terraform + CI) |
| `spec/` | Documentación de diseño y decisiones | — |
| `doc/` | Material del organizador (no editar) | — |

## Estado

Workflow confirmado: **Opción A — disputas de transacciones**, con umbral de escalamiento de $500 (ver `spec/WORKFLOW_DECISION.md`). El slice vertical completo (backend + agent + frontend + etl) está implementado, testeado y desplegado en GCP.

**Despliegue primario en GCP**:
- **Frontend**: Next.js 14 en Cloud Run (`https://frontend-127503393524.us-central1.run.app`).
- **Agente IA**: FastAPI + LangGraph con guardrails deterministas en Cloud Run (`https://agent-127503393524.us-central1.run.app`).
- **Backend Bancario**: FastAPI tool layer con permisos y acceso a base de datos en Cloud Run (`https://backend-127503393524.us-central1.run.app`).
- **Pipeline ETL Ultraligero**: Cloud Run Job (`etl`) ejecutando DuckDB + `dbt-duckdb` en RAM (procesa 23.5M filas en ~2.5 min, ejecuta 121 tests de calidad y publica exclusivamente las tablas `gold.*`). Sin microservicios dbt sueltos.
- **Base de Datos Serving**: Cloud SQL PostgreSQL 16 con **Hibernación Just-in-Time** (`./infra/gcp/manage_db.sh pause/resume`), reduciendo el costo en reposo a ~$0.05 USD/día.

Railway queda como referencia histórica (`.railway/railway.ts` legacy).

## Probar

Comandos verificados (por carpeta, ver los README de cada una para más detalle):

```bash
cd backend  && python -m pytest   # suite del tool layer (DB mockeada; requiere pytest + httpx)
cd agent    && python -m pytest   # suite del agente + guardrail (backend y LLM fakeados)
cd frontend && pnpm build         # build y typecheck de la UI
```

Control de base de datos Just-in-Time (GCP):
```bash
./infra/gcp/manage_db.sh resume   # Despierta Cloud SQL para pruebas (~60s)
./infra/gcp/manage_db.sh status   # Inspecciona estado actual (RUNNABLE / STOPPED)
./infra/gcp/manage_db.sh pause    # Hiberna Cloud SQL y congela facturación de cómputo/IP
```

