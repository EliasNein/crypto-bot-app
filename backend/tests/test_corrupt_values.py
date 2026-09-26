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
from app.ledger_readers import _parse_utc_datetime, summarize_grid
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


# --- Randdaten mit Zeitzonen-Offset (App-Check 26.09.2026, Befund 1) -------
#
# fromisoformat() liest diese Werte fehlerfrei, erst die Umrechnung nach
# UTC läuft aus dem datetime-Bereich (Jahr 1 minus 5 Stunden, Jahr 9999
# plus 5 Stunden) und wirft OverflowError. Vor dem Fix riss das den
# ganzen /api/status mit - alle vier Bots weg. Erwartet ist dieselbe
# Regel wie bei jedem anderen unlesbaren Zeitstempel: der WERT wird
# übersprungen, der Bot bleibt "ok".

JAHR_1_PLUS_5 = "0001-01-01T00:00:00+05:00"
JAHR_9999_MINUS_5 = "9999-12-31T23:59:59-05:00"
GUTER_TAG = "2026-01-01T12:00:00+00:00"


def _dca_buy(timestamp):
    return {"timestamp": timestamp, "symbol": "BTCUSDT", "quantity": 0.001,
            "price": 50000.0, "quote_spent": 50.0, "dry_run": False}


def _grid_closed(sold_at, pnl):
    return {**_grid_open(0), "status": "closed", "bought_at": GUTER_TAG,
            "sell_price": 110.0, "sold_at": sold_at, "realized_pnl": pnl}


def _heartbeat(last_successful_cycle):
    return {"last_successful_cycle": last_successful_cycle,
            "last_cycle_attempt": GUTER_TAG, "consecutive_failures": 0}


def _check_dca_buy_skipped_in_activity(body):
    # Beide Käufe bleiben in der DCA-Karte, nur die Tageszählung
    # ignoriert den unlesbaren.
    assert body["dca"]["metrics"]["real_trades"] == 2
    assert body["investment_activity"]["days_with_activity"] == 1


def _check_grid_close_skipped_in_history(body):
    # Der Betrag zählt weiter ins Gesamtergebnis, nur der Verlauf kann
    # ihn keinem Tag zuordnen und lässt ihn aus.
    assert body["overview"]["gesamtgewinn"] == pytest.approx(3.0)
    assert body["pnl_verlauf"] == [
        {"datum": "2026-01-01", "realisierte_pnl_an_diesem_tag": 1.0,
         "kumulierte_pnl_bis_zu_diesem_tag": 1.0}
    ]


def _check_heartbeat_treated_as_no_success(body):
    beat = body["heartbeat"]["dca"]
    assert beat["status"] == "ok"
    assert beat["reason"] == "no_confirmed_success"
    assert beat["seconds_since_success"] is None
    assert beat["last_successful_cycle"] == JAHR_1_PLUS_5  # Rohwert bleibt sichtbar


@pytest.mark.parametrize(
    "overrides, check",
    [
        pytest.param(
            {"trade_ledger.json": [_dca_buy(JAHR_1_PLUS_5), _dca_buy(GUTER_TAG)]},
            _check_dca_buy_skipped_in_activity,
            id="dca-jahr-1",
        ),
        pytest.param(
            {"trade_ledger.json": [_dca_buy(JAHR_9999_MINUS_5), _dca_buy(GUTER_TAG)]},
            _check_dca_buy_skipped_in_activity,
            id="dca-jahr-9999",
        ),
        pytest.param(
            {"grid_positions.json": [_grid_closed(JAHR_1_PLUS_5, 2.0),
                                     _grid_closed(GUTER_TAG, 1.0)]},
            _check_grid_close_skipped_in_history,
            id="grid-sold-at-jahr-1",
        ),
        pytest.param(
            {"heartbeat_dca.json": _heartbeat(JAHR_1_PLUS_5)},
            _check_heartbeat_treated_as_no_success,
            id="heartbeat-jahr-1",
        ),
    ],
)
def test_edge_date_with_offset_does_not_crash_status(tmp_path, monkeypatch, overrides, check):
    _seed(
        tmp_path,
        monkeypatch,
        **{"allocator_state.json": {"trend_fraction": 0.3, "updated_at": GUTER_TAG}},
        **overrides,
    )

    response = client.get("/api/status", headers={"X-Dashboard-Token": VALID_TOKEN})

    assert response.status_code == 200
    body = response.json()
    # Kein Bot fällt auf "keine Daten" - auch nicht der betroffene.
    for bot in ("dca", "grid", "trend", "allocator"):
        assert body[bot]["status"] == "ok", bot
    check(body)

    # Der Export hat einen eigenen Parser und war nie betroffen - bleibt so.
    export = client.get("/api/export/trades", headers={"X-Dashboard-Token": VALID_TOKEN},
                        params={"period": "year"})
    assert export.status_code == 200


@pytest.mark.parametrize("value", [JAHR_1_PLUS_5, JAHR_9999_MINUS_5])
def test_parse_utc_datetime_returns_none_on_overflow(value):
    assert _parse_utc_datetime(value) is None


def test_parse_utc_datetime_keeps_valid_edge_dates():
    """Gegenprobe: dieselben Randdaten OHNE Überlauf bleiben lesbar."""
    assert _parse_utc_datetime("0001-01-01T00:00:00+00:00").year == 1
    assert _parse_utc_datetime("9999-12-31T23:59:59-00:00").year == 9999
    assert _parse_utc_datetime("0001-01-01T12:00:00+05:00").hour == 7
