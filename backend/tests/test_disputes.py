import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.fakes import CUS_A, CUS_B, FakeStore

HANDOFF = {
    "request": "Human review: possible fraud",
    "verified_facts": ["TXN-A1 is Declined"],
    "actions_taken": [],
    "evidence": [],
    "open_questions": ["Who made the charge?"],
}


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


def _create_dispute(client, headers, transaction_id="TXN-A1"):
    return client.post(
        "/disputes",
        json={"transaction_id": transaction_id, "reason_code": "unrecognized_charge", "summary": "Cargo que no reconozco"},
        headers=headers,
    )


def test_create_dispute_on_own_transaction(client, auth_headers):
    response = _create_dispute(client, auth_headers)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "open"
    assert body["customer_id"] == CUS_A
    assert body["evidence"]["transaction"]["transaction_id"] == "TXN-A1"


def test_create_dispute_on_foreign_transaction_is_404(client, auth_headers):
    response = _create_dispute(client, auth_headers, transaction_id="TXN-B1")
    assert response.status_code == 404
    assert client.get("/disputes").status_code == 401  # the list needs a session like everything else


def test_dispute_not_created_when_transaction_missing(client, auth_headers, store):
    _create_dispute(client, auth_headers, transaction_id="TXN-NOPE")
    assert store.disputes == {}


def test_get_dispute_includes_events(client, auth_headers):
    case_id = _create_dispute(client, auth_headers).json()["case_id"]
    body = client.get(f"/disputes/{case_id}", headers=auth_headers).json()
    assert body["status"] == "open"
    assert body["events"][0]["event"] == "created"


def test_get_foreign_dispute_is_404(client, auth_headers):
    case_id = _create_dispute(client, auth_headers).json()["case_id"]
    other = TestClient(create_app(FakeStore()))
    token = other.post(
        "/session", json={"customer_id": CUS_B, "document_number": "CPF-456"}
    ).json()["session_token"]
    response = other.get(f"/disputes/{case_id}", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 404


def test_escalate_stores_structured_handoff(client, auth_headers):
    case_id = _create_dispute(client, auth_headers).json()["case_id"]
    response = client.post(f"/disputes/{case_id}/escalate", json={"handoff": HANDOFF}, headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "escalated"
    assert body["evidence"]["handoff"] == HANDOFF

    events = client.get(f"/disputes/{case_id}", headers=auth_headers).json()["events"]
    assert events[-1]["event"] == "escalated"
    assert events[-1]["payload"] == HANDOFF


def test_escalate_foreign_dispute_is_404(client, auth_headers):
    response = client.post(
        "/disputes/ffffffff-ffff-ffff-ffff-ffffffffffff/escalate",
        json={"handoff": HANDOFF},
        headers=auth_headers,
    )
    assert response.status_code == 404


def test_a_case_with_a_specialist_or_closed_is_not_reset_by_an_escalation(client, auth_headers, store):
    """Found while documenting the API: escalate used to overwrite any status, so a re-report could undo a closure."""
    for taken in ("in_progress", "closed"):
        case_id = _create_dispute(client, auth_headers, transaction_id="TXN-A2" if taken == "closed" else "TXN-A1").json()["case_id"]
        store.disputes[case_id]["status"] = taken
        response = client.post(f"/disputes/{case_id}/escalate", json={"handoff": HANDOFF}, headers=auth_headers)
        assert response.status_code == 409
        assert store.disputes[case_id]["status"] == taken  # untouched


def test_an_open_or_automatically_resolved_case_can_still_be_escalated(client, auth_headers, store):
    case_id = _create_dispute(client, auth_headers).json()["case_id"]
    store.disputes[case_id]["status"] = "auto_resolved"  # the customer disputes the automatic resolution
    assert client.post(f"/disputes/{case_id}/escalate", json={"handoff": HANDOFF}, headers=auth_headers).status_code == 200
    assert store.disputes[case_id]["status"] == "escalated"


# ------------------------------------------------------------------ one case per transaction, resolve, list


def test_reporting_the_same_transaction_twice_returns_the_same_case(client, auth_headers, store):
    first = _create_dispute(client, auth_headers)
    second = _create_dispute(client, auth_headers)
    assert first.status_code == 201
    assert second.status_code == 201  # the route always answers 201; the body is the case that already existed
    assert second.json()["case_id"] == first.json()["case_id"]
    assert len(store.disputes) == 1


def test_a_closed_case_does_not_block_reporting_again(client, auth_headers, store):
    first = _create_dispute(client, auth_headers).json()
    store.disputes[first["case_id"]]["status"] = "closed"
    again = _create_dispute(client, auth_headers)
    assert again.status_code == 201
    assert again.json()["case_id"] != first["case_id"]


def test_resolve_foreign_case_is_404(client, auth_headers):
    response = client.post(
        "/disputes/ffffffff-ffff-ffff-ffff-ffffffffffff/resolve",
        json={"resolution": "no_charge_confirmed"},
        headers=auth_headers,
    )
    assert response.status_code == 404


def test_list_returns_only_own_cases_newest_first_and_without_events(client, auth_headers, store):
    first = _create_dispute(client, auth_headers, "TXN-A1").json()["case_id"]
    second = _create_dispute(client, auth_headers, "TXN-A2").json()["case_id"]
    store.disputes["foreign"] = {**store.disputes[first], "case_id": "foreign", "customer_id": CUS_B}
    body = client.get("/disputes", headers=auth_headers).json()
    assert [c["case_id"] for c in body] == [second, first]
    assert all("events" not in c or c["events"] is None for c in body)


def test_list_filters_by_status(client, auth_headers):
    case_id = _create_dispute(client, auth_headers, "TXN-A1").json()["case_id"]
    _create_dispute(client, auth_headers, "TXN-A2")
    client.post(f"/disputes/{case_id}/resolve", json={"resolution": "no_charge_confirmed"}, headers=auth_headers)
    resolved = client.get("/disputes?status=auto_resolved", headers=auth_headers).json()
    assert [c["case_id"] for c in resolved] == [case_id]
    assert client.get("/disputes?status=bogus", headers=auth_headers).status_code == 422


def test_v1_serves_the_same_dispute_routes(client, auth_headers):
    created = client.post(
        "/v1/disputes",
        json={"transaction_id": "TXN-A1", "reason_code": "x", "summary": "s"},
        headers=auth_headers,
    )
    assert created.status_code == 201
    assert client.get(f"/v1/disputes/{created.json()['case_id']}", headers=auth_headers).status_code == 200
