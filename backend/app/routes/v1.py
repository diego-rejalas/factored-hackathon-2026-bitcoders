"""The API the web app uses (through its server side). Disputes are shared with the agent's routes: see main.py."""

import os
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth import _unauthorized, create_session_token, SESSION_TTL_MINUTES
from app.auth import get_current_customer
from app.db import get_store
from app.passwords import DUMMY_HASH, verify_password
from app.schemas import (
    Customer,
    DataMeta,
    DemoAccounts,
    LoginRequest,
    LoginResponse,
    Product,
    Summary,
    Transaction,
    TransactionPage,
)

router = APIRouter(tags=["v1"])

MAX_FAILED_ATTEMPTS = int(os.environ.get("LOGIN_MAX_FAILED_ATTEMPTS", "5"))
LOCK_MINUTES = int(os.environ.get("LOGIN_LOCK_MINUTES", "15"))


@router.post("/auth/login", response_model=LoginResponse)
async def login(body: LoginRequest, store=Depends(get_store)) -> dict:
    """User name and password. The answer is the same whether the user exists or not."""
    credentials = await store.get_credentials(body.username.strip())
    now = datetime.now(timezone.utc)
    locked_until = credentials["locked_until"] if credentials else None
    if locked_until and locked_until > now:
        wait = int((locked_until - now).total_seconds()) + 1
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many failed attempts. Try again later.",
            headers={"Retry-After": str(wait)},
        )
    # Check against a dummy hash when the user does not exist, so both cases take the same time.
    valid = verify_password(credentials["password_hash"] if credentials else DUMMY_HASH, body.password)
    if credentials is None or not valid:
        if credentials is not None:
            await store.record_login_failure(credentials["customer_id"], MAX_FAILED_ATTEMPTS, LOCK_MINUTES)
        raise _unauthorized("Invalid user name or password")
    await store.record_login_success(credentials["customer_id"])
    profile = await store.get_profile(credentials["customer_id"])
    if profile is None:
        raise _unauthorized("Invalid user name or password")
    return {
        "session_token": create_session_token(credentials["customer_id"]),
        "token_type": "bearer",
        "expires_in": SESSION_TTL_MINUTES * 60,
        "customer": Customer(**profile),
    }


@router.get("/auth/demo-accounts", response_model=DemoAccounts)
async def demo_accounts(store=Depends(get_store)) -> dict:
    """The demonstration accounts for the sign-in page. Off (404) unless DEMO_ACCOUNTS_ENABLED=true."""
    if os.environ.get("DEMO_ACCOUNTS_ENABLED", "false").lower() != "true":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    return {
        "accounts": await store.list_demo_accounts(),
        "password": os.environ.get("DEMO_PASSWORD") or None,
    }


@router.get("/me", response_model=Customer)
async def get_me(customer_id: str = Depends(get_current_customer), store=Depends(get_store)) -> dict:
    profile = await store.get_profile(customer_id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")
    return profile


@router.get("/meta/data", response_model=DataMeta)
async def data_meta(customer_id: str = Depends(get_current_customer), store=Depends(get_store)) -> dict:
    """When the data was last refreshed (the last successful pipeline run), for a "data as of ..." line."""
    return await store.data_meta()


@router.get("/me/summary", response_model=Summary)
async def get_summary(customer_id: str = Depends(get_current_customer), store=Depends(get_store)) -> dict:
    """Home screen: balances by currency, the latest movements and the active cases."""
    return await store.summary(customer_id)


@router.get("/me/products", response_model=list[Product])
async def list_products(customer_id: str = Depends(get_current_customer), store=Depends(get_store)) -> list[dict]:
    return await store.list_products(customer_id)


@router.get("/me/products/{product_id}", response_model=Product)
async def get_product(
    product_id: str, customer_id: str = Depends(get_current_customer), store=Depends(get_store)
) -> dict:
    product = await store.get_product(customer_id, product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found for this customer")
    return product


@router.get("/me/transactions", response_model=TransactionPage)
async def list_transactions(
    product_id: str | None = Query(default=None, min_length=1),
    status_filter: str | None = Query(default=None, alias="status", min_length=1),
    merchant: str | None = Query(default=None, min_length=2),
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    cursor: str | None = Query(default=None, max_length=300),
    limit: int = Query(default=20, ge=1, le=100),
    customer_id: str = Depends(get_current_customer),
    store=Depends(get_store),
) -> dict:
    """Newest first, a page at a time. Each row says whether it already has a dispute case."""
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, "'from' is after 'to'")
    try:
        items, next_cursor = await store.list_transactions_page(
            customer_id,
            product_id=product_id,
            status=status_filter,
            merchant=merchant,
            date_from=date_from,
            date_to=date_to,
            cursor=cursor,
            limit=limit,
        )
    except ValueError:
        raise HTTPException(422, "Invalid cursor")
    return {"items": items, "next_cursor": next_cursor}


@router.get("/me/transactions/{transaction_id}", response_model=Transaction)
async def get_transaction(
    transaction_id: str, customer_id: str = Depends(get_current_customer), store=Depends(get_store)
) -> dict:
    transaction = await store.get_transaction(customer_id, transaction_id)
    if transaction is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transaction not found for this customer")
    return transaction
