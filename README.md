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
| `backend/` | Backend — microservicio de banca (tool layer, permisos) | Por crear |
| `agent/` | AI engineer — agente + guardrail (LangGraph) | Por crear |
| `frontend/` | Chat UI (Vercel) | Por crear |
| `.railway/railway.ts` | Infra — despliegue completo como código (reemplaza `railway.toml`, deprecado) | Vigente |
| `spec/` | Documentación de diseño y decisiones | — |
| `doc/` | Material del organizador (no editar) | — |

## Estado

Workflow (disputas de transacciones / tarjetas / cuentas / crédito) todavía en votación del equipo — ver opciones en `spec/ARCHITECTURE.md` (versión previa de este documento, sección de propuestas). Infra base (Airflow, Postgres) ya desplegada en Railway; código de negocio pendiente de esa decisión.
