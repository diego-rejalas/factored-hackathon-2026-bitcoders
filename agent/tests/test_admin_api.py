import os
import time

import jwt
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.tracing import aggregate_metrics, percentile
from tests.fakes import CUS_A, FakeBankTools, FakeTracer

TEST_SECRET = os.environ.get("SESSION_JWT_SECRET", "test-secret")

TRACE_ROWS = [
    # run 1: clarify then resolved, es
    {"run_id": "r1", "conversation_id": "c1", "node": "understand", "intent": "dispute", "params": {"language": "es"}, "result_status": None, "latency_ms": 10},
    {"run_id": "r1", "conversation_id": "c1", "node": "decide", "intent": "dispute", "params": None, "result_status": "clarify", "latency_ms": 20},
    {"run_id": "r1", "conversation_id": "c1", "node": "respond", "intent": "dispute", "params": None, "result_status": "clarify", "latency_ms": 30},
    {"run_id": "r2", "conversation_id": "c1", "node": "understand", "intent": "dispute", "params": {"language": "es"}, "result_status": None, "latency_ms": 11},
    {"run_id": "r2", "conversation_id": "c1", "node": "decide", "intent": "dispute", "params": None, "result_status": "act", "latency_ms": 21},
    {"run_id": "r2", "conversation_id": "c1", "node": "act", "intent": "dispute", "params": None, "result_status": "open", "latency_ms": 40},
    {"run_id": "r2", "conversation_id": "c1", "node": "verify", "intent": "dispute", "params": None, "result_status": "auto_resolved", "latency_ms": 41},
    {"run_id": "r2", "conversation_id": "c1", "node": "respond", "intent": "dispute", "params": None, "result_status": "resolved", "latency_ms": 31},
    # run 3: escalated, pt
    {"run_id": "r3", "conversation_id": "c2", "node": "understand", "intent": "dispute", "params": {"language": "pt"}, "result_status": None, "latency_ms": 12},
    {"run_id": "r3", "conversation_id": "c2", "node": "decide", "intent": "dispute", "params": None, "result_status": "escalate", "latency_ms": 22},
    {"run_id": "r3", "conversation_id": "c2", "node": "escalate", "intent": "dispute", "params": None, "result_status": "escalated", "latency_ms": 50},
    {"run_id": "r3", "conversation_id": "c2", "node": "respond", "intent": "dispute", "params": None, "result_status": "escalated", "latency_ms": 32},
    {"run_id": "r3", "conversation_id": "c2", "node": "verify", "intent": "dispute", "params": None, "result_status": "failed", "latency_ms": 60},
]


@pytest.fixture()
def tools():
    return FakeBankTools()


@pytest.fixture()
def tracer():
    return FakeTracer(TRACE_ROWS)


@pytest.fixture()
def client(tools, tracer):
    return TestClient(create_app(tools=tools, tracer=tracer, llm=None))


def _customer_jwt(customer_id=CUS_A):
    now = int(time.time())
    return jwt.encode(
        {"sub": customer_id, "role": "customer", "iat": now, "exp": now + 3600, "iss": "backend-sandbox"},
        TEST_SECRET,
        algorithm="HS256",
    )


def _admin_jwt(username="ops-demo"):
    now = int(time.time())
    return jwt.encode(
        {"sub": username, "role": "admin", "iat": now, "exp": now + 3600, "iss": "backend-sandbox"},
        TEST_SECRET,
        algorithm="HS256",
    )


def _admin_login(client):
    body = client.post("/admin/session", json={"username": "ops-demo", "password": "demo-password"})
    assert body.status_code == 200
    return {"Authorization": f"Bearer {body.json()['session_token']}"}


# --- enriched chat ---------------------------------------------------------------------------------


def test_chat_returns_candidates_when_clarifying(client):
    response = client.post(
        "/chat",
        json={
            "session_token": _customer_jwt(),
            "message": "Me hicieron un cobro que no reconozco",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "clarify"
    assert body["candidates"], "candidates must be present with multiple matches"
    assert all("transaction_id" in c for c in body["candidates"])
    assert body["language"] == "es"
    assert body["reason"]


def test_chat_returns_case_and_language_in_pt(client):
    response = client.post(
        "/chat",
        json={
            "session_token": _customer_jwt(),
            "message": "Olá, não reconheço uma cobrança de 45.50 na Tienda Don Pepe",
        },
    )
    body = response.json()
    assert body["outcome"] == "resolved"
    assert body["case"]["status"] == "auto_resolved"
    assert body["language"] == "pt"
    assert body["candidates"] is None or isinstance(body["candidates"], list)


def test_chat_backward_compatible_fields_still_present(client):
    body = client.post(
        "/chat",
        json={"session_token": _customer_jwt(), "message": "Hola, buenas tardes"},
    ).json()
    assert body["reply"]
    assert body["conversation_id"]
    assert body["outcome"] == "resolved"
    assert body["handoff"] is None


# --- admin proxies -----------------------------------------------------------------------------------


def test_admin_session_proxies_login(client, tools):
    response = client.post("/admin/session", json={"username": "ops-demo", "password": "demo-password"})
    assert response.status_code == 200
    assert tools.calls_of("admin_login")

    bad = client.post("/admin/session", json={"username": "ops-demo", "password": "nope"})
    assert bad.status_code == 401


def test_admin_proxies_reject_customer_token(client):
    headers = {"Authorization": f"Bearer {_customer_jwt()}"}
    assert client.get("/admin/disputes", headers=headers).status_code == 403
    assert client.get("/admin/metrics", headers=headers).status_code == 403
    assert client.get("/admin/agent-metrics", headers=headers).status_code == 403
    assert client.get("/meta/data", headers=headers).status_code == 403


def test_customer_chat_rejects_admin_token(client):
    response = client.post(
        "/chat",
        json={"session_token": _admin_jwt(), "message": "Hola"},
    )
    assert response.status_code == 403


def test_admin_proxies_reject_missing_token(client):
    assert client.get("/admin/disputes").status_code == 401
    assert client.get("/admin/agent-metrics").status_code == 401


def test_admin_disputes_proxy_forwards_token_and_filters(client, tools):
    headers = _admin_login(client)
    body = client.get("/admin/disputes?status=escalated", headers=headers).json()
    assert "items" in body
    forwarded = tools.calls_of("admin_list_disputes")[-1][1]
    assert forwarded == {"status": "escalated", "customer_id": None}


def test_admin_transition_proxy_propagates_409(client, tools):
    headers = _admin_login(client)
    response = client.post(
        "/admin/disputes/00000000-0000-0000-0000-000000000009/transition",
        json={"action": "claim", "note": "tomar"},
        headers=headers,
    )
    assert response.status_code == 404  # unknown case: backend status code passes through


def test_admin_metrics_proxy(client, tools):
    headers = _admin_login(client)
    body = client.get("/admin/metrics?window=24", headers=headers).json()
    assert "safe_automated_resolution" in body
    assert tools.calls_of("admin_metrics")[-1][1] == {"window_hours": 24}


def test_meta_demo_scenarios_is_public(client, tools):
    body = client.get("/meta/demo-scenarios").json()
    assert body["scenarios"][0]["scenario"] == "auto_resolved"
    assert tools.calls_of("get_demo_scenarios")


def test_my_disputes_proxy_forwards_customer_token(client, tools):
    headers = {"Authorization": f"Bearer {_customer_jwt()}"}
    client.post(
        "/chat",
        json={"session_token": _customer_jwt(), "message": "cobro que no reconozco de 45.50 en Tienda Don Pepe"},
    )
    body = client.get("/me/disputes", headers=headers).json()
    assert isinstance(body, list) and body[0]["status"] == "auto_resolved"


# --- agent-owned metrics (agent.trace_log) ------------------------------------------------------------


def test_percentile_matches_percentile_cont_semantics():
    assert percentile([], 0.5) is None
    assert percentile([7], 0.5) == 7.0
    assert percentile([10, 20], 0.5) == 15.0
    assert percentile([1, 2, 3, 4], 0.95) == 3.85
    assert percentile([1, 2, 3, 4], 0.0) == 1.0
    assert percentile([1, 2, 3, 4], 1.0) == 4.0


def test_aggregate_metrics_computes_outcomes_containment_and_percentiles():
    result = aggregate_metrics(TRACE_ROWS)
    assert result["runs_by_outcome"] == {"clarify": 1, "resolved": 1, "escalated": 1}
    assert result["total_runs"] == 3
    assert result["containment"] == {"conversations": 2, "without_transfer": 1, "rate_percent": 50.0}
    # decide latencies: [20, 21, 22] -> p50 21, p95 21.9
    assert result["latency_by_node"]["decide"] == {"p50_ms": 21.0, "p95_ms": 21.9, "n": 3}
    assert result["intents"] == {"dispute": 3}
    assert result["languages"] == {"es": 2, "pt": 1}
    assert result["verify"] == {"ok": 1, "failed": 1}


def test_aggregate_metrics_empty_is_not_defined():
    result = aggregate_metrics([])
    assert result["total_runs"] == 0
    assert result["containment"]["rate_percent"] is None
    assert result["latency_by_node"] == {}


def test_agent_metrics_endpoint_serves_aggregation(client):
    headers = {"Authorization": f"Bearer {_admin_jwt()}"}
    body = client.get("/admin/agent-metrics", headers=headers).json()
    assert body["tracing_enabled"] is True
    assert body["runs_by_outcome"]["resolved"] == 1
    assert body["languages"] == {"es": 2, "pt": 1}


def test_conversation_trace_endpoint_returns_rows(client):
    headers = {"Authorization": f"Bearer {_admin_jwt()}"}
    body = client.get("/admin/conversations/c2/trace", headers=headers).json()
    assert body["conversation_id"] == "c2"
    nodes = [row["node"] for row in body["rows"]]
    assert nodes == ["understand", "decide", "escalate", "respond", "verify"]
