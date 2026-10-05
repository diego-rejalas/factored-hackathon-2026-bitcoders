# API contract

[Index](README.md) · [Workflow](WORKFLOW.md) · [Architecture](ARCHITECTURE.md) · [Data](DATA.md) · [API](API.md)

The contract of workflow A (transaction disputes) between **the web UI**, **the agent** and **the backend**, including the specialist console. Date: 2026-10-04, with the console and the customer's cases merged.

## How this contract is maintained

| Source | What it says | Who enforces it |
|---|---|---|
| `backend/tests/contract/openapi.json` and `agent/tests/contract/openapi.json` | Routes, parameters, bodies and response schemas. **The code generates it** | A test fails if the code generates something different. Changing the contract is a decision reviewed in the diff (`UPDATE_CONTRACT=1 python -m pytest tests/test_openapi_contract.py` regenerates it) |
| **This document** | What a schema cannot say: rules, states, call order, security, limits and assumptions | Review |

If this document and an OpenAPI file contradict each other, **the OpenAPI wins**, because the tests run it.

What the backend contract enforces with tests:
- the operations that do **not** require a session are exactly `GET /health`, `GET /ready`, `POST /session`, `POST /admin/session`, `POST /v1/auth/login`, `GET /v1/auth/demo-accounts` and `GET /meta/demo-scenarios`. This was checked by making `/v1/me` public and watching the test fail;
- no customer route receives a `customer_id` from the caller (the admin ones can filter by customer, because the role is what authorizes them);
- no schema has a field for `is_fraud`, `fraud_score`, `password_hash`, `credit_score` or `estimated_monthly_income`;
- the body of `POST /chat` cannot name a customer.

## 1. Who calls whom

```
Browser ─► ALB + Cloud Armor ─┬─► Frontend (Next.js)   pages: / (customer) and /admin (specialist)
                              └─► Agent  (/agent/*)    ◄── the browser calls it directly, with the session token
                                       │
                                       └─► Backend (private, Cloud Run ID token) ─► Cloud SQL
```

- **The web UI calls the agent from the browser** (`/session`, `/chat`, `/me/disputes`, `/disputes/{id}`, `/meta/demo-scenarios`, and `/admin/*` for the console). The agent forwards to the backend whatever is not its own.
- **The backend is private.** Only service accounts with `run.invoker` call it, with their ID token in `X-Serverless-Authorization`. `Authorization` stays free for the session token.
- **The agent** reads data only through the backend and never touches the customers' database. It writes only its own trace (`agent.trace_log`) and the conversation history.

## 2. Common conventions

| Topic | Rule |
|---|---|
| Format | JSON in UTF-8. Dates in ISO 8601 (timestamps with a zone end in `Z`) |
| Money | A **number** plus a separate `currency`. `amount_usd_effective` is `amount_usd` or, if it is missing and the currency is USD, `amount`. It is `null` if unknown and is **never treated as zero** |
| Identifiers | Opaque. `case_id` is a UUID. Transaction and product ids are dataset text |
| Session | `Authorization: Bearer <token>`. JWT HS256, issuer `backend-sandbox`. **Two roles:** `customer` (`sub` = `customer_id`, 2 hours) and `admin` (`sub` = username, `role=admin`, 8 hours by default). **A token of one role does not open the other's routes** (`403`). Identity always comes from the token |
| Traceability | Every backend and agent response carries `X-Request-ID`. If the request brings a valid one (8 to 100 characters of `A-Za-z0-9._-`) it is kept, and otherwise one is created. The agent forwards it to the backend. Each request writes one JSON log line with `severity`. `Authorization`, the query string and any body are **not** logged |
| Pagination | The `/v1` API paginates by **cursor** (`?limit=` from 1 to 100 and `?cursor=`). A cursor the service did not issue gives `422`. The admin inbox uses `limit` and `offset` |
| One case per transaction | Reporting again a transaction that already has a case (not `closed`) **returns that case**: the route answers `201` and the body is the case that already existed. Two simultaneous requests create only one. A case **without** a transaction is never a duplicate of another |
| Versions | `/v1` admits only non-breaking changes. The root routes are the UI's and the agent's, and their shape is frozen |

### Errors

The body is `{"detail": "<text>"}`. Validation errors (`422`) carry `{"detail": [{"loc": [...], "msg": "...", "type": "..."}]}`. The text includes no data from another customer.

| Code | When |
|---|---|
| `401` | The token is missing, malformed or expired. Also a login with wrong credentials (**the same response if the user does not exist**) |
| `403` | The token belongs to another role |
| `404` | It does not exist **or does not belong to the customer**. The two are indistinguishable on purpose |
| `409` | `resolve` on a case that is not `open`, or that changed state in the meantime |
| `422` | Invalid parameter or body |
| `429` | Five failed login attempts (`LOGIN_MAX_FAILED_ATTEMPTS`): the account is locked for 15 minutes. It carries `Retry-After` |
| `503` | `GET /ready` without a database. The admin login if `ADMIN_USERS` is empty |

## 3. Backend

The exact schema is in `backend/tests/contract/openapi.json`. Here is what each route does and what the schema does not say.

### 3.1 Root: the routes the UI and the agent use

| Route | Session | Does |
|---|---|---|
| `POST /session` `{customer_id, document_number}` | no | The customer's **sandbox** login: it validates against `gold.customers`. There is no identity provider behind it |
| `POST /admin/session` `{username, password}` | no | The specialist's login with `ADMIN_USERS` (bcrypt hashes, in Secret Manager). Five failures per IP and user lock it for 60 s |
| `GET /me`, `GET /me/transactions`, `GET /me/transactions/{id}` | customer | Minimal profile and own transactions (a simple list). Each transaction carries `response_meaning` |
| `GET /me/disputes` | customer | My cases, newest first (including closed ones and ones without a transaction) |
| `GET /me/conversations` | customer | My conversations, most recent first, with the title (the first thing the customer wrote). They belong to the agent: `agent.conversation_messages` |
| `GET /me/conversations/{id}` | customer | One full conversation (messages and the cards of each reply). 404 if it does not exist or belongs to another customer |
| `POST /disputes` `{transaction_id?, reason_code, summary}` | customer | Opens the case. `transaction_id` is **optional**: an escalation that could not be tied to a transaction is a case without a transaction |
| `GET /disputes/{case_id}` | customer | The case with its timeline (`events`) |
| `POST /disputes/{case_id}/escalate` `{handoff}` | customer | Called by the agent. It marks `escalated` and stores the handoff. It can be called on a case that is `open`, `auto_resolved` (the customer disputes the automatic resolution) or `escalated`. On one that is `in_progress` or `closed` it answers `409` and changes nothing: a specialist has it or closed it, and a new report does not reopen it |
| `POST /disputes/{case_id}/resolve` `{resolution}` | customer | Called by the agent. `resolution` is `no_charge_confirmed` or `reversal_confirmed`. It moves `open` to `auto_resolved`. Repeating it on one already `auto_resolved` returns it unchanged, and on any other state it gives `409`. **Humans never set `auto_resolved`** |
| `GET /meta/demo-scenarios` | no | Up to four deterministic demo scenarios, computed from the data (threshold, fraud, auto-resolved...). Public on purpose: it exposes only what the test login already asks for |
| `GET /health`, `GET /ready` | no | The process is alive / reaches the database |

### 3.2 Admin (`role=admin`)

| Route | Does |
|---|---|
| `GET /admin/disputes?status=&customer_id=&limit=&offset=` | Inbox with customer, language and handoff reason. `status=active` includes `escalated` and `in_progress` |
| `GET /admin/disputes/{case_id}` | Detail: handoff, `conversation_id` and audited events |
| `POST /admin/disputes/{case_id}/transition` `{action, note, resolution?}` | `claim`: `open` or `escalated` to `in_progress`. `close`: `in_progress` to `closed`, with a **required note and a required resolution**. Each transition adds an event |
| `GET /admin/metrics?window=<hours>` | Totals by status, safe automatic resolution **with its denominator**, escalations, human closures, language and reason. With no cases the rate is `null` ("not defined"), not zero |
| `GET /meta/data` | Freshness: `gold.*` counts, the snapshot edge and the last run in `ops.etl_runs` |

### 3.3 `/v1`: the surface for a web app that does not use the agent directly

The current UI **does not use it**. It is kept because tests and this contract cover it, and it is the path to a future BFF.

| Route | Does |
|---|---|
| `POST /v1/auth/login` `{username, password}` | Username and password (argon2id). Five failures lock the account, and a successful login resets the count. The same response if the user does not exist |
| `GET /v1/auth/demo-accounts` | Demo accounts and their shared password (public on purpose). **`404` unless `DEMO_ACCOUNTS_ENABLED=true`** |
| `GET /v1/me`, `/v1/me/summary` | Profile, and balances by currency (**deposits and credit kept apart, never netted**) with the latest transactions and the active cases |
| `GET /v1/me/products` and `/{id}` | Products with the number **masked** (`****1234`) and `kind` (`deposit`, `credit`, `other`) |
| `GET /v1/me/transactions` and `/{id}` | `{items, next_cursor}` with filters `product_id`, `status`, `merchant`, `from`, `to`. Each row carries `case_id`, `dispute_status` and `response_meaning` |
| `GET /v1/disputes`, `/v1/disputes/{id}`, `POST /v1/disputes…` | The same dispute routes as the root |

**`response_meaning`** (`{es, pt}` or `null`) is the standard (ISO 8583) meaning of `response_code`. **It is an assumption:** the organizer does not define the codes, and the dataset has only `00`, `05`, `14`, `51` and `54` (and empty in ~5%). An empty or unknown code gives `null`, and no reason is invented.

**`kind` and balances:** the organizer's dictionary does not define `current_balance` either. For a deposit it is what the customer holds. **For credit it is inferred to be what they owe** (there are 7,510 credit products with a balance above their limit, which only makes sense if the balance is the amount used).

## 4. Case states and who changes them

```
              ┌─── resolve (agent) ──► auto_resolved ──┐
   open ──────┤                                         ├── escalate (agent) ──► escalated ── claim (specialist) ──► in_progress ── close ──► closed
              └──────────── escalate (agent) ──────────┘
```

| State | Means | Set by |
|---|---|---|
| `open` | Just opened, in progress | `POST /disputes` |
| `auto_resolved` | The policy resolved it **and it was recorded** (`no_charge_confirmed` or `reversal_confirmed`) | only the agent, through `resolve` |
| `escalated` | Waiting for a specialist, with its handoff | the agent, through `escalate` |
| `in_progress` | A specialist took it | the specialist, through `claim` |
| `closed` | The specialist closed it, with a note and a resolution | the specialist, through `close`. **A `closed` case does not count**: the transaction can be reported again |

Escalations **without a transaction** (fraud with no chosen transaction, ambiguity that was not resolved) are cases with a null `transaction_id`, so they reach the specialist's inbox just the same. An escalated case has no `resolved_at`: that is only for what was resolved.

The timeline (`events`) only grows: `created`, then `auto_resolved`, `escalated`, `claimed`, `closed`.

## 5. Agent

The exact schema is in `agent/tests/contract/openapi.json`.

### `POST /chat`

Request: `{session_token, message, conversation_id?, transaction_id?}`. The token goes in the body, not in a header.

- **`transaction_id`** is the transaction the customer picked. It identifies the transaction better than any text: it is not searched for and the customer is not asked to confirm it. **Everything else still applies** (the USD 500 threshold, an already approved charge, an unknown amount). The backend verifies that it belongs to the customer, and **someone else's is ignored** as if nothing had been picked, with no error and no data from another customer. It is not carried into the next turn. *The current UI does not use it: it builds a sentence ("It was the charge of X at Y") when a candidate is picked.*
- **`conversation_id`** continues a conversation. If it is missing, one is created and returned.

Response: `{reply, conversation_id, outcome, handoff, case_id, case_status, case, candidates, reason, language}`. `case_id` and `case_status` are the case that this turn opened or found. `case`, `candidates`, `reason` and `language` are what the UI uses for its cards.

| `outcome` | Means | Case |
|---|---|---|
| `resolved` | The policy resolved it, or the agent answered (a greeting, the status of a case) | `auto_resolved` if there was a dispute |
| `clarify` | There are 0 or several candidate transactions, or the key detail is missing (with `candidates` if there are any). One question per turn, at most 2, then it escalates | none |
| `escalated` | Goes to a person | **the case, `escalated`**, tied to the transaction if possible and with no transaction if not |
| `declined` | The request is not a dispute (a loan, the balance, the weather...). It is answered with a fixed text in the customer's language, **with no case and no handoff**. It does not say a person has it, because nobody would | none |
| `unavailable` | **It could not be verified** because the banking service failed after the retries. Nothing was changed, and the customer can retry | none |

**Automatic resolution is closed or escalated.** After opening the case, the agent rereads it, marks it `auto_resolved` through `resolve`, and rereads it again. **If it cannot be marked, the turn becomes an escalation with reason `verify_failed`.** "Resolved" is never a promise that nobody recorded.

`unavailable` arrives with `200` and a plain text in the customer's language (es or pt), not with a `502`. An expired session is still `401`.

`handoff` (when `outcome` is `escalated`): `reason`, `limitation`, `request` (`{es, pt}`), `customer_language`, `conversation_id`, `verified_facts`, `actions_taken`, `evidence`, `open_questions`, and `case_id` and `escalated_in_backend` if there was a case. Reasons: `amount_threshold`, `amount_unknown`, `posted_charge_disputed`, `fraud_suspected`, `out_of_scope`, `ambiguity_unresolved`, `verify_failed`.

**Decline reason:** if the transaction is `Declined` and its code is known, the reply states it with the code and says it is the standard meaning. With an empty or unknown code it adds nothing.

**The agent's retries to the backend:** up to 3 attempts with short waits, on a connection failure or `502`, `503`, `504`, and **never** on a `4xx`. Repeating everything is safe because the writes are idempotent. The connection has its own 2 s limit, and **the worst case measured, with the backend down, was 6.9 s** until `unavailable` was returned.

### The agent's other routes

They are thin forwards to the backend with the same session, with up-front checks that fail fast: `GET /me/disputes`, `GET /disputes/{id}`, `GET /meta/demo-scenarios`, `GET /meta/data` and, for the specialist, `POST /admin/session`, `GET /admin/disputes`, `GET /admin/disputes/{id}` and `POST /admin/disputes/{id}/transition`, plus `GET /admin/metrics`. **Two routes belong to the agent itself:** `GET /admin/agent-metrics` (outcomes, containment, p50 and p95 latency, intents and languages, from `agent.trace_log`) and `GET /admin/conversations/{id}/trace` (the steps of one conversation). The customer routes `GET /me/conversations` and `GET /me/conversations/{id}` also belong to the agent. They store what the customer wrote and what they were answered, and are read only with the customer from the verified token (this table carries the retention policy, and `trace_log` still has no user text). `POST /session` forwards the backend's login.

## 6. End-to-end flows

**Customer:** `POST /session`, then `POST /chat` (with `message` and, if they picked one, `transaction_id`), then `resolved` with its case, or `escalated` with its case and handoff. After that, `GET /me/disputes` for "Mis casos" and `GET /me/conversations` for recent conversations, which reopen with `GET /me/conversations/{id}`.

**Specialist:** `POST /admin/session`, then `GET /admin/disputes?status=active`, then the detail (handoff and events), then `claim`, then `close` with a note and a resolution, then `GET /admin/metrics`.

## 7. A possible evolution: a backend-for-frontend (BFF) for the web

It does not exist, and the submission does not need it. If the UI stopped calling the agent from the browser, the Next server would store the token in an `httpOnly` cookie and call `/v1` and `/chat`. That would **force infrastructure changes**: today the agent accepts only the load balancer's traffic, so the Next server could not call it. The agent would have to become private like the backend, with the frontend as the invoker. That is why `/v1` is kept.

## 8. Limits and assumptions

- **The decline reason (`response_meaning`) is the ISO 8583 standard**, not a definition from the organizer. The reply says so.
- **A credit product's balance is interpreted as the amount owed** (inferred). The dataset has no MXN although half of the customers are Mexican, so the currency is shown as stored.
- **There is no real identity service.** The customer's login (`customer_id` and document) and the specialist's are demo logins. The specialist's has an attempt limit per process. The contract declares this and does not hide it.
- **The agent's conversation state lives in each instance's memory.** With more than one instance, a turn can land on another one and lose the thread (the clarification context is lost, not the cases, which are in the database). Real production needs a shared store.
- **The specialist login's attempt limit lives in each process's memory** (with several instances, each one counts separately). The limit of `POST /v1/auth/login` is in the database, per account. `POST /session` (customer and document) has no attempt limit.
