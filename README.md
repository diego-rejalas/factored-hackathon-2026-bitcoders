# factored-hackathon-2026-bitcoders

Prototipo de sistema de atención al cliente bancario AI-first para el Factored AI & Data Hackathon 2026.

## Empezar acá

1. `doc/Factored AI & Data Hackathon 2026.md` — enunciado del reto (leer primero).
2. `spec/CRITERIA.md` — checklist de todo lo que hay que cumplir para la entrega.
3. `spec/DATA_FINDINGS.md` — hallazgos reales del dataset (S3), antes de asumir nada de los datos.
4. `spec/ARCHITECTURE.md` — arquitectura por verticales, diagramas, decisiones tomadas y por qué.
5. `spec/ENTERPRISE_ARCHITECTURE_EVALUATION.md` — evaluación de viabilidad para empresas reales, modelado de costos TCO y roadmap de madurez.

## Estructura del repo

| Carpeta | Rol / vertical | Estado |
|---|---|---|
| `infra/airflow/`, `data/dags/` | Pipeline A (Railway): Airflow orquesta; DuckDB extrae de S3 y carga a `bronze.*` | Desplegado en Railway |
| `infra/dbt/`, `data/dbt/` | Lógica — dbt sobre Postgres (`bronze.*` → `silver.*` → `gold.*`), 133 pruebas más 37 de valores aceptados | Implementado |
| `infra/gcp/etl/` | Pipeline B (GCP, del PR): un Cloud Run Job con DuckDB y `dbt-duckdb` en RAM; publica solo `gold.*` | Definido, sin validar |
| `backend/` | Backend — microservicio de banca (tool layer, sesión por JWT, permisos por titularidad, API admin de disputas) | Implementado (PR #1) |
| `agent/` | AI engineer — agente + guardrail (LangGraph); proxies admin y métricas/traza desde `agent.trace_log` | Implementado (PR #1); en revisión, ver `spec/PR1_REVIEW.md` |
| `frontend/` | Next.js (Cloud Run standalone con `AGENT_URL`): chat cliente (`/`), consola de especialistas (`/admin`), documentación de datos en `/data-docs` | Implementado |
| `.railway/railway.ts` | Infra Railway: pipeline A y servicios actuales | Vigente hasta decidir la migración |
| `infra/gcp/` | Infra GCP en Terraform, en tres ambientes (`envs/dev|qa|prod`) con módulos compartidos | Definido, `validate` y `plan` verificados; sin `apply` |
| `spec/` | Documentación de diseño y decisiones | — |
| `doc/` | Material del organizador (no editar) | — |

## Estado

Workflow confirmado: **Opción A — disputas de transacciones**, con umbral de escalamiento de $500 (ver `spec/WORKFLOW_DECISION.md`). El slice vertical completo (backend + agent + frontend + etl) está implementado, testeado y desplegado en GCP.

**Despliegue primario en GCP**:
- **Frontend**: Next.js 14 en Cloud Run (`https://frontend-127503393524.us-central1.run.app`).
- **Agente IA**: FastAPI + LangGraph con guardrails deterministas en Cloud Run (`https://agent-127503393524.us-central1.run.app`).
- **Backend Bancario**: FastAPI tool layer con permisos y acceso a base de datos en Cloud Run (`https://backend-127503393524.us-central1.run.app`).
- **Pipeline ETL Ultraligero**: Cloud Run Job (`etl`) ejecutando DuckDB + `dbt-duckdb` en RAM (procesa 23.5M filas en ~2.5 min, ejecuta 121 tests de calidad y publica exclusivamente las tablas `gold.*`). Sin microservicios dbt sueltos.
- **Data Lakehouse (GCS + Parquet)**: Capas Bronze y Silver preservadas en Parquet comprimido (ZSTD) particionado por Hive en Google Cloud Storage (`gs://factored-lakehouse-*`) por ~$0.03 USD/mes, manteniendo Cloud SQL libre de tablas crudas intermedias.
- **Base de Datos Serving**: Cloud SQL PostgreSQL 16 con **Hibernación Just-in-Time** (`./infra/gcp/scripts/manage_db.sh pause/resume`), reduciendo el costo en reposo a ~$0.05 USD/día.
- **Consola de especialistas (`/admin`)**: bandeja de casos escalados con handoff estructurado, traza del agente, transiciones auditadas (`claim → close`) y métricas backend+agente con denominadores explícitos. Login sandbox con `ADMIN_USERS` (bcrypt en Secret Manager).

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
./infra/gcp/scripts/manage_db.sh resume   # Despierta Cloud SQL para pruebas (~60s)
./infra/gcp/scripts/manage_db.sh status   # Inspecciona estado actual (RUNNABLE / STOPPED)
./infra/gcp/scripts/manage_db.sh pause    # Hiberna Cloud SQL y congela facturación de cómputo/IP
```

