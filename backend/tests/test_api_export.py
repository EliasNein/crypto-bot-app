import json

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

# 64 Hex-Zeichen wie aus `openssl rand -hex 32` - kürzere Tokens weist
# der Entropie-Check in auth.py ab.
VALID_TOKEN = "a" * 64


@pytest.fixture(autouse=True)
def dashboard_token(monkeypatch):
    monkeypatch.setenv("DASHBOARD_TOKEN", VALID_TOKEN)
    yield


def _seed_empty_ledgers(tmp_path, monkeypatch):
    for name in ("trade_ledger.json", "grid_positions.json", "trend_ledger.json"):
        (tmp_path / name).write_text(json.dumps([]), encoding="utf-8")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))


def test_export_without_token_is_rejected(tmp_path, monkeypatch):
    _seed_empty_ledgers(tmp_path, monkeypatch)
    response = client.get("/api/export/trades")
    assert response.status_code == 401


def test_export_with_correct_token_returns_csv(tmp_path, monkeypatch):
    _seed_empty_ledgers(tmp_path, monkeypatch)

    response = client.get("/api/export/trades", headers={"X-Dashboard-Token": VALID_TOKEN})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    assert "trades_export.csv" in response.headers["content-disposition"]
    assert response.text.startswith("datum_zeit_utc,")
    assert "# Dies ist keine Steuerberatung" in response.text


def test_export_query_token_is_no_longer_accepted(tmp_path, monkeypatch):
    """Früher erlaubt - jetzt abgelehnt, damit das Token nicht über den
    Query-String in Access-Log, History und Cloudflare-Logs wandert."""
    _seed_empty_ledgers(tmp_path, monkeypatch)

    response = client.get("/api/export/trades", params={"token": VALID_TOKEN})

    assert response.status_code == 401


@pytest.mark.parametrize("period", ["all", "week", "month", "year"])
def test_export_accepts_all_valid_period_values(tmp_path, monkeypatch, period):
    _seed_empty_ledgers(tmp_path, monkeypatch)

    response = client.get(
        "/api/export/trades",
        headers={"X-Dashboard-Token": VALID_TOKEN},
        params={"period": period},
    )

    assert response.status_code == 200
    assert "# Zeitraum:" in response.text


def test_export_with_invalid_period_returns_400_not_500(tmp_path, monkeypatch):
    _seed_empty_ledgers(tmp_path, monkeypatch)

    response = client.get(
        "/api/export/trades",
        headers={"X-Dashboard-Token": VALID_TOKEN},
        params={"period": "decade"},
    )

    assert response.status_code == 400
    assert "period" in response.json()["detail"]
