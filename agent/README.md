# agent/ — agente + guardrail

Vertical 4 de `../spec/ARCHITECTURE.md`. Servicio FastAPI con LangGraph adentro. **Nunca toca `gold.*` directo** — todos los datos viajan por las tools HTTP de `../backend/`, siempre reenviando el token del usuario (enforcement doble). **Implementado** (workflow Opción A: disputas de transacciones).

## Contrato

| Endpoint | Qué hace |
|---|---|
| `POST /chat` `{session_token, message, conversation_id?}` | Devuelve `{reply, conversation_id, outcome: resolved\|clarify\|escalated, handoff?}`. Es lo único que consume el frontend. |
| `POST /session` | Proxy delgado al `POST /session` del backend — el frontend solo conoce la URL de este servicio. |
| `GET /health` | Liveness para Railway. |

## Grafo (`app/graph.py`)

`understand → decide → act → verify → (escalate) → respond` con edges condicionales. Control de flujo en código; el LLM solo redacta la respuesta final a partir de hechos verificados (sin key de OpenRouter responde con templates deterministas es/pt). Estado conversacional por `conversation_id` con checkpointer **en memoria** — se pierde al redeployar (limitación aceptada y documentada).

## Guardrail determinista (`app/guardrail.py` + nodo `decide`)

Tabla de decisiones, **no un prompt** — el LLM no puede negociarla:

- **Escal SIEMPRE:** (a) keywords de fraude/robo/"no fui yo" en es/pt (normalizadas sin acentos), (b) monto efectivo USD ≥ `GUARDRAIL_MAX_USD` (default 500), (c) ambigüedad sin resolver tras 2 rondas de aclaración, (d) intent fuera de alcance.
- **Auto-resuelve SOLO:** transacción `Declined`/`Reversed` del propio cliente, única candidata sin ambigüedad, bajo el umbral. `verify` re-consulta `GET /disputes/{id}` antes de reportar (no confía en que el LLM "diga" que funcionó).
- **Aclara (máx 2 rondas)** cuando hay 0 o >1 candidatas: pide comercio/monto/fecha; el narrowing es por menciones de comercio y monto en el texto, y si el cliente nombra un comercio que no coincide con nada, nunca autodescubre una transacción alternativa.

## Clasificación de intent (`app/intents.py`)

TypeSafe API si `TYPESAFE_API_KEY`+`TYPESAFE_API_URL` están presentes (la key aún no existe — camino defensivo), sino few-shot por OpenRouter, sino baseline determinista por keywords (referencia, se evalúa en el branch de eval).

## Otros módulos

- `app/tools.py` — clientes HTTP delgados al backend (`list_transactions`, `get_transaction`, `create_dispute`, `get_dispute`, `escalate_dispute`).
- `app/tracing.py` — cada paso del grafo a `agent.trace_log` en Postgres (DDL en startup). Evidencia de auditoría; **nunca** se registra chain-of-thought. Best-effort: un fallo de trace no rompe la conversación.
- `app/llm.py` — cliente OpenRouter (`OPENROUTER_MODEL` configurable, lista de fallback). Instrucción de sistema: responder en el idioma del usuario (es/pt), no inventar hechos, solo datos verificados.
- `app/replies.py` — templates deterministas es/pt por outcome (fallback sin LLM).

## Tests (backend mockeado, sin red ni Postgres)

```bash
python -m pytest                # desde agent/, con pytest + httpx instalados
```

Cubre los 3 caminos obligatorios (normal auto-resuelto con verificación, ambiguo con aclaración, handoff estructurado) más: fraude keyword → escalate, monto ≥ umbral → escalate (borde inclusive), 2 rondas sin resolución → escalate, portugués → respuesta en pt, token inválido/expirado → 401, y que el agente jamás toca datos de otro cliente.

Despliegue: `../.railway/railway.ts` (servicio `agent`, `BANK_URL` = dominio privado del backend, healthcheck `/health`).
