import os
import uuid
from contextlib import asynccontextmanager

import jwt
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import app.replies as replies
from app.observability import RequestLogMiddleware
from app.graph import build_graph
from app.llm import LLM
from app.tools import ToolError, bank_tools_from_env
from app.tracing import Tracer

DESCRIPTION = """
Conversational agent + deterministic guardrail for the Factored AI & Data
Hackathon 2026 prototype. Exposes `POST /chat` to the frontend and a thin
`POST /session` proxy to the backend, so the frontend only ever needs this
service's URL. Limitations, stated explicitly:

- The LangGraph checkpointer is in memory: conversation context is lost on
  redeploy (accepted for the hackathon, documented as a limitation).
- Tracing goes to `agent.trace_log` (best-effort); no chain-of-thought is
  ever logged.
- The agent never reads Postgres directly: all banking data travels through
  the backend HTTP tools, forwarding the user's session token.
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


class SessionRequest(BaseModel):
    customer_id: str = Field(min_length=1)
    document_number: str = Field(min_length=1)


def _precheck_token(token: str) -> None:
    """Fail fast on invalid/expired tokens when the shared secret is set.
    The backend re-validates anyway (double enforcement)."""
    secret = os.environ.get("SESSION_JWT_SECRET")
    if not secret:
        return
    try:
        jwt.decode(token, secret, algorithms=["HS256"], issuer="backend-sandbox")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired session token")


def create_app(tools=None, tracer=None, llm=None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if tracer is None:
            owned = await Tracer.connect()
            app.state.tools = tools or bank_tools_from_env()
            app.state.llm = llm or LLM()
            app.state.tracer = owned
            app.state.graph = build_graph(app.state.tools, owned, app.state.llm)
            yield
            await owned.close()
        else:
            yield

    app = FastAPI(
        title="banking-support-agent",
        description=DESCRIPTION,
        version="0.1.0",
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
                config={"configurable": {"thread_id": conversation_id}},
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
        return ChatResponse(
            reply=result.get("reply", ""),
            conversation_id=conversation_id,
            case_id=str(case["case_id"]) if case.get("case_id") else None,
            case_status=case.get("status"),
            outcome=result.get("outcome", "resolved"),
            handoff=result.get("handoff"),
        )

    return app


app = create_app()
