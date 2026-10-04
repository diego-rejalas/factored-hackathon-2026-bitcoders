import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from app.db import get_store

JWT_ALGORITHM = "HS256"
TOKEN_ISSUER = "backend-sandbox"
SESSION_TTL_MINUTES = int(os.environ.get("SESSION_TTL_MINUTES", "120"))
ADMIN_TTL_MINUTES = int(os.environ.get("ADMIN_TTL_MINUTES", "480"))
_bearer = HTTPBearer(auto_error=False)

router = APIRouter(tags=["session"])

# --- admin credentials -------------------------------------------------------------------------
# ADMIN_USERS is "user:bcrypt_hash,user2:bcrypt_hash" (generate hashes offline, keep the
# value in Secret Manager). Sandbox limitation, stated deliberately: there is no real IdP
# behind this, and the rate limit below is in-memory, so it holds per process only.

ADMIN_MAX_FAILURES = 5
ADMIN_LOCKOUT_SECONDS = 60
# Constant hash used to equalize timing when the username is unknown.
_DUMMY_HASH = "$2b$10$9qNEDrUy8P3jF9YqLdS5Wezs04P.HNyuKnVOqfmmPLJY4EzRiT7d."
_admin_failures: dict[str, tuple[int, float]] = {}


def _admin_users() -> dict[str, str]:
    users: dict[str, str] = {}
    for entry in os.environ.get("ADMIN_USERS", "").split(","):
        entry = entry.strip()
        if not entry:
            continue
        username, _, password_hash = entry.partition(":")
        if username and password_hash:
            users[username] = password_hash
    return users


def _client_key(request: Request, username: str) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")
    return f"{ip}:{username}"


def _rate_limited(key: str, now: float | None = None) -> bool:
    failures = _admin_failures.get(key)
    if not failures:
        return False
    count, blocked_until = failures
    now = now if now is not None else time.monotonic()
    return count >= ADMIN_MAX_FAILURES and now < blocked_until


def _register_failure(key: str) -> None:
    count, _ = _admin_failures.get(key, (0, 0.0))
    count += 1
    _admin_failures[key] = (count, time.monotonic() + ADMIN_LOCKOUT_SECONDS if count >= ADMIN_MAX_FAILURES else 0.0)


def _clear_failures(key: str) -> None:
    _admin_failures.pop(key, None)


# --- tokens ------------------------------------------------------------------------------------

class SessionRequest(BaseModel):
    customer_id: str = Field(min_length=1)
    document_number: str = Field(min_length=1)


class AdminSessionRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class SessionResponse(BaseModel):
    session_token: str
    token_type: str
    expires_in: int


def get_session_secret() -> str:
    secret = os.environ.get("SESSION_JWT_SECRET")
    if not secret:
        raise RuntimeError("SESSION_JWT_SECRET is not set")
    return secret


def create_session_token(
    customer_id: str, role: str = "customer", ttl_minutes: int | None = None
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": customer_id,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=ttl_minutes if ttl_minutes is not None else SESSION_TTL_MINUTES),
        "iss": TOKEN_ISSUER,
    }
    return jwt.encode(payload, get_session_secret(), algorithm=JWT_ALGORITHM)


async def _decode_bearer(
    credentials: HTTPAuthorizationCredentials | None,
) -> dict[str, Any]:
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
    if not payload.get("sub"):
        raise _unauthorized("Invalid or expired session token")
    return payload


async def get_current_customer(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    payload = await _decode_bearer(credentials)
    if payload.get("role", "customer") != "customer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Customer role required",
        )
    return str(payload["sub"])


async def get_current_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    payload = await _decode_bearer(credentials)
    if payload.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )
    return str(payload["sub"])


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


@router.post("/admin/session", response_model=SessionResponse, tags=["admin"])
async def create_admin_session(body: AdminSessionRequest, request: Request) -> SessionResponse:
    users = _admin_users()
    if not users:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin access is not configured (ADMIN_USERS is empty)",
        )
    key = _client_key(request, body.username)
    if _rate_limited(key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed attempts; wait before retrying",
            headers={"Retry-After": str(ADMIN_LOCKOUT_SECONDS)},
        )
    password_hash = users.get(body.username)
    try:
        password_matches = bcrypt.checkpw(
            body.password.encode(),
            (password_hash or _DUMMY_HASH).encode(),
        )
    except ValueError:  # malformed Secret Manager value fails closed, never 500s
        password_matches = False
    ok = password_matches and password_hash is not None
    if not ok:
        _register_failure(key)
        raise _unauthorized("Invalid admin username or password")
    _clear_failures(key)
    return SessionResponse(
        session_token=create_session_token(body.username, role="admin", ttl_minutes=ADMIN_TTL_MINUTES),
        token_type="bearer",
        expires_in=ADMIN_TTL_MINUTES * 60,
    )
