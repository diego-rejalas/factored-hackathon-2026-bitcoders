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
| `infra/airflow/`, `data/dags/` | Airflow orquesta; DuckDB extrae de S3 y carga a `bronze.*` | Desplegado en Railway |
| `infra/dbt/`, `data/dbt/` | Lógica — dbt sobre Postgres (`bronze.*` → `silver.*` → `gold.*`), 121 tests | Implementado |
| `backend/` | Backend — tool layer de banca (FastAPI, rol de solo lectura) | Cascarón desplegado en Railway |
| `agent/` | AI engineer — agente + guardrail (PydanticAI) | Por crear |
| `frontend/` | Interfaz de chat (Next.js en Vercel) | Cascarón |
| `.railway/railway.ts` | Infra — despliegue completo como código (reemplaza `railway.toml`, deprecado) | Vigente |
| `spec/` | Documentación de diseño y decisiones | — |
| `doc/` | Material del organizador (no editar) | — |

## Estado

Workflow (disputas de transacciones / tarjetas / cuentas / crédito) todavía en votación del equipo — ver opciones en `spec/ARCHITECTURE.md` (versión previa de este documento, sección de propuestas). Infra base (Airflow, Postgres) ya desplegada en Railway; código de negocio pendiente de esa decisión.
