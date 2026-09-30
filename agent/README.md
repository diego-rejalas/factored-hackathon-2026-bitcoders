# agent/ — agente + guardrail

Vertical 4 de `../spec/ARCHITECTURE.md`. Servicio FastAPI separado en Railway con **PydanticAI** adentro. Nunca toca Postgres directo — llama a `../backend/` por HTTP.

Pendiente de crear (una vez el equipo vote el workflow):
- `app/main.py` — expone el endpoint de chat (stream compatible con el SDK de Vercel, vía `VercelAIAdapter.dispatch_request()`)
- `app/agent.py` — el agente PydanticAI y su flujo `understand → decide → act → verify → escalate` (con `pydantic-graph` si hace falta un grafo explícito)
- `app/guardrail.py` — tabla/config determinista de qué tool se puede invocar según intent + estado de sesión (vive en `decide`, ANTES de `act`)
- `app/tools/` — herramientas: clientes HTTP delgados a `../backend/`, tipados con los modelos de `../backend/app/schemas.py`
- `app/tracing.py` — logging estructurado de cada paso a `trace_log` en Postgres
- `Dockerfile`, `requirements.txt`

Despliegue gestionado en `../.railway/railway.ts`, mismo patrón que `../infra/airflow/` y `../backend/`.

LLM vía OpenRouter. Ver reglas del guardrail y casos obligatorios (normal/ambiguo/escalamiento) en `../spec/ARCHITECTURE.md`.
