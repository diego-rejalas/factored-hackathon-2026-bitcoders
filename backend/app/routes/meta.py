from fastapi import APIRouter, Depends

from app.auth import get_current_admin
from app.db import get_store

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("/data")
async def meta_data(
    admin: str = Depends(get_current_admin),
    store=Depends(get_store),
) -> dict:
    """Data freshness for the admin console: gold.* counts plus the last pipeline run
    (ops.etl_runs). The snapshot is static by design — see docs/ARCHITECTURE.md."""
    return await store.data_freshness()


@router.get("/demo-scenarios")
async def demo_scenarios(store=Depends(get_store)) -> dict:
    """Deterministic demo picks so a demo/video can guarantee the four workflow paths
    (auto-resolved, ambiguous, fraud, threshold). Public by design: it only surfaces the
    same fields the test login asks for (customer_id, document_number, name) and never
    any fraud column. Sandbox aid, documented as such."""
    return {"scenarios": await store.demo_scenarios()}
