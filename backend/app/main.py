from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db import BankStore
from app.routes import customers, disputes
from app.auth import router as session_router

DESCRIPTION = """
Mock banking service (tool layer) for the Factored AI & Data Hackathon 2026
prototype. Sandbox limitations, stated explicitly:

- Login is a test session: `POST /session` checks `customer_id` +
  `document_number` against `gold.customers` and issues a short-lived JWT
  (HS256). No real identity provider is behind it.
- Reads come from the read-only `gold.*` tables published by the dbt pipeline;
  operational tables (`app.disputes`, `app.dispute_events`) are created at
  startup with `CREATE TABLE IF NOT EXISTS` instead of a real migration.
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
        version="0.1.0",
        lifespan=lifespan,
    )
    if store is not None:
        app.state.store = store
    app.include_router(session_router)
    app.include_router(customers.router)
    app.include_router(disputes.router)

    @app.get("/health", tags=["health"])
    async def health() -> dict:
        return {"status": "ok", "service": "backend"}

    return app


app = create_app()
