from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.auth import get_current_customer
from app.db import get_store
from app.schemas import Dispute, DisputeDetail

# Registered twice (see main.py): at the root, where the agent and the web app call them, and under /v1.
router = APIRouter(prefix="/disputes", tags=["disputes"])


class DisputeCreate(BaseModel):
    transaction_id: str | None = Field(default=None, min_length=1)
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
    resolution: str = Field(
        pattern="^(no_charge_confirmed|reversal_confirmed)$",
        description="no_charge_confirmed for Declined, reversal_confirmed for Reversed",
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=Dispute)
async def create_dispute(
    body: DisputeCreate,
    customer_id: str = Depends(get_current_customer),
    store=Depends(get_store),
) -> dict:
    """Open the case. One per (customer, transaction): reporting the same transaction again returns that case."""
    evidence = {}
    if body.transaction_id is not None:
        transaction = await store.get_transaction(customer_id, body.transaction_id)
        if transaction is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "Transaction not found for this customer"
            )
        evidence = {"transaction": transaction}
    return await store.create_dispute(
        customer_id,
        body.transaction_id,
        body.reason_code,
        body.summary,
        evidence=evidence,
    )


@router.get("", response_model=list[Dispute])
async def list_disputes(
    status_filter: str | None = Query(
        default=None, alias="status", pattern="^(open|auto_resolved|escalated|in_progress)$"
    ),
    limit: int = Query(default=20, ge=1, le=100),
    customer_id: str = Depends(get_current_customer),
    store=Depends(get_store),
) -> list[dict]:
    """The customer's own cases, newest first."""
    return await store.list_disputes(customer_id, status=status_filter, limit=limit)


@router.get("/{case_id}", response_model=DisputeDetail)
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


@router.post("/{case_id}/escalate", response_model=Dispute)
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


@router.post("/{case_id}/resolve", response_model=Dispute)
async def resolve_dispute(
    case_id: str,
    body: ResolveRequest,
    customer_id: str = Depends(get_current_customer),
    store=Depends(get_store),
) -> dict:
    """System (agent) resolution after verifying the case: 'open' -> 'auto_resolved'.
    Only the safe path ever calls this; humans close cases through /admin transitions."""
    dispute = await store.get_dispute(customer_id, case_id)
    if dispute is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dispute not found")
    if dispute["status"] == "auto_resolved":
        return dispute
    if dispute["status"] != "open":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Case in status '{dispute['status']}' cannot be auto-resolved",
        )
    resolved = await store.resolve_dispute(customer_id, case_id, body.resolution)
    if resolved is None:  # raced with an escalation
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Case changed state, retry"
        )
    return resolved
