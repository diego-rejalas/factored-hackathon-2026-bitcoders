from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Query

from app.auth import get_current_admin
from app.db import BankStore, get_store
from app.routes import admin_disputes, customers, disputes, meta
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
  operational tables (`app.disputes`, `app.dispute_events`) are created at
  startup and receive a narrow idempotent CHECK/data repair. This is not a
  general-purpose migration framework.
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
            app.state.store = owned
            yield
            await owned.close()
        else:
            yield

    app = FastAPI(
        title="mock-banking-service",
        description=DESCRIPTION,
        version="0.2.0",
        lifespan=lifespan,
    )
    if store is not None:
        app.state.store = store
    app.include_router(session_router)
    app.include_router(customers.router)
    app.include_router(disputes.router)
    app.include_router(admin_disputes.router)
    app.include_router(meta.router)

    @app.get("/health", tags=["health"])
    async def health() -> dict:
        return {"status": "ok", "service": "backend"}

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
        Definitions follow spec/CRITERIA.md; rates are null ("not defined") without data."""
        return await store.admin_metrics(window_hours)

    return app


app = create_app()
