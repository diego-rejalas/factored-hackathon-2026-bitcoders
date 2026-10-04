import os

os.environ.setdefault("SESSION_JWT_SECRET", "test-session-secret-key-over-thirty-two-bytes")
os.environ.setdefault("GUARDRAIL_MAX_USD", "500")


import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.tracing import NullTracer
from tests.fakes import FakeBankTools


@pytest.fixture()
def tools():
    return FakeBankTools()


@pytest.fixture()
def client(tools):
    return TestClient(create_app(tools=tools, tracer=NullTracer(), llm=None))
