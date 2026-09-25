"""PnL-Verlauf: realisierte Gewinne/Verluste je Tag plus Kumulation.

Stichtag ist der Verkauf, nicht der Kauf - und es zählen ausschließlich
echte, geschlossene Positionen.
"""

import json

import pytest

from app.ledger_readers import summarize_pnl_history


def _write(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


def _grid_closed(sold_day, pnl, dry_run=False, bought_day="2026-02-01"):
    return {
        "id": f"g-{sold_day}-{pnl}",
        "level_index": 0,
        "buy_price": 100.0,
        "quantity": 1.0,
        "quote_spent": 100.0,
        "bought_at": f"{bought_day}T10:00:00+00:00",
        "dry_run": dry_run,
        "status": "closed",
        "sell_price": 100.0 + pnl,
        "sold_at": f"{sold_day}T15:00:00+00:00",
        "realized_pnl": pnl,
    }


def _trend_closed(exit_day, pnl, dry_run=False):
    return {
        "id": f"t-{exit_day}-{pnl}",
        "entry_price": 100.0,
        "entry_time": "2026-02-01T10:00:00+00:00",
        "quantity": 1.0,
        "quote_spent": 100.0,
        "dry_run": dry_run,
        "status": "closed",
        "exit_price": 100.0 + pnl,
        "exit_time": f"{exit_day}T16:00:00+00:00",
        "exit_reason": "target",
        "realized_pnl": pnl,
    }


def _history(tmp_path, *, grid=(), trend=()):
    grid_path = tmp_path / "grid_positions.json"
    trend_path = tmp_path / "trend_ledger.json"
    _write(grid_path, list(grid))
    _write(trend_path, list(trend))
    return summarize_pnl_history(grid_path, trend_path)


# --- Randfälle -------------------------------------------------------------


def test_empty_ledgers_yield_empty_history(tmp_path):
    assert _history(tmp_path) == []


def test_missing_files_yield_empty_history(tmp_path):
    assert summarize_pnl_history(tmp_path / "fehlt_a.json", tmp_path / "fehlt_b.json") == []


def test_only_dry_run_closes_yield_empty_history(tmp_path):
    result = _history(
        tmp_path,
        grid=[_grid_closed("2026-03-01", 5.0, dry_run=True)],
        trend=[_trend_closed("2026-03-02", 9.0, dry_run=True)],
    )

    assert result == []


def test_open_positions_are_not_part_of_the_history(tmp_path):
    result = _history(
        tmp_path,
        grid=[{**_grid_closed("2026-03-01", 5.0), "status": "open", "realized_pnl": None}],
    )

    assert result == []


def test_close_without_realized_pnl_is_skipped(tmp_path):
    result = _history(tmp_path, grid=[{**_grid_closed("2026-03-01", 5.0), "realized_pnl": None}])

    assert result == []


def test_unparseable_sell_timestamp_is_skipped(tmp_path):
    result = _history(tmp_path, grid=[{**_grid_closed("2026-03-01", 5.0), "sold_at": 1741000000}])

    assert result == []


# --- Kernlogik -------------------------------------------------------------


def test_single_close_produces_one_entry(tmp_path):
    result = _history(tmp_path, grid=[_grid_closed("2026-03-01", 5.0)])

    assert result == [
        {
            "datum": "2026-03-01",
            "realisierte_pnl_an_diesem_tag": pytest.approx(5.0),
            "kumulierte_pnl_bis_zu_diesem_tag": pytest.approx(5.0),
        }
    ]


def test_several_closes_on_the_same_day_are_aggregated(tmp_path):
    result = _history(
        tmp_path,
        grid=[_grid_closed("2026-03-01", 5.0), _grid_closed("2026-03-01", -2.0)],
        trend=[_trend_closed("2026-03-01", 1.5)],
    )

    assert len(result) == 1
    assert result[0]["realisierte_pnl_an_diesem_tag"] == pytest.approx(4.5)


def test_cumulative_sum_runs_across_days_and_stays_sorted(tmp_path):
    result = _history(
        tmp_path,
        grid=[_grid_closed("2026-03-05", 10.0), _grid_closed("2026-03-01", 4.0)],
        trend=[_trend_closed("2026-03-03", -6.0)],
    )

    assert [entry["datum"] for entry in result] == ["2026-03-01", "2026-03-03", "2026-03-05"]
    assert [entry["realisierte_pnl_an_diesem_tag"] for entry in result] == [
        pytest.approx(4.0),
        pytest.approx(-6.0),
        pytest.approx(10.0),
    ]
    assert [entry["kumulierte_pnl_bis_zu_diesem_tag"] for entry in result] == [
        pytest.approx(4.0),
        pytest.approx(-2.0),
        pytest.approx(8.0),
    ]


def test_days_without_closes_get_no_entry(tmp_path):
    """Lücken werden nicht aufgefüllt - das übernimmt das Frontend."""
    result = _history(
        tmp_path, grid=[_grid_closed("2026-03-01", 1.0), _grid_closed("2026-03-10", 1.0)]
    )

    assert [entry["datum"] for entry in result] == ["2026-03-01", "2026-03-10"]


def test_mixed_real_and_dry_run_counts_only_real(tmp_path):
    result = _history(
        tmp_path,
        grid=[
            _grid_closed("2026-03-01", 5.0),
            _grid_closed("2026-03-01", 1000.0, dry_run=True),
        ],
    )

    assert len(result) == 1
    assert result[0]["kumulierte_pnl_bis_zu_diesem_tag"] == pytest.approx(5.0)


def test_sell_timestamp_decides_the_day_not_the_buy(tmp_path):
    result = _history(
        tmp_path, grid=[_grid_closed("2026-03-08", 3.0, bought_day="2026-01-02")]
    )

    assert result[0]["datum"] == "2026-03-08"


def test_sell_timestamp_is_normalised_to_utc(tmp_path):
    """01:30 in UTC+2 gehört zum Vortag in UTC."""
    result = _history(
        tmp_path, grid=[{**_grid_closed("2026-03-08", 3.0), "sold_at": "2026-03-08T01:30:00+02:00"}]
    )

    assert result[0]["datum"] == "2026-03-07"
