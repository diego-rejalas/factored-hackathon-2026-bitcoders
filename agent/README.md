# agent/: agent and guardrail

A FastAPI service with LangGraph. It talks to the customer, decides with a deterministic policy, calls the backend's tools, verifies and escalates. It is vertical 4 of [`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md), and the full policy is in [`docs/WORKFLOW.md`](../docs/WORKFLOW.md).

**It never touches `gold.*`.** All banking data travels through the backend over HTTP, forwarding the customer's token (authorization is checked twice). It writes only its own tables: `agent.trace_log` and `agent.conversation_messages`.

## Contract

The exact schema is `tests/contract/openapi.json`, and a test fails if the code drifts from it. The agent's own routes:

| Route | What it does |
|---|---|
| `POST /chat` `{session_token, message, conversation_id?, transaction_id?}` | Returns `{reply, conversation_id, outcome, case_id, case_status, case, handoff, candidates, reason, language}`. `outcome` is `resolved`, `clarify`, `escalated`, `declined` or `unavailable` |
| `GET /me/conversations`, `GET /me/conversations/{id}` | The customer's history. Only its owner reads it (the customer comes from the token), and another customer gets 404 |
| `GET /admin/agent-metrics?window=<hours>` | Outcomes, containment, p50 and p95 latency per node, intents, languages and the `verify` result, from `agent.trace_log` |
| `GET /admin/conversations/{id}/trace` | The steps of a conversation. It never contains customer text |
| `GET /health` | Liveness |
| `GET /ready` | Readiness: the agent's own database connection works and the backend answers its `/ready` (which reaches the database). `503` otherwise. The page that wakes the demo waits for it |

The rest are thin forwards to the backend with up-front checks: `POST /session`, `POST /admin/session`, `GET /me/disputes`, `GET /disputes/{id}`, `GET /meta/demo-scenarios`, `GET /meta/data`, `GET /admin/disputes*`, `POST /admin/disputes/{id}/transition` and `GET /admin/metrics`.

## Graph (`app/graph.py`)

`understand → decide → act → verify → respond | escalate`, with conditional edges. Flow control is code, and the model decides nothing.

- **`decide`** applies the guardrail before any tool.
- **`verify`** rereads the case from the backend before saying it was recorded, and escalates if it does not match (`verify_failed`).
- **Failures:** up to 3 attempts per tool, with a 2 s connection timeout (worst case ~6.9 s). If the backend does not answer, `outcome: unavailable` with a safe message and no changes.

## Guardrail (`app/guardrail.py`)

A decision table in code, not a prompt. It always escalates on: fraud or theft (es and pt), an `Approved` or `Pending` charge, an effective USD amount greater than or equal to `GUARDRAIL_MAX_USD` (500 by default) or unknown, ambiguity unresolved after 2 clarification rounds, and a classifier confidence below `INTENT_MIN_CONFIDENCE` (0.5 by default; the fraud override applies before this abstention). An out-of-scope request is **declined** (`outcome: declined`, with no case or handoff). It resolves alone only a `Declined` or `Reversed` transaction of the customer's own, which is the only candidate and is under the threshold. The detail and the order are in [`docs/WORKFLOW.md`](../docs/WORKFLOW.md).

When the candidate pool has 2 or more, `app/ranking.py` only **orders** them so that the most likely one is offered first. It adds or removes no candidates and does not change the 0, 1 or 2-and-more decision or the corroboration required to resolve.

## Language model (optional)

With `OPENROUTER_API_KEY`, the model does three things, and never decides policy:

1. **Classifying the intent** of a message (`app/intents.py`): a structured output `{intent, language, confidence}`, with the prompt version in the trace. Without a key, or if the response is not valid, the es and pt keywords are used.
2. **A second look for fraud** (`LLM.flags_fraud`), at the same time as the classification, on messages that look like a dispute or something out of scope. It can only add caution: a "yes" sends the case to a person, while a "no" or a failure leaves the phrase list in `guardrail.py` as it was.
3. **Drafting the reply for an already resolved case** (`app/llm.py`). The draft passes through `app/grounding.py` before it is sent: no deadlines or money promises, no numbers that are not in the facts, no customer identifiers, and with the case number. If it fails, the template in `app/replies.py` is sent. A model never writes escalations, clarifications or statuses.

Language is set by the classification (if the model says "mixed", the text resolves it with a single function, `replies.detect_language`). The trace records the source, the prompt version, the confidence and the latencies. The model client adds up tokens and cost (`LLM.usage`).

The held-out sets and evaluations are in `../ml/eval/` (intent classification and transaction ranking) and in `eval/` (the end-to-end system and the classifier). The results are in [`docs/EVALUATION.md`](../docs/EVALUATION.md) and [`docs/ML_FINDINGS.md`](../docs/ML_FINDINGS.md).

## Other modules

- `app/tools.py`: thin HTTP clients to the backend. Each call forwards the customer's or the admin's token.
- `app/ranking.py`: an interpretable ranker (difflib, amount, date and channel) that reorders ambiguous pools.
- `app/tracing.py`: every step to `agent.trace_log`. It never stores customer text or the model's reasoning. It is the audit evidence, and a trace failure does not break the conversation.
- `app/conversations.py`: stores each turn in `agent.conversation_messages` (what the customer wrote, the reply and its cards). It is the table a retention policy would apply to. Saving is best effort.
- `app/observability.py`: `X-Request-ID` and JSON logs.

## Configuration

See `.env.example`. The main ones: `BANK_URL`, `SESSION_JWT_SECRET` (shared with the backend), `GUARDRAIL_MAX_USD`, `OPENROUTER_API_KEY` and `OPENROUTER_MODEL`, `CORS_ALLOWED_ORIGINS` (exact origins, never `*`) and `PG_*` for the agent's tables.

## Tests

```bash
python -m pytest        # from agent/, with pytest and httpx; the backend and the model are mocked
PG_TEST_HOST=localhost PG_TEST_PORT=5433 PG_TEST_USER=postgres PG_TEST_PASSWORD=dev python -m pytest   # also the history SQL against PostgreSQL
```

They cover the three mandatory paths, the guardrail and its edges (the inclusive threshold), abstention on low confidence and candidate ordering, Portuguese, an invalid session, the retries, the checks on the model's draft, the isolation of history between customers and the OpenAPI contract.

Deployment: Cloud Run, see [`infra/gcp/envs/`](../infra/gcp/envs/).
