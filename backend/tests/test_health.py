from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_is_up():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_db_health_reports_503_when_the_database_is_unreachable(monkeypatch):
    monkeypatch.setenv("DB_HOST", "127.0.0.1")
    monkeypatch.setenv("DB_PORT", "1")  # nothing listens here
    monkeypatch.setenv("DB_USER", "x")
    monkeypatch.setenv("DB_PASSWORD", "x")
    response = client.get("/health/db")
    assert response.status_code == 503
    assert "unreachable" in response.json()["detail"]
