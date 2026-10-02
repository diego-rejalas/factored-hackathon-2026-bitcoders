from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from app.auth import get_current_customer
from app.db import get_store
from app.schemas import Dispute

# Registered twice (see main.py): at the root, where the agent calls them, and under /v1 for the web app.
router = APIRouter(prefix="/disputes", tags=["disputes"])


class DisputeCreate(BaseModel):
    transaction_id: str = Field(min_length=1)
    reason_code: str = Field(
        min_length=1,
        description="e.g. unrecognized_charge, duplicate, failed, other",
    )
    summary: str = Field(min_length=1, max_length=2000)


class EscalateRequest(BaseModel):
    handoff: dict = Field(
        description="Structured handoff payload for a human agent (request, verified facts, actions taken, evidence, open questions)"
    )


class ResolveRequest(BaseModel):
    resolution: dict = Field(
        description="What the policy decided and the facts it rested on (rule applied, verified facts)."
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    responses={200: {"description": "The transaction already had a case: this is it, nothing new was created."}},
)
async def create_dispute(
    body: DisputeCreate,
    response: Response,
    idempotency_key: str | None = Header(default=None, max_length=120),
    customer_id: str = Depends(get_current_customer),
    store=Depends(get_store),
) -> dict:
    """One case per (customer, transaction): reporting the same transaction again returns the same case."""
    transaction = await store.get_transaction(customer_id, body.transaction_id)
    if transaction is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Transaction not found for this customer"
        )
    case, created = await store.create_dispute(
        customer_id,
        body.transaction_id,
        body.reason_code,
        body.summary,
        evidence={"transaction": transaction},
        idempotency_key=idempotency_key,
    )
    if not created:
        response.status_code = status.HTTP_200_OK
    return case


@router.get("", response_model=list[Dispute], response_model_exclude={"__all__": {"events"}})
async def list_disputes(
    status_filter: str | None = Query(
        default=None, alias="status", pattern="^(open|auto_resolved|escalated)$"
    ),
    limit: int = Query(default=20, ge=1, le=100),
    customer_id: str = Depends(get_current_customer),
    store=Depends(get_store),
) -> list[dict]:
    """The customer's own cases, newest first."""
    return await store.list_disputes(customer_id, status=status_filter, limit=limit)


@router.get("/{case_id}")
async def get_dispute(
    case_id: str,
    customer_id: str = Depends(get_current_customer),
    store=Depends(get_store),
) -> dict:
    dispute = await store.get_dispute(customer_id, case_id)
    if dispute is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dispute not found")
    dispute["events"] = await store.get_dispute_events(dispute["case_id"])
    return dispute


@router.post("/{case_id}/escalate")
async def escalate_dispute(
    case_id: str,
    body: EscalateRequest,
    customer_id: str = Depends(get_current_customer),
    store=Depends(get_store),
) -> dict:
    dispute = await store.escalate_dispute(customer_id, case_id, body.handoff)
    if dispute is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dispute not found")
    return dispute


@router.post("/{case_id}/resolve")
async def resolve_dispute(
    case_id: str,
    body: ResolveRequest,
    customer_id: str = Depends(get_current_customer),
    store=Depends(get_store),
) -> dict:
    """Record that the policy resolved the case without a person (open -> auto_resolved), once."""
    dispute = await store.resolve_dispute(customer_id, case_id, body.resolution)
    if dispute is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dispute not found")
    return dispute
