import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.fakes import CUS_A, CUS_B, FakeStore


@pytest.fixture()
def store():
    return FakeStore()


@pytest.fixture()
def client(store):
    return TestClient(create_app(store))


@pytest.fixture()
def auth_headers(client):
    token = client.post(
        "/session", json={"customer_id": CUS_A, "document_number": "CC-123"}
    ).json()["session_token"]
    return {"Authorization": f"Bearer {token}"}


def _create(client, headers, transaction_id="TXN-A1"):
    return client.post(
        "/disputes",
        json={"transaction_id": transaction_id, "reason_code": "unrecognized_charge", "summary": "Cargo que no reconozco"},
        headers=headers,
    )


def test_my_disputes_lists_only_own_cases_desc(client, auth_headers):
    first = _create(client, auth_headers).json()
    second = _create(client, auth_headers, transaction_id="TXN-A2").json()

    body = client.get("/me/disputes", headers=auth_headers).json()
    assert [row["case_id"] for row in body] == [second["case_id"], first["case_id"]]
    for row in body:
        assert set(row.keys()) == {
            "case_id",
            "transaction_id",
            "reason_code",
            "status",
            "created_at",
            "resolved_at",
        }
        assert row["status"] == "open"

    other = TestClient(create_app(FakeStore()))
    token = other.post(
        "/session", json={"customer_id": CUS_B, "document_number": "CPF-456"}
    ).json()["session_token"]
    assert other.get("/me/disputes", headers={"Authorization": f"Bearer {token}"}).json() == []


def test_my_disputes_requires_token(client):
    assert client.get("/me/disputes").status_code == 401


def test_resolve_marks_case_auto_resolved_with_audit_event(client, auth_headers, store):
    case_id = _create(client, auth_headers).json()["case_id"]
    response = client.post(
        f"/disputes/{case_id}/resolve",
        json={"resolution": "no_charge_confirmed"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "auto_resolved"
    assert body["resolved_at"] is not None
    events = client.get(f"/disputes/{case_id}", headers=auth_headers).json()["events"]
    assert events[-1]["event"] == "auto_resolved"
    assert events[-1]["payload"] == {"resolution": "no_charge_confirmed", "by": "agent"}


def test_resolve_is_idempotent(client, auth_headers):
    case_id = _create(client, auth_headers).json()["case_id"]
    first = client.post(
        f"/disputes/{case_id}/resolve",
        json={"resolution": "no_charge_confirmed"},
        headers=auth_headers,
    )
    second = client.post(
        f"/disputes/{case_id}/resolve",
        json={"resolution": "no_charge_confirmed"},
        headers=auth_headers,
    )
    assert first.status_code == 200 and second.status_code == 200
    assert second.json()["status"] == "auto_resolved"


def test_cannot_resolve_an_escalated_case(client, auth_headers):
    case_id = _create(client, auth_headers).json()["case_id"]
    client.post(
        f"/disputes/{case_id}/escalate",
        json={"handoff": {"reason": "fraud_suspected"}},
        headers=auth_headers,
    )
    response = client.post(
        f"/disputes/{case_id}/resolve",
        json={"resolution": "no_charge_confirmed"},
        headers=auth_headers,
    )
    assert response.status_code == 409


def test_resolve_rejects_unknown_resolution(client, auth_headers):
    case_id = _create(client, auth_headers).json()["case_id"]
    response = client.post(
        f"/disputes/{case_id}/resolve",
        json={"resolution": "made_up"},
        headers=auth_headers,
    )
    assert response.status_code == 422


def test_unlinked_handoff_case_can_be_created_after_ambiguous_report(client, auth_headers):
    response = client.post(
        "/disputes",
        json={
            "reason_code": "unrecognized_charge",
            "summary": "No se identificó una transacción única.",
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    assert response.json()["transaction_id"] is None
    assert response.json()["status"] == "open"
