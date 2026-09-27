# agent/ — agente + guardrail

Vertical 4 de `../spec/ARCHITECTURE.md`. Servicio FastAPI separado en Railway con LangGraph adentro. Nunca toca Postgres directo — llama a `../backend/` por HTTP.

Pendiente de crear (una vez el equipo vote el workflow):
- `app/main.py` — expone `POST /chat`
- `app/graph.py` — grafo LangGraph: `understand → decide → act → verify → escalate`
- `app/guardrail.py` — tabla/config determinista de qué tool se puede invocar según intent + estado de sesión (vive en `decide`, ANTES de `act`)
- `app/tools/` — clientes HTTP delgados a `../backend/`
- `app/tracing.py` — logging estructurado de cada paso del grafo a `trace_log` en Postgres
- `Dockerfile`, `requirements.txt`

Despliegue gestionado en `../.railway/railway.ts`, mismo patrón que `../infra/airflow/` y `../backend/`.

LLM vía OpenRouter. Ver reglas del guardrail y casos obligatorios (normal/ambiguo/escalamiento) en `../spec/ARCHITECTURE.md`.
