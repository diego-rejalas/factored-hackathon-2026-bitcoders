# agent/: agente y guardrail

Servicio FastAPI con LangGraph. Habla con el cliente, decide con una política determinista, llama a las herramientas del backend, verifica y escala. Es la vertical 4 de [`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md); la política completa está en [`docs/WORKFLOW.md`](../docs/WORKFLOW.md).

**Nunca toca `gold.*`.** Todo dato bancario viaja por el backend HTTP, reenviando el token del cliente (la autorización se comprueba dos veces). Solo escribe sus propias tablas: `agent.trace_log` y `agent.conversation_messages`.

## Contrato

El esquema exacto es `tests/contract/openapi.json` y una prueba falla si el código se desvía. Rutas del propio agente:

| Ruta | Qué hace |
|---|---|
| `POST /chat` `{session_token, message, conversation_id?, transaction_id?}` | Devuelve `{reply, conversation_id, outcome, case_id, case_status, case, handoff, candidates, reason, language}`. `outcome` es `resolved`, `clarify`, `escalated` o `unavailable` |
| `GET /me/conversations`, `GET /me/conversations/{id}` | El historial del cliente. Solo lo lee su dueño (el cliente sale del token); otro cliente recibe 404 |
| `GET /admin/agent-metrics?window=<horas>` | Resultados, contención, latencia p50 y p95 por nodo, intenciones, idiomas y resultado de `verify`, desde `agent.trace_log` |
| `GET /admin/conversations/{id}/trace` | Los pasos de una conversación. Nunca contiene texto del cliente |
| `GET /health` | Liveness |

El resto son reenvíos delgados al backend con comprobaciones previas: `POST /session`, `POST /admin/session`, `GET /me/disputes`, `GET /disputes/{id}`, `GET /meta/demo-scenarios`, `GET /meta/data`, `GET /admin/disputes*`, `POST /admin/disputes/{id}/transition` y `GET /admin/metrics`.

## Grafo (`app/graph.py`)

`understand → decide → act → verify → respond | escalate`, con aristas condicionales. El control de flujo es código; el modelo no decide nada.

- **`decide`** aplica el guardrail antes de cualquier herramienta.
- **`verify`** relee el caso del backend antes de decir que se registró; si no coincide, escala (`verify_failed`).
- **Fallas:** hasta 3 intentos por herramienta, con 2 s de conexión (peor caso ~6,9 s). Si el backend no responde, `outcome: unavailable` con un mensaje seguro y sin cambios.

## Guardrail (`app/guardrail.py`)

Una tabla de decisiones en código, no un prompt. Escala siempre ante: fraude o robo (es y pt), un cobro `Approved` o `Pending`, un monto efectivo en USD mayor o igual a `GUARDRAIL_MAX_USD` (500 por defecto) o desconocido, ambigüedad sin resolver tras 2 rondas de aclaración, y una confianza del clasificador menor que `INTENT_MIN_CONFIDENCE` (0,5 por defecto; el override de fraude se aplica antes de esta abstención). Una petición fuera de alcance se **declina** (`outcome: declined`, sin caso ni traspaso). Resuelve solo una transacción `Declined` o `Reversed` del propio cliente, única candidata y bajo el umbral. El detalle y el orden están en [`docs/WORKFLOW.md`](../docs/WORKFLOW.md).

Cuando el pool de candidatas tiene 2 o más, `app/ranking.py` solo las **ordena** para ofrecer primero la más probable: no agrega ni quita candidatas y no cambia la decisión 0, 1 o 2 y más ni la corroboración exigida para resolver.

## Modelo de lenguaje (opcional)

Con `OPENROUTER_API_KEY`, el modelo hace tres cosas, y nunca decide la política:

1. **Clasificar la intención** de un mensaje (`app/intents.py`): una salida estructurada `{intent, language, confidence}`, con la versión del prompt en la traza. Sin clave, o si la respuesta no es válida, se usan las palabras clave en es y pt.
2. **Una segunda lectura de fraude** (`LLM.flags_fraud`), a la vez que la clasificación, sobre mensajes que parecen una disputa o algo fuera de alcance. Solo puede sumar cautela: un "sí" pasa el caso a una persona; un "no" o un fallo dejan la lista de frases de `guardrail.py` como estaba.
3. **Redactar la respuesta de un caso ya resuelto** (`app/llm.py`). El borrador pasa por `app/grounding.py` antes de enviarse: sin plazos ni promesas de dinero, sin números que no estén en los hechos, sin identificadores de cliente, con el número de caso. Si falla, sale la plantilla de `app/replies.py`. Escalaciones, aclaraciones y estados nunca los redacta el modelo.

El idioma lo fija la clasificación (si el modelo dice "mixto", lo resuelve el texto con una sola función, `replies.detect_language`). La traza registra fuente, versión del prompt, confianza y latencias. El cliente del modelo suma tokens y costo (`LLM.usage`).

Los conjuntos retenidos y las evaluaciones están en `../ml/eval/` (clasificación de intención y ranking de transacciones) y en `eval/` (el sistema de punta a punta y el clasificador); los resultados, en [`docs/EVALUATION.md`](../docs/EVALUATION.md) y [`docs/ML_FINDINGS.md`](../docs/ML_FINDINGS.md).

## Otros módulos

- `app/tools.py`: clientes HTTP delgados al backend; cada llamada reenvía el token del cliente o del administrador.
- `app/ranking.py`: ranker interpretable (difflib, monto, fecha y canal) que reordena pools ambiguos.
- `app/tracing.py`: cada paso a `agent.trace_log`. Nunca guarda el texto del cliente ni el razonamiento del modelo. Es la evidencia de auditoría; un fallo de traza no rompe la conversación.
- `app/conversations.py`: guarda cada turno en `agent.conversation_messages` (lo que escribió el cliente, la respuesta y sus tarjetas). Es la tabla a la que aplicaría la política de retención. Guardar es de mejor esfuerzo.
- `app/observability.py`: `X-Request-ID` y registros JSON.

## Configuración

Ver `.env.example`. Las principales: `BANK_URL`, `SESSION_JWT_SECRET` (compartida con el backend), `GUARDRAIL_MAX_USD`, `OPENROUTER_API_KEY` y `OPENROUTER_MODEL`, `CORS_ALLOWED_ORIGINS` (orígenes exactos, nunca `*`) y `PG_*` para las tablas del agente.

## Pruebas

```bash
python -m pytest        # desde agent/, con pytest y httpx; el backend y el modelo van simulados
PG_TEST_HOST=localhost PG_TEST_PORT=5433 PG_TEST_USER=postgres PG_TEST_PASSWORD=dev python -m pytest   # también el SQL del historial contra PostgreSQL
```

Cubren los tres caminos obligatorios, el guardrail y sus bordes (el umbral inclusive), la abstención por baja confianza y el orden de candidatas, el portugués, la sesión inválida, los reintentos, las comprobaciones del borrador del modelo, el aislamiento del historial entre clientes y el contrato OpenAPI.

Despliegue: Cloud Run, ver [`infra/gcp/envs/`](../infra/gcp/envs/).
