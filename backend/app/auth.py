import os
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from app.db import get_store

JWT_ALGORITHM = "HS256"
TOKEN_ISSUER = "backend-sandbox"
SESSION_TTL_MINUTES = int(os.environ.get("SESSION_TTL_MINUTES", "120"))
_bearer = HTTPBearer(auto_error=False)

router = APIRouter(tags=["session"])


class SessionRequest(BaseModel):
    customer_id: str = Field(min_length=1)
    document_number: str = Field(min_length=1)


class SessionResponse(BaseModel):
    session_token: str
    token_type: str
    expires_in: int


def get_session_secret() -> str:
    secret = os.environ.get("SESSION_JWT_SECRET")
    if not secret:
        raise RuntimeError("SESSION_JWT_SECRET is not set")
    return secret


def create_session_token(customer_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": customer_id,
        "iat": now,
        "exp": now + timedelta(minutes=SESSION_TTL_MINUTES),
        "iss": TOKEN_ISSUER,
    }
    return jwt.encode(payload, get_session_secret(), algorithm=JWT_ALGORITHM)


async def get_current_customer(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized("Missing bearer session token")
    try:
        payload: dict[str, Any] = jwt.decode(
            credentials.credentials,
            get_session_secret(),
            algorithms=[JWT_ALGORITHM],
            issuer=TOKEN_ISSUER,
        )
    except jwt.PyJWTError:
        raise _unauthorized("Invalid or expired session token")
    customer_id = payload.get("sub")
    if not customer_id:
        raise _unauthorized("Invalid or expired session token")
    return str(customer_id)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


@router.post("/session", response_model=SessionResponse)
async def create_session(body: SessionRequest, store=Depends(get_store)) -> SessionResponse:
    customer_id = await store.authenticate(
        body.customer_id.strip(), body.document_number.strip()
    )
    if customer_id is None:
        raise _unauthorized("Invalid customer_id or document_number")
    return SessionResponse(
        session_token=create_session_token(customer_id),
        token_type="bearer",
        expires_in=SESSION_TTL_MINUTES * 60,
    )
