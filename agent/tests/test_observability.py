import json

import httpx
import pytest

from app import tools as tools_module
from app.observability import request_id_var
from app.tools import BankTools


def lines(capsys) -> list[dict]:
    return [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")]


def test_every_response_carries_a_request_id(client):
    assert len(client.get("/health").headers["X-Request-ID"]) >= 8


def test_a_well_formed_id_is_kept_and_a_malformed_one_replaced(client):
    assert client.get("/health", headers={"X-Request-ID": "bff-7f3a9c2e-0001"}).headers["X-Request-ID"] == "bff-7f3a9c2e-0001"
    assert client.get("/health", headers={"X-Request-ID": "bad id!"}).headers["X-Request-ID"] != "bad id!"


def test_a_chat_turn_logs_one_line_with_severity_and_no_message_text(client, capsys):
    from tests.test_api import _jwt

    client.post(
        "/chat",
        json={"session_token": _jwt(), "message": "No reconozco el cobro de 45.50 en Tienda Don Pepe"},
        headers={"X-Request-ID": "trace-0000000002"},
    )
    out = capsys.readouterr().out
    entry = [json.loads(line) for line in out.splitlines() if line.startswith("{") and '"/chat"' in line][-1]
    assert entry["service"] == "agent" and entry["request_id"] == "trace-0000000002" and entry["status"] == 200
    assert "Tienda Don Pepe" not in out and "45.50" not in out  # what the customer wrote is not logged
    assert "session_token" not in out


def test_the_browser_may_read_and_send_the_id(client):
    # Preflight from an allowed origin, if the app is configured with one.
    from app.main import create_app
    from app.tracing import NullTracer
    from fastapi.testclient import TestClient
    from tests.fakes import FakeBankTools
    import os

    os.environ["CORS_ALLOWED_ORIGINS"] = "http://localhost:3000"
    try:
        app = TestClient(create_app(tools=FakeBankTools(), tracer=NullTracer(), llm=None))
        preflight = app.options(
            "/chat",
            headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "x-request-id"},
        )
        assert "x-request-id" in preflight.headers["access-control-allow-headers"].lower()
        shown = app.get("/health", headers={"Origin": "http://localhost:3000"})
        assert "x-request-id" in shown.headers["access-control-expose-headers"].lower()
    finally:
        del os.environ["CORS_ALLOWED_ORIGINS"]


@pytest.mark.anyio
async def test_the_id_of_the_request_is_passed_on_to_the_backend(monkeypatch):
    monkeypatch.setattr(tools_module, "BACKOFF_SECONDS", (0, 0))
    seen: dict = {}
    real = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(request.headers)
        return httpx.Response(200, json={})

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real(**{**kw, "transport": httpx.MockTransport(handler)}))
    token = request_id_var.set("trace-0000000003")
    try:
        await BankTools("http://backend").get_dispute("session-jwt", "c1")
    finally:
        request_id_var.reset(token)
    assert seen["x-request-id"] == "trace-0000000003"
    assert seen["authorization"] == "Bearer session-jwt"


@pytest.mark.anyio
async def test_without_a_request_there_is_no_header(monkeypatch):
    seen: dict = {}
    real = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(request.headers)
        return httpx.Response(200, json={})

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real(**{**kw, "transport": httpx.MockTransport(handler)}))
    await BankTools("http://backend").get_dispute("t", "c1")
    assert "x-request-id" not in seen
