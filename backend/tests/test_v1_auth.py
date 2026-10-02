from fastapi.testclient import TestClient

from app.main import create_app
from tests.fakes import CUS_A, PASSWORD_A, FakeStore


def login(client, username="ana.garcia", password=PASSWORD_A):
    return client.post("/v1/auth/login", json={"username": username, "password": password})


def test_login_returns_a_session_token_and_the_customer(client):
    response = login(client)
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 120 * 60
    assert body["customer"] == {"customer_id": CUS_A, "first_name": "Ana", "last_name": "García", "country": "Colombia"}


def test_the_token_from_login_opens_the_data_routes(client):
    token = login(client).json()["session_token"]
    response = client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["customer_id"] == CUS_A


def test_user_name_is_not_case_sensitive(client):
    assert login(client, username="  ANA.Garcia ").status_code == 200


def test_wrong_password_and_unknown_user_get_the_same_answer(client):
    wrong = login(client, password="mala")
    unknown = login(client, username="nobody", password="mala")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_five_failures_lock_the_account_even_for_the_right_password(client):
    for _ in range(5):
        assert login(client, password="mala").status_code == 401
    locked = login(client)
    assert locked.status_code == 429
    assert int(locked.headers["Retry-After"]) > 0


def test_a_success_resets_the_failure_count(client, store):
    for _ in range(4):
        login(client, password="mala")
    assert login(client).status_code == 200
    assert store.credentials["ana.garcia"]["failed_attempts"] == 0
    assert login(client, password="mala").status_code == 401  # not locked: the count started again


def test_empty_fields_are_rejected_by_validation(client):
    assert client.post("/v1/auth/login", json={"username": "", "password": "x"}).status_code == 422
    assert client.post("/v1/auth/login", json={"username": "ana"}).status_code == 422


def test_the_password_is_never_in_a_response(client):
    body = login(client).text
    assert PASSWORD_A not in body and "password_hash" not in body


def test_legacy_login_for_the_agent_still_works(client):
    response = client.post("/session", json={"customer_id": CUS_A, "document_number": "CC-123"})
    assert response.status_code == 200


def test_demo_accounts_are_off_by_default(client):
    assert client.get("/v1/auth/demo-accounts").status_code == 404


def test_demo_accounts_list_only_demo_rows_and_the_shared_password(monkeypatch):
    monkeypatch.setenv("DEMO_ACCOUNTS_ENABLED", "true")
    monkeypatch.setenv("DEMO_PASSWORD", "Demo-2026")
    body = TestClient(create_app(FakeStore())).get("/v1/auth/demo-accounts").json()
    assert [a["username"] for a in body["accounts"]] == ["ana.garcia"]  # bruno.souza is not a demo account
    assert body["password"] == "Demo-2026"
    assert "password_hash" not in str(body)
