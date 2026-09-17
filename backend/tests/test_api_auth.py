import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

# Realistisches Token (64 Hex-Zeichen, wie `openssl rand -hex 32` es
# erzeugt) - kurze Testtokens werden vom Entropie-Check abgelehnt.
VALID_TOKEN = "a" * 64


@pytest.fixture(autouse=True)
def dashboard_token(monkeypatch):
    monkeypatch.setenv("DASHBOARD_TOKEN", VALID_TOKEN)
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
    response = client.get("/api/status", headers={"X-Dashboard-Token": VALID_TOKEN})
    assert response.status_code == 200


def test_status_query_token_is_no_longer_accepted():
    """Der ?token=-Weg wurde entfernt: Query-Strings landen im
    Access-Log, in der Browser-History und in den Cloudflare-Logs."""
    response = client.get("/api/status", params={"token": VALID_TOKEN})
    assert response.status_code == 401


def test_status_without_configured_server_token_returns_500(monkeypatch):
    monkeypatch.delenv("DASHBOARD_TOKEN", raising=False)
    response = client.get("/api/status", headers={"X-Dashboard-Token": "anything"})
    assert response.status_code == 500


@pytest.mark.parametrize("weak", ["change-me", "CHANGE-ME", "secret", "kurz", "a" * 31])
def test_weak_server_token_is_refused_even_when_client_sends_it(monkeypatch, weak):
    """Fail closed: ein zu schwaches Server-Token darf gar nichts
    ausliefern, auch nicht dem, der es korrekt mitschickt."""
    monkeypatch.setenv("DASHBOARD_TOKEN", weak)
    response = client.get("/api/status", headers={"X-Dashboard-Token": weak})
    assert response.status_code == 500


def test_token_of_minimum_length_is_accepted(monkeypatch):
    token = "b" * 32
    monkeypatch.setenv("DASHBOARD_TOKEN", token)
    response = client.get("/api/status", headers={"X-Dashboard-Token": token})
    assert response.status_code == 200


def test_failed_attempt_is_logged_without_leaking_the_token(caplog):
    with caplog.at_level("WARNING"):
        client.get("/api/status", headers={"X-Dashboard-Token": "falsches-token-123"})

    assert "Abgelehnter Zugriff" in caplog.text
    # Der übermittelte Wert darf nirgends im Log auftauchen.
    assert "falsches-token-123" not in caplog.text


def test_docs_endpoints_are_disabled():
    """Ohne Token öffentlich erreichbare API-Doku wäre unnötige
    Angriffsfläche auf einem öffentlich exponierten Dashboard."""
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404, path
