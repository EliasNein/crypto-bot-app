import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def dashboard_token(monkeypatch):
    monkeypatch.setenv("DASHBOARD_TOKEN", "secret-token")
    yield


def test_health_requires_no_token():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_status_without_token_is_rejected():
    response = client.get("/api/status")
    assert response.status_code == 401


def test_status_with_wrong_token_is_rejected():
    response = client.get("/api/status", headers={"X-Dashboard-Token": "wrong"})
    assert response.status_code == 401


def test_status_with_correct_header_token_is_accepted():
    response = client.get("/api/status", headers={"X-Dashboard-Token": "secret-token"})
    assert response.status_code == 200


def test_status_with_correct_query_token_is_accepted():
    response = client.get("/api/status", params={"token": "secret-token"})
    assert response.status_code == 200


def test_status_without_configured_server_token_returns_500(monkeypatch):
    monkeypatch.delenv("DASHBOARD_TOKEN", raising=False)
    response = client.get("/api/status", headers={"X-Dashboard-Token": "anything"})
    assert response.status_code == 500
