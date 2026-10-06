import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query

from app.auth import get_current_admin
from app.db import BankStore, get_store
from app.demo import seed_demo_accounts
from app.observability import RequestLogMiddleware
from app.routes import admin_disputes, customers, disputes, meta, v1
from app.auth import router as session_router

DESCRIPTION = """
Mock banking service (tool layer) for the Factored AI & Data Hackathon 2026
prototype. Sandbox limitations, stated explicitly:

- Login is a test session: `POST /session` checks `customer_id` +
  `document_number` against `gold.customers` and issues a short-lived JWT
  (HS256). No real identity provider is behind it.
- Admin login (`POST /admin/session`) checks credentials against `ADMIN_USERS`
  (bcrypt hashes, in-memory rate limit, single-process sandbox limitation).
  Admins work an inbox of escalated cases with audited transitions
  (claim -> in_progress -> closed); they never set `auto_resolved`.
- `GET /meta/demo-scenarios` is a public demo aid: it surfaces only the fields
  the test login itself asks for (customer_id, document_number, name), never
  fraud columns.
- Reads come from the read-only `gold.*` tables published by the dbt pipeline;
  operational tables (`app.*`) are built by the versioned SQL migrations in
  `app/migrations`, applied at startup under an advisory lock.
- `/v1` is what the web app uses (user name and password login, products,
  paginated history, summary). The routes at the root are the agent's.
- No money is ever moved: disputes only explain, document and escalate.
- Fraud ground truth (`is_fraud`/`fraud_score`) is not part of `gold.transactions`
  and is never exposed here.
"""


def create_app(store: BankStore | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if store is None:
            owned = await BankStore.create()
            await owned.init_schema()
            if os.environ.get("DEMO_ACCOUNTS_ENABLED", "false").lower() == "true" and os.environ.get("DEMO_PASSWORD"):
                await seed_demo_accounts(owned, os.environ["DEMO_PASSWORD"])
            app.state.store = owned
            # Warm the demo scenarios now, so the first visitor to the login does not wait for them.
            warm = asyncio.create_task(owned.demo_scenarios())
            warm.add_done_callback(lambda task: task.cancelled() or task.exception())
            yield
            warm.cancel()
            await owned.close()
        else:
            yield

    app = FastAPI(
        title="mock-banking-service",
        description=DESCRIPTION,
        version="0.2.0",
        lifespan=lifespan,
    )
    app.add_middleware(RequestLogMiddleware, service="backend")
    if store is not None:
        app.state.store = store
    # Root: the routes the agent calls. /v1: what the web app uses, plus the same dispute routes.
    app.include_router(session_router)
    app.include_router(customers.router)
    app.include_router(disputes.router)
    app.include_router(v1.router, prefix="/v1")
    app.include_router(disputes.router, prefix="/v1")
    app.include_router(admin_disputes.router)
    app.include_router(meta.router)

    @app.get("/health", tags=["health"])
    async def health() -> dict:
        return {"status": "ok", "service": "backend"}

    @app.get("/ready", tags=["health"])
    async def ready() -> dict:
        """Liveness says the process is up; readiness says it can reach the database."""
        try:
            ok = await app.state.store.ping()
        except Exception:  # noqa: BLE001
            ok = False
        if not ok:
            raise HTTPException(503, "database unavailable")
        return {"status": "ready", "service": "backend"}
    @app.get("/admin/metrics", tags=["admin"])
    async def admin_metrics(
        window_hours: int | None = Query(
            default=None,
            ge=1,
            alias="window",
            description="Hours back from now; omit for all time",
        ),
        admin: str = Depends(get_current_admin),
        store=Depends(get_store),
    ) -> dict:
        """Outcome metrics from app.disputes, with denominators always reported.
        Definitions follow docs/CRITERIA.md; rates are null ("not defined") without data."""
        return await store.admin_metrics(window_hours)

    return app


app = create_app()
