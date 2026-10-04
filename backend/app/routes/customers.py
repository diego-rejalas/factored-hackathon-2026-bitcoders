from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth import get_current_customer
from app.db import get_store
from app.schemas import Customer, Transaction

router = APIRouter(prefix="/me", tags=["customers"])


@router.get("", response_model=Customer)
async def get_me(
    customer_id: str = Depends(get_current_customer),
    store=Depends(get_store),
) -> dict:
    profile = await store.get_profile(customer_id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")
    return profile


@router.get("/transactions", response_model=list[Transaction])
async def list_transactions(
    status_filter: str | None = Query(default=None, alias="status"),
    merchant: str | None = Query(default=None, min_length=2),
    days: int | None = Query(default=None, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    customer_id: str = Depends(get_current_customer),
    store=Depends(get_store),
) -> list[dict]:
    return await store.list_transactions(
        customer_id, status=status_filter, merchant=merchant, days=days, limit=limit
    )


@router.get("/transactions/{transaction_id}", response_model=Transaction)
async def get_transaction(
    transaction_id: str,
    customer_id: str = Depends(get_current_customer),
    store=Depends(get_store),
) -> dict:
    transaction = await store.get_transaction(customer_id, transaction_id)
    if transaction is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Transaction not found for this customer"
        )
    return transaction


@router.get("/disputes")
async def list_my_disputes(
    customer_id: str = Depends(get_current_customer),
    store=Depends(get_store),
) -> list[dict]:
    return await store.list_customer_disputes(customer_id)
