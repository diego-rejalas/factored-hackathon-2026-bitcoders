import os

import bcrypt

os.environ.setdefault("SESSION_JWT_SECRET", "test-session-secret-key-over-thirty-two-bytes")
os.environ.setdefault("SESSION_TTL_MINUTES", "120")

# Admin credentials for the suite: same format as production ADMIN_USERS
# (user:bcrypt_hash). Low cost factor: it exists to pass, not to resist.
_HASH = bcrypt.hashpw(b"demo-password", bcrypt.gensalt(rounds=4)).decode()
os.environ.setdefault("ADMIN_USERS", f"ops-demo:{_HASH},lead-demo:{_HASH}")

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.fakes import CUS_A, FakeStore


@pytest.fixture()
def store():
    return FakeStore()


@pytest.fixture()
def client(store):
    return TestClient(create_app(store))


@pytest.fixture()
def auth_headers(client):
    token = client.post("/session", json={"customer_id": CUS_A, "document_number": "CC-123"}).json()["session_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def anyio_backend():
    return "asyncio"
