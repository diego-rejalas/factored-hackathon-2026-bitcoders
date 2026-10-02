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


def test_me_returns_minimal_profile_only(client, auth_headers):
    body = client.get("/me", headers=auth_headers).json()
    assert body["customer_id"] == CUS_A
    assert body == {
        "customer_id": CUS_A,
        "first_name": "Ana",
        "last_name": "García",
        "country": "Colombia",
    }


def test_me_profile_never_exposes_sensitive_fields(client, auth_headers, store):
    body = client.get("/me", headers=auth_headers).json()
    sensitive = {"document_number", "credit_score", "estimated_monthly_income", "email"}
    assert sensitive.isdisjoint(body.keys())
    sensitive.isdisjoint(store.customers[CUS_A].keys() & body.keys())


def test_transactions_always_scoped_to_token(client, auth_headers):
    body = client.get("/me/transactions", headers=auth_headers).json()
    ids = {row["transaction_id"] for row in body}
    assert ids == {"TXN-A1", "TXN-A2", "TXN-A3"}
    assert all(row["customer_id"] not in (None, CUS_B) for row in body)


def test_transaction_filters_apply(client, auth_headers):
    declined = client.get("/me/transactions?status=Declined", headers=auth_headers).json()
    assert [row["transaction_id"] for row in declined] == ["TXN-A1"]

    merchant = client.get("/me/transactions?merchant=farmacia", headers=auth_headers).json()
    assert [row["transaction_id"] for row in merchant] == ["TXN-A2"]

    # Day windows are anchored to the latest transaction in the dataset
    # (static snapshot), not to now().
    recent = client.get("/me/transactions?days=30", headers=auth_headers).json()
    assert [row["transaction_id"] for row in recent] == ["TXN-A1", "TXN-A2"]

    wide = client.get("/me/transactions", headers=auth_headers).json()
    assert "TXN-A3" in [row["transaction_id"] for row in wide]


def test_amount_usd_effective_coalesces_null_on_usd_rows(client, auth_headers):
    rows = {row["transaction_id"]: row for row in client.get("/me/transactions", headers=auth_headers).json()}
    # TXN-A1 is USD with null amount_usd -> effective falls back to amount
    assert rows["TXN-A1"]["amount_usd_effective"] == "49.90"
    # TXN-A2 is COP with amount_usd present -> effective is amount_usd
    assert rows["TXN-A2"]["amount_usd_effective"] == "0.30"


def test_foreign_transaction_returns_404(client, auth_headers):
    response = client.get("/me/transactions/TXN-B1", headers=auth_headers)
    assert response.status_code == 404


def test_unknown_transaction_returns_404(client, auth_headers):
    assert client.get("/me/transactions/TXN-NOPE", headers=auth_headers).status_code == 404


def test_transactions_require_valid_token(client):
    assert client.get("/me/transactions").status_code == 401
