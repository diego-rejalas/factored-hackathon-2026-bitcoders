import pytest
from fastapi.testclient import TestClient

from app import auth as auth_module
from app.main import create_app
from tests.fakes import CUS_A, CUS_B, FakeStore

HANDOFF = {
    "reason": "fraud_suspected",
    "customer_language": "es",
    "conversation_id": "conv-1",
    "verified_facts": ["TXN-A1 is Declined"],
    "actions_taken": [],
    "evidence": [],
    "open_questions": ["Who made the charge?"],
}


@pytest.fixture(autouse=True)
def _clean_rate_limit():
    auth_module._admin_failures.clear()
    yield
    auth_module._admin_failures.clear()


@pytest.fixture()
def store():
    return FakeStore()


@pytest.fixture()
def client(store):
    return TestClient(create_app(store))


@pytest.fixture()
def customer_headers(client):
    token = client.post(
        "/session", json={"customer_id": CUS_A, "document_number": "CC-123"}
    ).json()["session_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def admin_headers(client):
    body = client.post(
        "/admin/session", json={"username": "ops-demo", "password": "demo-password"}
    )
    assert body.status_code == 200
    return {"Authorization": f"Bearer {body.json()['session_token']}"}


def _create_dispute(client, headers, transaction_id="TXN-A1"):
    return client.post(
        "/disputes",
        json={"transaction_id": transaction_id, "reason_code": "unrecognized_charge", "summary": "Cargo que no reconozco"},
        headers=headers,
    )


def _escalated_case(client, customer_headers, transaction_id="TXN-A1"):
    case_id = _create_dispute(client, customer_headers, transaction_id).json()["case_id"]
    client.post(f"/disputes/{case_id}/escalate", json={"handoff": HANDOFF}, headers=customer_headers)
    return case_id


# --- admin authentication ----------------------------------------------------------------------


def test_admin_login_issues_admin_role_token(client):
    body = client.post(
        "/admin/session", json={"username": "ops-demo", "password": "demo-password"}
    ).json()
    assert body["token_type"] == "bearer"
    import jwt as pyjwt

    payload = pyjwt.decode(
        body["session_token"],
        auth_module.get_session_secret(),
        algorithms=["HS256"],
        issuer="backend-sandbox",
    )
    assert payload["sub"] == "ops-demo"
    assert payload["role"] == "admin"


def test_admin_login_rejects_wrong_password(client):
    response = client.post(
        "/admin/session", json={"username": "ops-demo", "password": "nope"}
    )
    assert response.status_code == 401


def test_admin_login_rejects_unknown_user(client):
    response = client.post(
        "/admin/session", json={"username": "ghost", "password": "demo-password"}
    )
    assert response.status_code == 401


def test_malformed_configured_bcrypt_hash_fails_closed(monkeypatch, client):
    monkeypatch.setenv("ADMIN_USERS", "ops-demo:not-a-bcrypt-hash")
    response = client.post(
        "/admin/session", json={"username": "ops-demo", "password": "demo-password"}
    )
    assert response.status_code == 401


def test_admin_login_locks_out_after_five_failures(client):
    for _ in range(5):
        assert (
            client.post(
                "/admin/session", json={"username": "lead-demo", "password": "bad"}
            ).status_code
            == 401
        )
    locked = client.post(
        "/admin/session", json={"username": "lead-demo", "password": "demo-password"}
    )
    assert locked.status_code == 429
    # The lockout is per username: another admin is unaffected.
    assert (
        client.post(
            "/admin/session", json={"username": "ops-demo", "password": "demo-password"}
        ).status_code
        == 200
    )


def test_customer_token_cannot_use_admin_endpoints(client, customer_headers):
    for method, path in [
        ("get", "/admin/disputes"),
        ("get", "/admin/metrics"),
        ("get", "/meta/data"),
        ("post", "/admin/disputes/00000000-0000-0000-0000-000000000001/transition"),
    ]:
        response = getattr(client, method)(path, headers=customer_headers)
        assert response.status_code == 403, path


def test_admin_token_cannot_use_customer_endpoints(client):
    token = client.post(
        "/admin/session", json={"username": "ops-demo", "password": "demo-password"}
    ).json()["session_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/me/disputes", headers=headers).status_code == 403
    assert client.post(
        "/disputes",
        json={"transaction_id": "TXN-A1", "reason_code": "unrecognized_charge", "summary": "x"},
        headers=headers,
    ).status_code == 403


def test_legacy_customer_token_without_role_remains_accepted(client):
    import jwt as pyjwt
    import time

    now = int(time.time())
    token = pyjwt.encode(
        {"sub": CUS_A, "iat": now, "exp": now + 60, "iss": "backend-sandbox"},
        auth_module.get_session_secret(),
        algorithm="HS256",
    )
    response = client.get("/me/disputes", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200


def test_admin_endpoints_reject_missing_token(client):
    assert client.get("/admin/disputes").status_code == 401
    assert client.get("/admin/metrics").status_code == 401
    assert client.get("/meta/data").status_code == 401


# --- admin inbox ---------------------------------------------------------------------------------


def test_admin_lists_disputes_with_customer_context(client, customer_headers, admin_headers):
    _escalated_case(client, customer_headers)
    body = client.get("/admin/disputes", headers=admin_headers).json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["customer_id"] == CUS_A
    assert item["first_name"] == "Ana"
    assert item["status"] == "escalated"
    assert item["handoff_reason"] == "fraud_suspected"
    assert item["customer_language"] == "es"


def test_admin_list_filters_by_status(client, customer_headers, admin_headers):
    _escalated_case(client, customer_headers)  # escalated
    _create_dispute(client, customer_headers, transaction_id="TXN-A2")  # open
    escalated = client.get("/admin/disputes?status=escalated", headers=admin_headers).json()
    assert escalated["total"] == 1
    assert all(item["status"] == "escalated" for item in escalated["items"])


def test_active_queue_includes_escalated_and_in_progress(client, customer_headers, admin_headers):
    case_id = _escalated_case(client, customer_headers)
    client.post(
        f"/admin/disputes/{case_id}/transition",
        json={"action": "claim", "note": "asignado"},
        headers=admin_headers,
    )
    _escalated_case(client, customer_headers, "TXN-A2")  # another transaction: one case per (customer, transaction)
    body = client.get("/admin/disputes?status=active", headers=admin_headers).json()
    assert body["total"] == 2
    assert {item["status"] for item in body["items"]} == {"escalated", "in_progress"}


def test_admin_case_detail_includes_handoff_events_and_conversation(client, customer_headers, admin_headers):
    case_id = _escalated_case(client, customer_headers)
    body = client.get(f"/admin/disputes/{case_id}", headers=admin_headers).json()
    assert body["handoff"]["reason"] == "fraud_suspected"
    assert body["conversation_id"] == "conv-1"
    assert [e["event"] for e in body["events"]] == ["created", "escalated"]


def test_unlinked_escalation_is_in_admin_inbox(client, customer_headers, admin_headers):
    created = client.post(
        "/disputes",
        json={"reason_code": "unrecognized_charge", "summary": "Varias transacciones posibles."},
        headers=customer_headers,
    )
    assert created.status_code == 201
    case_id = created.json()["case_id"]
    assert created.json()["transaction_id"] is None
    escalated = client.post(
        f"/disputes/{case_id}/escalate",
        json={"handoff": {**HANDOFF, "reason": "ambiguity_unresolved"}},
        headers=customer_headers,
    )
    assert escalated.status_code == 200
    inbox = client.get("/admin/disputes?status=active", headers=admin_headers).json()
    assert inbox["total"] == 1
    assert inbox["items"][0]["case_id"] == case_id
    detail = client.get(f"/admin/disputes/{case_id}", headers=admin_headers).json()
    assert detail["transaction_id"] is None
    assert detail["handoff"]["reason"] == "ambiguity_unresolved"


def test_admin_case_unknown_is_404(client, admin_headers):
    response = client.get(
        "/admin/disputes/ffffffff-ffff-ffff-ffff-ffffffffffff", headers=admin_headers
    )
    assert response.status_code == 404


# --- audited transitions -------------------------------------------------------------------------


def test_claim_then_close_is_audited(client, customer_headers, admin_headers):
    case_id = _escalated_case(client, customer_headers)

    claimed = client.post(
        f"/admin/disputes/{case_id}/transition",
        json={"action": "claim", "note": "lo tomo"},
        headers=admin_headers,
    )
    assert claimed.status_code == 200
    assert claimed.json()["status"] == "in_progress"

    closed = client.post(
        f"/admin/disputes/{case_id}/transition",
        json={
            "action": "close",
            "note": "confirmado con el cliente",
            "resolution": "resolved_customer",
        },
        headers=admin_headers,
    )
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"

    events = client.get(f"/admin/disputes/{case_id}", headers=admin_headers).json()["events"]
    by_event = {e["event"]: e["payload"] for e in events}
    assert by_event["admin_claim"] == {"admin": "ops-demo", "note": "lo tomo"}
    assert by_event["admin_close"]["resolution"] == "resolved_customer"
    assert by_event["admin_close"]["admin"] == "ops-demo"


def test_double_claim_conflicts(client, customer_headers, admin_headers):
    case_id = _escalated_case(client, customer_headers)
    first = client.post(
        f"/admin/disputes/{case_id}/transition", json={"action": "claim", "note": "tomado"}, headers=admin_headers
    )
    second = client.post(
        f"/admin/disputes/{case_id}/transition", json={"action": "claim", "note": "intento duplicado"}, headers=admin_headers
    )
    assert first.status_code == 200
    assert second.status_code == 409


def test_close_requires_resolution(client, customer_headers, admin_headers):
    case_id = _escalated_case(client, customer_headers)
    client.post(f"/admin/disputes/{case_id}/transition", json={"action": "claim", "note": "tomado"}, headers=admin_headers)
    response = client.post(
        f"/admin/disputes/{case_id}/transition",
        json={"action": "close", "note": "sin resolución"},
        headers=admin_headers,
    )
    assert response.status_code == 422


def test_close_without_claim_conflicts(client, customer_headers, admin_headers):
    case_id = _escalated_case(client, customer_headers)
    response = client.post(
        f"/admin/disputes/{case_id}/transition",
        json={"action": "close", "note": "resolución no confirmada", "resolution": "no_resolution"},
        headers=admin_headers,
    )
    assert response.status_code == 409


def test_unknown_action_is_rejected(client, customer_headers, admin_headers):
    case_id = _escalated_case(client, customer_headers)
    response = client.post(
        f"/admin/disputes/{case_id}/transition",
        json={"action": "resolve"},
        headers=admin_headers,
    )
    assert response.status_code == 422


# --- metrics ---------------------------------------------------------------------------------------


def test_metrics_shape_and_denominators(client, customer_headers, admin_headers):
    case_id = _create_dispute(client, customer_headers).json()["case_id"]
    client.post(
        f"/disputes/{case_id}/resolve", json={"resolution": "no_charge_confirmed"}, headers=customer_headers
    )
    escalated_case = _escalated_case(client, customer_headers, "TXN-A2")  # a second transaction: one case per transaction
    client.post(
        f"/admin/disputes/{escalated_case}/transition",
        json={"action": "claim", "note": "lo tomo"},
        headers=admin_headers,
    )
    client.post(
        f"/admin/disputes/{escalated_case}/transition",
        json={"action": "close", "note": "cliente atendido", "resolution": "resolved_customer"},
        headers=admin_headers,
    )

    body = client.get("/admin/metrics", headers=admin_headers).json()
    assert body["total_cases"] == 2
    assert body["by_status"]["auto_resolved"] == 1
    assert body["by_status"]["closed"] == 1
    safe = body["safe_automated_resolution"]
    assert safe == {"resolved": 1, "attempted": 2, "rate_percent": 50.0}
    assert body["escalations"] == {"count": 1, "rate_percent": 50.0}
    assert body["human_closure"] == {"closed": 1}
    assert {"language": "es", "n": 1} in body["by_language"]
    assert {"reason": "fraud_suspected", "n": 1} in body["by_reason"]


def test_metrics_rate_is_null_without_data(client, admin_headers):
    body = client.get("/admin/metrics", headers=admin_headers).json()
    assert body["total_cases"] == 0
    assert body["safe_automated_resolution"]["rate_percent"] is None  # "not defined"


# --- meta ------------------------------------------------------------------------------------------

def test_meta_data_reports_freshness(client, admin_headers):
    body = client.get("/meta/data", headers=admin_headers).json()
    assert body["gold"]["customers"] == 2
    assert body["last_etl_run"]["status"] == "success"


DEMO_ALLOWED_FIELDS = {
    "scenario",
    "customer_id",
    "document_number",
    "first_name",
    "hint_es",
    "hint_pt",
}


def test_demo_scenarios_shape_is_stable_and_never_exposes_fraud_columns(client):
    first = client.get("/meta/demo-scenarios")
    assert first.status_code == 200
    scenarios = first.json()["scenarios"]
    assert scenarios, "at least one scenario must be pickable from the fixture data"
    for entry in scenarios:
        assert set(entry.keys()) == DEMO_ALLOWED_FIELDS
        assert entry["scenario"] in ("auto_resolved", "ambiguous", "fraud", "threshold")
        assert entry["customer_id"] and entry["document_number"]
        assert entry["hint_es"] and entry["hint_pt"]
    again = client.get("/meta/demo-scenarios").json()["scenarios"]
    assert again == scenarios  # deterministic
