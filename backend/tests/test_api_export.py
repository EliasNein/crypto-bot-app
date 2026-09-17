import json

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def dashboard_token(monkeypatch):
    monkeypatch.setenv("DASHBOARD_TOKEN", "secret-token")
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

    response = client.get("/api/export/trades", headers={"X-Dashboard-Token": "secret-token"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    assert "trades_export.csv" in response.headers["content-disposition"]
    assert response.text.startswith("datum_zeit_utc,")
    assert "# Dies ist keine Steuerberatung" in response.text


def test_export_accepts_query_token(tmp_path, monkeypatch):
    _seed_empty_ledgers(tmp_path, monkeypatch)

    response = client.get("/api/export/trades", params={"token": "secret-token"})

    assert response.status_code == 200


@pytest.mark.parametrize("period", ["all", "week", "month", "year"])
def test_export_accepts_all_valid_period_values(tmp_path, monkeypatch, period):
    _seed_empty_ledgers(tmp_path, monkeypatch)

    response = client.get(
        "/api/export/trades",
        headers={"X-Dashboard-Token": "secret-token"},
        params={"period": period},
    )

    assert response.status_code == 200
    assert "# Zeitraum:" in response.text


def test_export_with_invalid_period_returns_400_not_500(tmp_path, monkeypatch):
    _seed_empty_ledgers(tmp_path, monkeypatch)

    response = client.get(
        "/api/export/trades",
        headers={"X-Dashboard-Token": "secret-token"},
        params={"period": "decade"},
    )

    assert response.status_code == 400
    assert "period" in response.json()["detail"]
