"""Robustheit gegen Typ-Korruption INNERHALB gültiger JSON-Dateien.

Die übrigen Tests decken Datei-Ebene ab (fehlend, kaputtes JSON, falscher
Top-Level-Typ). Hier geht es um die Stufe darunter: die Datei ist
gültiges JSON, aber ein einzelnes Feld hat den falschen Typ. Genau dort
lagen zwei 500er, die den ganzen Endpunkt mitrissen - und damit auch die
Anzeige der Bots, mit denen alles in Ordnung war.
"""

import json

import pytest
from fastapi.testclient import TestClient

from app.export import build_trades_csv
from app.ledger_readers import summarize_grid
from app.main import app

client = TestClient(app)
VALID_TOKEN = "a" * 64


@pytest.fixture(autouse=True)
def dashboard_token(monkeypatch):
    monkeypatch.setenv("DASHBOARD_TOKEN", VALID_TOKEN)
    yield


def _write(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


def _seed(tmp_path, monkeypatch, **overrides):
    files = {
        "trade_ledger.json": [],
        "grid_positions.json": [],
        "trend_ledger.json": [],
        "allocator_state.json": {},
    }
    files.update(overrides)
    for name, data in files.items():
        _write(tmp_path / name, data)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))


def _grid_open(level_index):
    return {
        "id": "x",
        "level_index": level_index,
        "buy_price": 100.0,
        "target_sell_price": 110.0,
        "quantity": 1.0,
        "quote_spent": 100.0,
        "bought_at": "2026-01-01T00:00:00+00:00",
        "dry_run": False,
        "status": "open",
    }


def test_grid_level_index_as_string_does_not_crash_status(tmp_path, monkeypatch):
    _seed(
        tmp_path,
        monkeypatch,
        **{"grid_positions.json": [_grid_open("zwei"), _grid_open(1)]},
    )

    response = client.get("/api/status", headers={"X-Dashboard-Token": VALID_TOKEN})

    assert response.status_code == 200
    body = response.json()
    assert body["grid"]["status"] == "ok"
    # Die anderen drei Bots bleiben sichtbar - das ist der eigentliche Punkt.
    assert body["dca"]["status"] == "ok"
    assert body["trend"]["status"] == "ok"


def test_grid_level_index_as_string_sorts_deterministically(tmp_path):
    path = tmp_path / "grid_positions.json"
    _write(path, [_grid_open("zwei"), _grid_open(1), _grid_open(0)])

    result = summarize_grid(path)

    assert result["status"] == "ok"
    # Unlesbarer Wert sortiert nach -1, also an den Anfang; der Rest
    # bleibt numerisch aufsteigend.
    assert [p["level_index"] for p in result["open_positions"]] == ["zwei", 0, 1]


def test_dca_numeric_timestamp_does_not_crash_export(tmp_path, monkeypatch):
    _seed(
        tmp_path,
        monkeypatch,
        **{
            "trade_ledger.json": [
                {"timestamp": 1735689600, "symbol": "BTCUSDT", "quantity": 1.0,
                 "price": 10.0, "quote_spent": 10.0, "dry_run": False},
                {"timestamp": "2026-01-01T00:00:00+00:00", "symbol": "BTCUSDT",
                 "quantity": 1.0, "price": 10.0, "quote_spent": 10.0, "dry_run": False},
            ]
        },
    )

    for params in ({}, {"period": "year"}):
        response = client.get(
            "/api/export/trades",
            headers={"X-Dashboard-Token": VALID_TOKEN},
            params=params,
        )
        assert response.status_code == 200, params
        assert response.text.startswith("datum_zeit_utc,")


def test_export_with_mixed_timestamp_types_sorts_and_filters(tmp_path):
    """Direkt auf Funktionsebene: gemischte Typen dürfen weder beim
    Sortieren noch beim Zeitraum-Filter eine Exception auslösen."""
    dca = tmp_path / "trade_ledger.json"
    grid = tmp_path / "grid_positions.json"
    trend = tmp_path / "trend_ledger.json"
    _write(grid, [])
    _write(trend, [])
    _write(
        dca,
        [
            {"timestamp": 42, "symbol": "BTCUSDT", "quantity": 1.0, "price": 1.0,
             "quote_spent": 1.0, "dry_run": False},
            {"timestamp": "2026-01-01T00:00:00+00:00", "symbol": "BTCUSDT",
             "quantity": 1.0, "price": 1.0, "quote_spent": 1.0, "dry_run": False},
        ],
    )

    alle = build_trades_csv(dca, grid, trend)
    assert alle.count("BTCUSDT") == 2  # beide Zeilen bleiben erhalten

    # Beim gefilterten Export fliegt der unlesbare Zeitstempel raus,
    # statt geraten zu werden.
    jahr = build_trades_csv(dca, grid, trend, period="year")
    assert jahr.count("BTCUSDT") <= 1


def test_allocator_non_numeric_fraction_does_not_crash(tmp_path, monkeypatch):
    _seed(
        tmp_path,
        monkeypatch,
        **{"allocator_state.json": {"trend_fraction": "viel", "updated_at": "t"}},
    )

    response = client.get("/api/status", headers={"X-Dashboard-Token": VALID_TOKEN})

    assert response.status_code == 200
    assert response.json()["allocator"]["trend_fraction"] is None
