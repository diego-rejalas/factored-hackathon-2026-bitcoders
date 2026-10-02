from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth import get_current_customer
from app.db import get_store

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


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_dispute(
    body: DisputeCreate,
    customer_id: str = Depends(get_current_customer),
    store=Depends(get_store),
) -> dict:
    transaction = await store.get_transaction(customer_id, body.transaction_id)
    if transaction is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Transaction not found for this customer"
        )
    return await store.create_dispute(
        customer_id,
        body.transaction_id,
        body.reason_code,
        body.summary,
        evidence={"transaction": transaction},
    )


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
