import os
import uuid
from contextlib import asynccontextmanager

import jwt
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import app.replies as replies
from app.observability import RequestLogMiddleware
from app.graph import build_graph
from app.llm import LLM
from app.tools import ToolError, bank_tools_from_env
from app.conversations import Conversations
from app.tracing import Tracer

DESCRIPTION = """
Conversational agent + deterministic guardrail for the Factored AI & Data
Hackathon 2026 prototype. The frontend only ever knows this service's URL:
`POST /chat` runs the graph, `POST /session` and the `/admin/*` routes are
thin proxies to the backend (which re-validates every token), and
`/admin/agent-metrics` + `/admin/conversations/{id}/trace` are served from
`agent.trace_log`, which this service owns. Limitations, stated explicitly:

- The LangGraph checkpointer is in memory: conversation context is lost on
  redeploy (accepted for the hackathon, documented as a limitation). The
  trace and the handoff survive in Postgres even when the conversation does.
- Tracing goes to `agent.trace_log` (best-effort); no chain-of-thought and
  no user text is ever logged — only structured step metadata.
- The agent never reads Postgres directly for banking data: everything
  travels through the backend HTTP tools, forwarding the user's token.
- Admin credentials are sandbox credentials (backend ADMIN_USERS); the demo
  login is rate-limited in memory, per process.
"""


class ChatRequest(BaseModel):
    session_token: str = Field(min_length=1)
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = Field(default=None, max_length=100)
    transaction_id: str | None = Field(
        default=None,
        max_length=100,
        description="The transaction the customer picked in the app. The backend checks it is theirs; one that is not is ignored.",
    )


class ChatResponse(BaseModel):
    reply: str
    conversation_id: str
    case_id: str | None = Field(default=None, description="The dispute case this turn opened or found, if any.")
    case_status: str | None = None
    outcome: str
    handoff: dict | None = None
    candidates: list[dict] | None = None
    case: dict | None = None
    reason: str | None = None
    language: str | None = None


class SessionRequest(BaseModel):
    customer_id: str = Field(min_length=1)
    document_number: str = Field(min_length=1)


class AdminSessionRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class AdminTransitionRequest(BaseModel):
    action: str = Field(pattern="^(claim|close)$")
    note: str = Field(min_length=1, max_length=2000)
    resolution: str | None = Field(default=None)


def _precheck_token(token: str) -> None:
    """Fail fast on invalid/expired tokens when the shared secret is set.
    The backend re-validates anyway (double enforcement)."""
    secret = os.environ.get("SESSION_JWT_SECRET")
    if not secret:
        return
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"], issuer="backend-sandbox")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired session token")
    if payload.get("role", "customer") != "customer":
        raise HTTPException(status_code=403, detail="Customer role required")


def _customer_id(token: str) -> str | None:
    """The customer a verified token belongs to. None when the shared secret is not configured (local runs
    without it): nothing is then saved or listed, because there is no identity to scope it to."""
    secret = os.environ.get("SESSION_JWT_SECRET")
    if not secret:
        return None
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"], issuer="backend-sandbox")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired session token")
    return payload.get("sub")


def _require_admin_local(token: str) -> None:
    """Local admin validation for the endpoints this service owns. Unlike the
    proxies, there is no backend hop behind these, so the role check happens here."""
    secret = os.environ.get("SESSION_JWT_SECRET")
    if not secret:
        raise HTTPException(
            status_code=503, detail="Admin validation unavailable (SESSION_JWT_SECRET not set)"
        )
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"], issuer="backend-sandbox")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired session token")
    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer session token")
    return authorization[7:].strip()


def _precheck_admin(authorization: str | None) -> None:
    """Fail fast on non-admin tokens before proxying; the backend enforces again."""
    secret = os.environ.get("SESSION_JWT_SECRET")
    token = _bearer(authorization)
    if not secret:
        return
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"], issuer="backend-sandbox")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired session token")
    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")


def create_app(tools=None, tracer=None, llm=None, conversations=None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if tracer is None:
            owned = await Tracer.connect()
            app.state.tools = tools or bank_tools_from_env()
            app.state.llm = llm or LLM()
            app.state.tracer = owned
            app.state.conversations = conversations or Conversations(owned.pool)
            await app.state.conversations.init_schema()
            app.state.graph = build_graph(app.state.tools, owned, app.state.llm)
            yield
            await owned.close()
        else:
            yield

    app = FastAPI(
        title="banking-support-agent",
        description=DESCRIPTION,
        version="0.2.0",
        lifespan=lifespan,
    )

    # The chat UI calls this service from the browser, from another origin. Allowed origins come
    # from CORS_ALLOWED_ORIGINS (comma separated, exact origins). Never "*": the session token
    # travels in the request body, and an open policy would let any site drive a logged-in chat.
    origins = [o.strip().rstrip("/") for o in os.environ.get("CORS_ALLOWED_ORIGINS", "").split(",") if o.strip()]
    if "*" in origins:
        raise RuntimeError("CORS_ALLOWED_ORIGINS must list exact origins, not '*'")
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
            expose_headers=["X-Request-ID"],
            max_age=600,
        )
    app.add_middleware(RequestLogMiddleware, service="agent")

    if tools is not None or tracer is not None or llm is not None:
        app.state.tools = tools or bank_tools_from_env()
        app.state.tracer = tracer if tracer is not None else Tracer(None)
        app.state.conversations = conversations or Conversations(None)
        app.state.llm = llm or LLM()
        app.state.graph = build_graph(app.state.tools, app.state.tracer, app.state.llm)

    @app.get("/health", tags=["health"])
    async def health() -> dict:
        return {"status": "ok", "service": "agent"}

    @app.post("/session", tags=["session"])
    async def session(body: SessionRequest) -> dict:
        try:
            return await app.state.tools.login(body.customer_id, body.document_number)
        except ToolError as error:
            raise HTTPException(status_code=error.status_code, detail=error.detail)

    @app.post("/chat", response_model=ChatResponse, tags=["chat"])
    async def chat(body: ChatRequest) -> ChatResponse:
        _precheck_token(body.session_token)
        conversation_id = body.conversation_id or str(uuid.uuid4())
        customer_id = _customer_id(body.session_token)
        run_id = str(uuid.uuid4())
        try:
            result = await app.state.graph.ainvoke(
                {
                    "session_token": body.session_token,
                    "message": body.message,
                    "conversation_id": conversation_id,
                    "run_id": run_id,
                    # Always set: the conversation keeps its state between turns, and a turn without a pick must
                    # not inherit the previous one's.
                    "selected_transaction_id": body.transaction_id,
                },
                # The graph's memory is keyed by customer too: a conversation id someone else guessed must not
                # land in another customer's thread.
                config={"configurable": {"thread_id": f"{customer_id}:{conversation_id}" if customer_id else conversation_id}},
            )
        except ToolError as error:
            if error.status_code == 401:
                raise HTTPException(status_code=401, detail="Invalid or expired session token")
            # The banking service could not be reached after the bounded retries, or failed. A safe answer, not a
            # stack trace: nothing was changed, and the customer is told so. The outcome says it was not handled.
            return ChatResponse(
                reply=replies.unavailable_reply(replies.detect_language(body.message)),
                conversation_id=conversation_id,
                outcome="unavailable",
            )
        case = result.get("case") or {}
        response = ChatResponse(
            reply=result.get("reply", ""),
            conversation_id=conversation_id,
            case_id=str(case["case_id"]) if case.get("case_id") else None,
            case_status=case.get("status"),
            outcome=result.get("outcome", "resolved"),
            handoff=result.get("handoff"),
            candidates=result.get("candidates"),
            case=result.get("case"),
            reason=result.get("reason"),
            language=result.get("language"),
        )
        if customer_id:
            await app.state.conversations.save_turn(
                customer_id, conversation_id, body.message, response.reply, response.model_dump(mode="json")
            )
        return response

    # --- customer: own conversations (the history next to "My cases") ------------------------------

    @app.get("/me/conversations", tags=["conversations"])
    async def my_conversations(authorization: str | None = Header(default=None)) -> list:
        token = _bearer(authorization)
        _precheck_token(token)
        customer_id = _customer_id(token)
        return await app.state.conversations.recent(customer_id) if customer_id else []

    @app.get("/me/conversations/{conversation_id}", tags=["conversations"])
    async def my_conversation(conversation_id: str, authorization: str | None = Header(default=None)) -> dict:
        token = _bearer(authorization)
        _precheck_token(token)
        customer_id = _customer_id(token)
        messages = await app.state.conversations.messages(customer_id, conversation_id) if customer_id else []
        if not messages:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return {"conversation_id": conversation_id, "messages": messages}

    # --- customer: own cases (for the "Mis casos" panel) --------------------------------------

    @app.get("/me/disputes", tags=["disputes"])
    async def my_disputes(authorization: str | None = Header(default=None)) -> list:
        token = _bearer(authorization)
        _precheck_token(token)
        try:
            return await app.state.tools.list_disputes(token)
        except ToolError as error:
            raise HTTPException(status_code=error.status_code, detail=error.detail)

    @app.get("/disputes/{case_id}", tags=["disputes"])
    async def get_dispute(
        case_id: str, authorization: str | None = Header(default=None)
    ) -> dict:
        token = _bearer(authorization)
        _precheck_token(token)
        try:
            return await app.state.tools.get_dispute(token, case_id)
        except ToolError as error:
            raise HTTPException(status_code=error.status_code, detail=error.detail)

    # --- meta: public demo aid + data freshness (proxied) --------------------------------------

    @app.get("/meta/demo-scenarios", tags=["meta"])
    async def demo_scenarios() -> dict:
        try:
            return await app.state.tools.get_demo_scenarios()
        except ToolError as error:
            raise HTTPException(status_code=error.status_code, detail=error.detail)

    @app.get("/meta/data", tags=["meta"])
    async def meta_data(authorization: str | None = Header(default=None)) -> dict:
        token = _bearer(authorization)
        _precheck_admin(authorization)
        try:
            return await app.state.tools.get_meta_data(token)
        except ToolError as error:
            raise HTTPException(status_code=error.status_code, detail=error.detail)

    # --- admin console: thin proxies to the backend ----------------------------------------------

    @app.post("/admin/session", tags=["admin"])
    async def admin_session(body: AdminSessionRequest) -> dict:
        try:
            return await app.state.tools.admin_login(body.username, body.password)
        except ToolError as error:
            raise HTTPException(status_code=error.status_code, detail=error.detail)

    @app.get("/admin/disputes", tags=["admin"])
    async def admin_disputes(
        status: str | None = None,
        customer_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
        authorization: str | None = Header(default=None),
    ) -> dict:
        _precheck_admin(authorization)
        token = _bearer(authorization)
        try:
            return await app.state.tools.admin_list_disputes(
                token, status=status, customer_id=customer_id, limit=limit, offset=offset
            )
        except ToolError as error:
            raise HTTPException(status_code=error.status_code, detail=error.detail)

    @app.get("/admin/disputes/{case_id}", tags=["admin"])
    async def admin_dispute(
        case_id: str, authorization: str | None = Header(default=None)
    ) -> dict:
        _precheck_admin(authorization)
        token = _bearer(authorization)
        try:
            return await app.state.tools.admin_get_dispute(token, case_id)
        except ToolError as error:
            raise HTTPException(status_code=error.status_code, detail=error.detail)

    @app.post("/admin/disputes/{case_id}/transition", tags=["admin"])
    async def admin_transition(
        case_id: str,
        body: AdminTransitionRequest,
        authorization: str | None = Header(default=None),
    ) -> dict:
        _precheck_admin(authorization)
        token = _bearer(authorization)
        try:
            return await app.state.tools.admin_transition(
                token, case_id, body.action, body.note, body.resolution
            )
        except ToolError as error:
            raise HTTPException(status_code=error.status_code, detail=error.detail)

    @app.get("/admin/metrics", tags=["admin"])
    async def admin_metrics(
        window_hours: int | None = Query(default=None, alias="window", ge=1),
        authorization: str | None = Header(default=None),
    ) -> dict:
        _precheck_admin(authorization)
        token = _bearer(authorization)
        try:
            return await app.state.tools.admin_metrics(token, window_hours=window_hours)
        except ToolError as error:
            raise HTTPException(status_code=error.status_code, detail=error.detail)

    # --- admin console: served from agent.trace_log (this service owns the schema) -------------

    @app.get("/admin/agent-metrics", tags=["admin"])
    async def agent_metrics(
        window_hours: int | None = None,
        authorization: str | None = Header(default=None),
    ) -> dict:
        _require_admin_local(_bearer(authorization))
        return await app.state.tracer.metrics(window_hours=window_hours)

    @app.get("/admin/conversations/{conversation_id}/trace", tags=["admin"])
    async def conversation_trace(
        conversation_id: str, authorization: str | None = Header(default=None)
    ) -> dict:
        _require_admin_local(_bearer(authorization))
        return {
            "conversation_id": conversation_id,
            "rows": await app.state.tracer.conversation_trace(conversation_id),
        }

    return app


app = create_app()
