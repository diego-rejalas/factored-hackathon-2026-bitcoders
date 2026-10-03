import json

from fastapi.testclient import TestClient

from app.main import create_app
from tests.fakes import FakeStore


def lines(capsys) -> list[dict]:
    return [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")]


def test_every_response_carries_a_request_id(client):
    response = client.get("/health")
    assert len(response.headers["X-Request-ID"]) >= 8


def test_a_well_formed_incoming_id_is_kept_so_the_action_can_be_followed(client):
    response = client.get("/health", headers={"X-Request-ID": "bff-7f3a9c2e-0001"})
    assert response.headers["X-Request-ID"] == "bff-7f3a9c2e-0001"


def test_a_malformed_id_is_replaced_and_never_echoed(client):
    for bad in ("short", "has spaces in it!!", "x" * 101, "<script>alert(1)</script>"):
        got = client.get("/health", headers={"X-Request-ID": bad}).headers["X-Request-ID"]
        assert got != bad and len(got) == 32  # a fresh uuid


def test_ids_are_different_per_request_when_none_comes_in(client):
    assert client.get("/health").headers["X-Request-ID"] != client.get("/health").headers["X-Request-ID"]


def test_one_json_log_line_per_request_with_severity_and_the_route_template(client, auth_headers, capsys):
    client.get("/v1/me/products", headers={**auth_headers, "X-Request-ID": "trace-0000000001"})
    entry = [e for e in lines(capsys) if e.get("path") == "/v1/me/products"][-1]
    assert entry["severity"] == "INFO" and entry["status"] == 200 and entry["request_id"] == "trace-0000000001"
    assert entry["service"] == "backend" and entry["method"] == "GET" and entry["duration_ms"] >= 0


def test_the_log_uses_the_route_template_not_the_concrete_path(client, auth_headers, capsys):
    case_id = client.post(
        "/v1/disputes", json={"transaction_id": "TXN-A1", "reason_code": "x", "summary": "s"}, headers=auth_headers
    ).json()["case_id"]
    capsys.readouterr()
    client.get(f"/v1/disputes/{case_id}", headers=auth_headers)
    assert [e["path"] for e in lines(capsys)] == ["/v1/disputes/{case_id}"]


def test_client_errors_are_warnings_and_server_errors_are_errors(client, auth_headers, store, capsys):
    client.get("/v1/me/products/NOPE", headers=auth_headers)  # 404
    client.get("/v1/me")  # 401
    severities = {e["status"]: e["severity"] for e in lines(capsys) if "status" in e}
    assert severities == {404: "WARNING", 401: "WARNING"}

    async def down():
        raise ConnectionError("db down")

    store.ping = down
    client.get("/ready")
    assert {e["status"]: e["severity"] for e in lines(capsys) if "status" in e} == {503: "ERROR"}


def test_a_crash_is_logged_as_an_error_with_the_exception_name_and_still_raises(store, capsys):
    app = create_app(store)

    @app.get("/boom")
    async def boom():
        raise RuntimeError("secret detail that must not be logged")

    quiet = TestClient(app, raise_server_exceptions=False)
    assert quiet.get("/boom").status_code == 500
    entry = [e for e in lines(capsys) if e.get("path") == "/boom"][-1]
    assert entry["severity"] == "ERROR" and entry["error"] == "RuntimeError"
    assert "secret detail" not in json.dumps(entry)


def test_nothing_sensitive_reaches_the_log(client, auth_headers, capsys):
    token = auth_headers["Authorization"].split()[1]
    client.get("/v1/me/transactions?merchant=farmacia", headers=auth_headers)
    client.post("/v1/auth/login", json={"username": "ana.garcia", "password": "Clave-Segura-1"})
    out = capsys.readouterr().out
    assert token not in out and "Authorization" not in out and "Clave-Segura-1" not in out
    assert "farmacia" not in out  # the query string is not logged
