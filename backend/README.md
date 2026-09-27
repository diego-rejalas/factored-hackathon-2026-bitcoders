# backend/ — mock banking service (tool layer)

Vertical 3 de `../spec/ARCHITECTURE.md`. Servicio FastAPI separado en Railway. Es el "service/tool layer" que el reto exige para enforced de permisos — la política vive acá, no en el prompt del LLM.

Pendiente de crear (una vez el equipo vote el workflow, define endpoints exactos según A/B/C/D):
- `app/main.py` — FastAPI app
- `app/auth.py` — validación de sesión de prueba antes de cualquier endpoint
- `app/routes/` — endpoints deterministas (`GET /customers/{id}`, `GET /customers/{id}/transactions`, `POST /cases`, etc.)
- `app/db.py` — conexión a `clean.*` en Postgres (ver `../data/dbt/`)
- `Dockerfile`, `requirements.txt`

Despliegue gestionado en `../.railway/railway.ts` (no `railway.toml` — deprecado, ver `../spec/ARCHITECTURE.md`), mismo patrón que `../infra/airflow/`.

Contrato de servicio (a documentar cuando existan los endpoints): OpenAPI que FastAPI expone gratis en `/docs`.
