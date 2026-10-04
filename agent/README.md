# agent/ — agente + guardrail

Vertical 4 de `../spec/ARCHITECTURE.md`. Servicio FastAPI con LangGraph adentro. **Nunca toca `gold.*` directo** — todos los datos viajan por las tools HTTP de `../backend/`, siempre reenviando el token del usuario (enforcement doble). **Implementado** (workflow Opción A: disputas de transacciones).

## Contrato

| Endpoint | Qué hace |
|---|---|
| `POST /chat` `{session_token, message, conversation_id?}` | Devuelve `{reply, conversation_id, outcome, handoff?, candidates?, case?, reason?, language?}`. Los nuevos campos son opcionales; todo el flujo sigue siendo compatible con consumidores antiguos. |
| `POST /session` | Proxy delgado al `POST /session` del backend — el frontend solo conoce la URL de este servicio. |
| `POST /admin/session` | Proxy de login admin; el backend valida el hash y crea el JWT. |
| `GET /admin/disputes*`, `POST /admin/disputes/{id}/transition`, `GET /admin/metrics` | Proxies: reenvían el JWT admin y el ID token de servicio al backend, que vuelve a validar permisos. |
| `GET /admin/agent-metrics?window=<hours>` | Métricas de `agent.trace_log`: outcomes, contención proxy, p50/p95 por nodo, intent, idioma y resultado de verify. |
| `GET /admin/conversations/{id}/trace` | Timeline estructurado de la conversación asociada a un caso. Nunca contiene texto del cliente. |
| `GET /me/disputes`, `GET /disputes/{id}` | Proxies para que el cliente consulte sus casos y eventos. |
| `GET /meta/demo-scenarios`, `GET /meta/data` | Proxy público del selector demo y proxy admin de frescura, respectivamente. |
| `GET /health` | Liveness para Railway. |

## Grafo (`app/graph.py`)

`understand → decide → act → verify → (escalate) → respond` con edges condicionales. Control de flujo en código; el LLM solo redacta la respuesta final a partir de hechos verificados (sin key de OpenRouter responde con templates deterministas es/pt). Estado conversacional por `conversation_id` con checkpointer **en memoria** — se pierde al redeployar (limitación aceptada y documentada).

## Guardrail determinista (`app/guardrail.py` + nodo `decide`)

Tabla de decisiones, **no un prompt** — el LLM no puede negociarla:

- **Escal SIEMPRE:** (a) keywords de fraude/robo/"no fui yo" en es/pt (normalizadas sin acentos), (b) monto efectivo USD ≥ `GUARDRAIL_MAX_USD` (default 500), (c) ambigüedad sin resolver tras 2 rondas de aclaración, (d) intent fuera de alcance.
- **Auto-resuelve SOLO:** transacción `Declined`/`Reversed` del propio cliente, única candidata sin ambigüedad, bajo el umbral. `verify` re-consulta `GET /disputes/{id}` y marca `auto_resolved` por el endpoint del backend antes de reportar (no confía en que el LLM "diga" que funcionó).
- **Aclara (máx 2 rondas)** cuando hay 0 o >1 candidatas: pide comercio/monto/fecha; el narrowing es por menciones de comercio y monto en el texto, y si el cliente nombra un comercio que no coincide con nada, nunca autodescubre una transacción alternativa.
- Si el clasificador estructurado tiene confianza menor que `INTENT_MIN_CONFIDENCE` (default `0.5`), `decide` escala por regla de código. El override determinista de fraude se aplica antes de esta abstención.
- Cuando el pool del narrowing tiene 2+ candidatas, `app/ranking.py` solo las ordena para presentar primero la opción más probable; no agrega ni elimina candidatas y no cambia la decisión 0/1/2+ ni la corroboración exigida para resolver.

## Clasificación de intent (`app/intents.py`)

Orden: TypeSafe si `TYPESAFE_API_KEY`+`TYPESAFE_API_URL` están presentes (stub defensivo, sin confianza); de otro modo, clasificación estructurada por OpenRouter `{intent, language, confidence}`; si falta la clave o la respuesta no es válida, baseline determinista por keywords. La traza registra fuente, versión de prompt, confianza y latencias del clasificador/nodo; el idioma clasificado usa la detección por substring como fallback.

Los sets generados por el equipo y los harnesses de evaluación están en `../ml/eval/`; incluyen baseline, clasificación LLM opcional y comparación de ranking. El candidato LLM requiere `OPENROUTER_API_KEY`; las instrucciones reproducibles y limitaciones están en `../ml/eval/README.md` y los resultados en `../spec/ML_FINDINGS.md` §12.

## Otros módulos

- `app/tools.py` — clientes HTTP delgados al backend y proxies admin; cada llamada bancaria reenvía el token del cliente, y cada llamada admin el token admin.
- `app/tracing.py` — cada paso del grafo a `agent.trace_log` en Postgres (DDL en startup). Evidencia de auditoría; **nunca** se registra chain-of-thought ni texto del usuario. Best-effort: un fallo de trace no rompe la conversación.
- `app/llm.py` — cliente OpenRouter (`OPENROUTER_MODEL` configurable, lista de fallback). Instrucción de sistema: responder en el idioma del usuario (es/pt), no inventar hechos, solo datos verificados.
- `app/ranking.py` — ranker interpretable (difflib + monto/fecha/canal) que reordena pools ambiguos; no altera la política del guardrail.
- `app/replies.py` — templates deterministas es/pt por outcome (fallback sin LLM).

## Tests (backend mockeado, sin red ni Postgres)

```bash
python -m pytest                # desde agent/, con pytest + httpx instalados
```

Cubre los 3 caminos obligatorios (normal auto-resuelto con verificación, ambiguo con aclaración, handoff estructurado) más: fraude keyword → escalate, abstención/fallback de intención, orden de candidatas sin auto-resolver un pool ambiguo, monto ≥ umbral → escalate (borde inclusive), 2 rondas sin resolución → escalate, portugués → respuesta en pt, token inválido/expirado → 401, proxies admin y agregación de percentiles, y que el agente jamás toca datos de otro cliente.

Despliegue: `../.railway/railway.ts` (servicio `agent`, `BANK_URL` = dominio privado del backend, healthcheck `/health`).
