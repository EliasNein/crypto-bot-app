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


def _auth_get(path="/api/status"):
    return client.get(path, headers={"X-Dashboard-Token": VALID_TOKEN})


def test_status_aggregates_all_four_bots(tmp_path, monkeypatch):
    (tmp_path / "trade_ledger.json").write_text(
        json.dumps([{"timestamp": "t", "symbol": "BTCUSDT", "quote_spent": 10.0, "quantity": 1.0, "price": 10.0, "dry_run": False}]),
        encoding="utf-8",
    )
    (tmp_path / "grid_positions.json").write_text(json.dumps([]), encoding="utf-8")
    (tmp_path / "trend_ledger.json").write_text(json.dumps([]), encoding="utf-8")
    (tmp_path / "allocator_state.json").write_text(
        json.dumps({"trend_fraction": 0.5, "updated_at": "t"}), encoding="utf-8"
    )
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    response = _auth_get()

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {
        "dca",
        "grid",
        "trend",
        "allocator",
        "overview",
        "investment_activity",
        "pnl_verlauf",
        "heartbeat",
    }
    assert body["dca"]["status"] == "ok"
    assert body["grid"]["status"] == "ok"
    assert body["trend"]["status"] == "ok"
    assert body["allocator"]["status"] == "ok"
    assert body["allocator"]["trend_fraction"] == 0.5
    assert body["overview"]["gesamtgewinn"] == 0.0
    assert body["overview"]["gesamtverlust"] == 0.0
    assert body["overview"]["unrealisiert_geschätzt"]["dca"] == {"quantity": 1.0, "avg_price": 10.0}


def test_status_reports_no_data_per_bot_without_failing_others(tmp_path, monkeypatch):
    # Nur die Grid-Datei existiert und ist gültig, die anderen drei fehlen
    # oder sind kaputt - der Endpunkt muss trotzdem 200 liefern und pro Bot
    # unabhängig entscheiden.
    (tmp_path / "grid_positions.json").write_text(json.dumps([]), encoding="utf-8")
    (tmp_path / "trend_ledger.json").write_text("not valid json", encoding="utf-8")
    # trade_ledger.json und allocator_state.json fehlen komplett.
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    response = _auth_get()

    assert response.status_code == 200
    body = response.json()
    assert body["dca"]["status"] == "no_data"
    assert body["grid"]["status"] == "ok"
    assert body["trend"]["status"] == "no_data"
    assert body["allocator"]["status"] == "no_data"

    # Fehlende/kaputte Dateien dürfen im Overview nicht wie "0 Bestand"
    # aussehen - nur die gültige, leere Grid-Datei bekommt einen Nullwert.
    unrealized = body["overview"]["unrealisiert_geschätzt"]
    assert unrealized["dca"] is None
    assert unrealized["trend"] is None
    assert unrealized["grid"] == {"quantity": 0.0, "avg_price": None}
