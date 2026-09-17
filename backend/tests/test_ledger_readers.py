import json

import pytest

from app.ledger_readers import (
    summarize_allocator,
    summarize_dca,
    summarize_grid,
    summarize_overview,
    summarize_trend,
)


def _write(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


# --- DCA ---------------------------------------------------------------


def test_summarize_dca_parses_real_and_dry_run_buys(tmp_path):
    path = tmp_path / "trade_ledger.json"
    _write(
        path,
        [
            {"timestamp": "2026-01-01T00:00:00+00:00", "symbol": "BTCUSDT", "quote_spent": 10.0, "quantity": 1.0, "price": 10.0, "dry_run": False},
            {"timestamp": "2026-01-02T00:00:00+00:00", "symbol": "BTCUSDT", "quote_spent": 10.0, "quantity": 0.5, "price": 20.0, "dry_run": False},
            {"timestamp": "2026-01-03T00:00:00+00:00", "symbol": "BTCUSDT", "quote_spent": 10.0, "quantity": 1.0, "price": 10.0, "dry_run": True},
        ],
    )

    result = summarize_dca(path)

    assert result["status"] == "ok"
    assert result["metrics"]["total_trades"] == 3
    assert result["metrics"]["real_trades"] == 2
    assert result["metrics"]["dry_run_trades"] == 1
    assert result["metrics"]["total_quantity"] == pytest.approx(1.5)
    assert result["metrics"]["total_spent"] == pytest.approx(20.0)
    assert len(result["open_positions"]) == 2
    assert result["last_activity"] == "2026-01-03T00:00:00+00:00"


def test_summarize_dca_missing_file_returns_no_data(tmp_path):
    result = summarize_dca(tmp_path / "does_not_exist.json")

    assert result["status"] == "no_data"
    assert "error" in result


def test_summarize_dca_corrupt_json_returns_no_data(tmp_path):
    path = tmp_path / "trade_ledger.json"
    path.write_text("{not valid json", encoding="utf-8")

    result = summarize_dca(path)

    assert result["status"] == "no_data"
    assert "error" in result


def test_summarize_dca_wrong_top_level_type_returns_no_data(tmp_path):
    path = tmp_path / "trade_ledger.json"
    _write(path, {"unexpected": "dict instead of list"})

    result = summarize_dca(path)

    assert result["status"] == "no_data"


# --- Grid ----------------------------------------------------------------


def test_summarize_grid_open_and_closed_positions(tmp_path):
    path = tmp_path / "grid_positions.json"
    _write(
        path,
        [
            {
                "id": "a",
                "level_index": 1,
                "buy_price": 100.0,
                "target_sell_price": 105.0,
                "quantity": 1.0,
                "quote_spent": 100.0,
                "bought_at": "2026-01-01T00:00:00+00:00",
                "dry_run": True,
                "status": "open",
                "sell_price": None,
                "sold_at": None,
                "realized_pnl": None,
            },
            {
                "id": "b",
                "level_index": 0,
                "buy_price": 90.0,
                "target_sell_price": 95.0,
                "quantity": 1.0,
                "quote_spent": 90.0,
                "bought_at": "2025-12-31T00:00:00+00:00",
                "dry_run": False,
                "status": "closed",
                "sell_price": 95.0,
                "sold_at": "2026-01-02T00:00:00+00:00",
                "realized_pnl": 5.0,
            },
        ],
    )

    result = summarize_grid(path)

    assert result["status"] == "ok"
    assert result["metrics"]["open_positions"] == 1
    assert result["metrics"]["closed_positions"] == 1
    assert result["metrics"]["realized_pnl"] == pytest.approx(5.0)
    assert len(result["open_positions"]) == 1
    assert result["open_positions"][0]["id"] == "a"
    assert result["last_activity"] == "2026-01-02T00:00:00+00:00"


def test_summarize_grid_missing_file_returns_no_data(tmp_path):
    result = summarize_grid(tmp_path / "missing.json")
    assert result["status"] == "no_data"


# --- Trend -----------------------------------------------------------------


def test_summarize_trend_single_open_position(tmp_path):
    path = tmp_path / "trend_ledger.json"
    _write(
        path,
        [
            {
                "id": "x",
                "entry_price": 100.0,
                "entry_time": "2026-01-01T00:00:00+00:00",
                "quantity": 1.0,
                "quote_spent": 100.0,
                "dry_run": True,
                "status": "open",
                "exit_price": None,
                "exit_time": None,
                "exit_reason": None,
                "realized_pnl": None,
            }
        ],
    )

    result = summarize_trend(path)

    assert result["status"] == "ok"
    assert result["metrics"]["open_trades"] == 1
    assert len(result["open_positions"]) == 1
    assert result["open_positions"][0]["entry_price"] == 100.0
    assert result["last_activity"] == "2026-01-01T00:00:00+00:00"


def test_summarize_trend_corrupt_file_returns_no_data(tmp_path):
    path = tmp_path / "trend_ledger.json"
    path.write_text("not json at all", encoding="utf-8")

    result = summarize_trend(path)

    assert result["status"] == "no_data"
    assert "error" in result


# --- Allocator ---------------------------------------------------------------


def test_summarize_allocator_reads_state_dict(tmp_path):
    path = tmp_path / "allocator_state.json"
    _write(
        path,
        {
            "trend_fraction": 0.35,
            "raw_target_fraction": 0.4,
            "last_notified_fraction": 0.3,
            "gap_pct": 2.1,
            "direction": "up",
            "updated_at": "2026-01-05T00:00:00+00:00",
        },
    )

    result = summarize_allocator(path)

    assert result["status"] == "ok"
    assert result["trend_fraction"] == pytest.approx(0.35)
    assert result["dca_fraction"] == pytest.approx(0.65)
    assert result["direction"] == "up"
    assert result["last_activity"] == "2026-01-05T00:00:00+00:00"


def test_summarize_allocator_missing_file_returns_no_data(tmp_path):
    result = summarize_allocator(tmp_path / "missing.json")
    assert result["status"] == "no_data"


def test_summarize_allocator_wrong_top_level_type_returns_no_data(tmp_path):
    path = tmp_path / "allocator_state.json"
    _write(path, [1, 2, 3])

    result = summarize_allocator(path)

    assert result["status"] == "no_data"


# --- Overview (Gesamtgewinn/-verlust + unrealisierter Bestand) -------------


def _grid_closed(realized_pnl, dry_run):
    return {
        "id": "g",
        "level_index": 0,
        "buy_price": 100.0,
        "target_sell_price": 105.0,
        "quantity": 1.0,
        "quote_spent": 100.0,
        "bought_at": "2026-01-01T00:00:00+00:00",
        "dry_run": dry_run,
        "status": "closed",
        "sell_price": 100.0 + realized_pnl,
        "sold_at": "2026-01-02T00:00:00+00:00",
        "realized_pnl": realized_pnl,
    }


def _trend_closed(realized_pnl, dry_run):
    return {
        "id": "t",
        "entry_price": 100.0,
        "entry_time": "2026-01-01T00:00:00+00:00",
        "quantity": 1.0,
        "quote_spent": 100.0,
        "dry_run": dry_run,
        "status": "closed",
        "exit_price": 100.0 + realized_pnl,
        "exit_time": "2026-01-02T00:00:00+00:00",
        "exit_reason": "target",
        "realized_pnl": realized_pnl,
    }


def test_overview_mixes_real_and_dry_run_only_counts_real(tmp_path):
    dca_path = tmp_path / "trade_ledger.json"
    grid_path = tmp_path / "grid_positions.json"
    trend_path = tmp_path / "trend_ledger.json"

    _write(dca_path, [])
    _write(
        grid_path,
        [
            _grid_closed(realized_pnl=5.0, dry_run=False),
            _grid_closed(realized_pnl=999.0, dry_run=True),  # darf nicht zählen
        ],
    )
    _write(
        trend_path,
        [
            _trend_closed(realized_pnl=-2.0, dry_run=False),
            _trend_closed(realized_pnl=-999.0, dry_run=True),  # darf nicht zählen
        ],
    )

    result = summarize_overview(dca_path, grid_path, trend_path)

    assert result["gesamtgewinn"] == pytest.approx(5.0)
    assert result["gesamtverlust"] == pytest.approx(-2.0)


def test_overview_only_gains_leaves_loss_at_zero(tmp_path):
    dca_path = tmp_path / "trade_ledger.json"
    grid_path = tmp_path / "grid_positions.json"
    trend_path = tmp_path / "trend_ledger.json"

    _write(dca_path, [])
    _write(grid_path, [_grid_closed(realized_pnl=3.0, dry_run=False)])
    _write(trend_path, [_trend_closed(realized_pnl=7.0, dry_run=False)])

    result = summarize_overview(dca_path, grid_path, trend_path)

    assert result["gesamtgewinn"] == pytest.approx(10.0)
    assert result["gesamtverlust"] == pytest.approx(0.0)


def test_overview_only_losses_leaves_gain_at_zero(tmp_path):
    dca_path = tmp_path / "trade_ledger.json"
    grid_path = tmp_path / "grid_positions.json"
    trend_path = tmp_path / "trend_ledger.json"

    _write(dca_path, [])
    _write(grid_path, [_grid_closed(realized_pnl=-4.0, dry_run=False)])
    _write(trend_path, [_trend_closed(realized_pnl=-6.0, dry_run=False)])

    result = summarize_overview(dca_path, grid_path, trend_path)

    assert result["gesamtgewinn"] == pytest.approx(0.0)
    assert result["gesamtverlust"] == pytest.approx(-10.0)


def test_overview_empty_ledgers_report_zero_holdings_not_none(tmp_path):
    dca_path = tmp_path / "trade_ledger.json"
    grid_path = tmp_path / "grid_positions.json"
    trend_path = tmp_path / "trend_ledger.json"

    _write(dca_path, [])
    _write(grid_path, [])
    _write(trend_path, [])

    result = summarize_overview(dca_path, grid_path, trend_path)

    assert result["gesamtgewinn"] == pytest.approx(0.0)
    assert result["gesamtverlust"] == pytest.approx(0.0)
    unrealized = result["unrealisiert_geschätzt"]
    # Datei vorhanden und gültig, aber leer: 0 Bestand ist eine echte Aussage,
    # kein fehlender Wert - deshalb ein Objekt mit quantity 0.0, nicht None.
    assert unrealized["dca"] == {"quantity": 0.0, "avg_price": None}
    assert unrealized["grid"] == {"quantity": 0.0, "avg_price": None}
    assert unrealized["trend"] == {"quantity": 0.0, "avg_price": None}


def test_overview_missing_file_reports_none_not_zero(tmp_path):
    dca_path = tmp_path / "trade_ledger.json"
    grid_path = tmp_path / "grid_positions.json"  # existiert nicht
    trend_path = tmp_path / "trend_ledger.json"

    _write(dca_path, [])
    _write(trend_path, [])

    result = summarize_overview(dca_path, grid_path, trend_path)

    # Ein Datenproblem darf nicht wie "0 BTC gehalten" aussehen.
    assert result["unrealisiert_geschätzt"]["grid"] is None
    assert result["unrealisiert_geschätzt"]["dca"] == {"quantity": 0.0, "avg_price": None}


def test_overview_dca_unrealized_independent_of_grid_and_trend(tmp_path):
    dca_path = tmp_path / "trade_ledger.json"
    grid_path = tmp_path / "grid_positions.json"
    trend_path = tmp_path / "trend_ledger.json"

    _write(
        dca_path,
        [
            {"timestamp": "t1", "symbol": "BTCUSDT", "quote_spent": 15.0, "quantity": 0.0002, "price": 75000.0, "dry_run": False},
            {"timestamp": "t2", "symbol": "BTCUSDT", "quote_spent": 15.0, "quantity": 1.0, "price": 15.0, "dry_run": True},
        ],
    )
    _write(grid_path, [])
    _write(trend_path, [])

    result = summarize_overview(dca_path, grid_path, trend_path)

    dca_unrealized = result["unrealisiert_geschätzt"]["dca"]
    assert dca_unrealized["quantity"] == pytest.approx(0.0002)
    assert dca_unrealized["avg_price"] == pytest.approx(75000.0)
    # Kein berechneter unrealisierter Gewinn/Verlust im Ergebnis.
    assert "unrealized_pnl" not in dca_unrealized
    assert set(dca_unrealized.keys()) == {"quantity", "avg_price"}


def test_overview_ignores_open_positions_for_realized_pnl(tmp_path):
    dca_path = tmp_path / "trade_ledger.json"
    grid_path = tmp_path / "grid_positions.json"
    trend_path = tmp_path / "trend_ledger.json"

    _write(dca_path, [])
    _write(
        grid_path,
        [
            {
                "id": "open1",
                "level_index": 0,
                "buy_price": 100.0,
                "target_sell_price": 110.0,
                "quantity": 1.0,
                "quote_spent": 100.0,
                "bought_at": "2026-01-01T00:00:00+00:00",
                "dry_run": False,
                "status": "open",
                "sell_price": None,
                "sold_at": None,
                "realized_pnl": None,
            }
        ],
    )
    _write(trend_path, [])

    result = summarize_overview(dca_path, grid_path, trend_path)

    assert result["gesamtgewinn"] == pytest.approx(0.0)
    assert result["gesamtverlust"] == pytest.approx(0.0)
    # Die offene, echte Position zählt stattdessen zum unrealisierten Bestand.
    assert result["unrealisiert_geschätzt"]["grid"] == {"quantity": 1.0, "avg_price": 100.0}
