"""Kennzahl "Tage ohne Kauf".

Der heutige UTC-Tag bleibt bewusst außen vor (noch nicht abgeschlossen),
deshalb wird `now` in allen Tests fest vorgegeben statt gegen die echte
Uhr zu laufen.
"""

import json
from datetime import datetime, timezone

import pytest

from app.ledger_readers import summarize_investment_activity

# Fester "Jetzt"-Zeitpunkt: 2026-03-10, damit der letzte abgeschlossene
# Tag immer der 2026-03-09 ist.
NOW = datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc)


def _write(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


def _paths(tmp_path):
    dca = tmp_path / "trade_ledger.json"
    grid = tmp_path / "grid_positions.json"
    trend = tmp_path / "trend_ledger.json"
    for path in (dca, grid, trend):
        _write(path, [])
    return dca, grid, trend


def _dca_buy(day, dry_run=False, hour=9):
    return {
        "timestamp": f"{day}T{hour:02d}:00:00+00:00",
        "symbol": "BTCUSDT",
        "quote_spent": 15.0,
        "quantity": 0.0002,
        "price": 75000.0,
        "dry_run": dry_run,
    }


def _grid_buy(day, dry_run=False):
    return {
        "id": f"g-{day}",
        "level_index": 0,
        "buy_price": 100.0,
        "quantity": 1.0,
        "quote_spent": 100.0,
        "bought_at": f"{day}T10:00:00+00:00",
        "dry_run": dry_run,
        "status": "open",
    }


def _trend_buy(day, dry_run=False):
    return {
        "id": f"t-{day}",
        "entry_price": 100.0,
        "entry_time": f"{day}T11:00:00+00:00",
        "quantity": 1.0,
        "quote_spent": 100.0,
        "dry_run": dry_run,
        "status": "open",
    }


def _activity(tmp_path, *, dca=(), grid=(), trend=(), now=NOW):
    dca_path, grid_path, trend_path = _paths(tmp_path)
    _write(dca_path, list(dca))
    _write(grid_path, list(grid))
    _write(trend_path, list(trend))
    return summarize_investment_activity(dca_path, grid_path, trend_path, now=now)


# --- Randfall: gar keine Daten --------------------------------------------


def test_empty_ledgers_report_no_data_without_dividing_by_zero(tmp_path):
    result = _activity(tmp_path)

    assert result["status"] == "no_data"
    assert result["total_days_tracked"] == 0
    assert result["days_without_activity_pct"] is None
    assert result["days_with_dry_run_activity"] == 0
    assert result["today_has_activity"] is False


def test_missing_files_do_not_crash(tmp_path):
    result = summarize_investment_activity(
        tmp_path / "fehlt_a.json", tmp_path / "fehlt_b.json", tmp_path / "fehlt_c.json", now=NOW
    )

    assert result["status"] == "no_data"


# --- Randfall: nur Dry-Run-Daten (aktuelle Paper-Trade-Phase) --------------


def test_only_dry_run_data_yields_no_data_but_counts_dry_run_days(tmp_path):
    """Genau die heutige Lage auf dem Homeserver: kein einziger echter
    Kauf. Die Primärkennzahl bleibt leer, die Paper-Trade-Phase wird
    trotzdem sichtbar."""
    result = _activity(
        tmp_path,
        dca=[_dca_buy("2026-03-01", dry_run=True), _dca_buy("2026-03-02", dry_run=True)],
        grid=[_grid_buy("2026-03-02", dry_run=True)],
    )

    assert result["status"] == "no_data"
    assert result["days_with_activity"] == 0
    # 01.03. und 02.03. - der zweite Grid-Kauf am 02.03. zählt nicht doppelt.
    assert result["days_with_dry_run_activity"] == 2


# --- Kernlogik -------------------------------------------------------------


def test_counts_gap_days_between_first_and_last_buy(tmp_path):
    """01.03. und 05.03. gekauft, dazwischen nichts: 5 Tage Fenster
    (01.-05.), davon 2 mit Aktivität."""
    result = _activity(tmp_path, dca=[_dca_buy("2026-03-01"), _dca_buy("2026-03-05")])

    assert result["status"] == "ok"
    assert result["total_days_tracked"] == 9  # 01.03. bis 09.03. (gestern)
    assert result["days_with_activity"] == 2
    assert result["days_without_activity"] == 7
    assert result["days_without_activity_pct"] == pytest.approx(77.8)


def test_activity_from_any_of_the_three_bots_counts(tmp_path):
    """Ein Kauf in irgendeinem Bot macht den Tag zu einem Aktivitätstag."""
    result = _activity(
        tmp_path,
        dca=[_dca_buy("2026-03-07")],
        grid=[_grid_buy("2026-03-08")],
        trend=[_trend_buy("2026-03-09")],
    )

    assert result["total_days_tracked"] == 3  # 07.-09.03.
    assert result["days_with_activity"] == 3
    assert result["days_without_activity"] == 0
    assert result["days_without_activity_pct"] == pytest.approx(0.0)


def test_several_buys_on_the_same_day_count_once(tmp_path):
    result = _activity(
        tmp_path,
        dca=[_dca_buy("2026-03-09", hour=8), _dca_buy("2026-03-09", hour=14)],
        grid=[_grid_buy("2026-03-09")],
    )

    assert result["total_days_tracked"] == 1
    assert result["days_with_activity"] == 1


def test_dry_run_buys_do_not_count_as_real_activity(tmp_path):
    """Gemischte Daten: nur der echte Kauf macht den Tag aktiv."""
    result = _activity(
        tmp_path,
        dca=[_dca_buy("2026-03-05"), _dca_buy("2026-03-06", dry_run=True)],
    )

    assert result["total_days_tracked"] == 5  # 05.-09.03.
    assert result["days_with_activity"] == 1  # nur der 05.03.
    assert result["days_with_dry_run_activity"] == 1  # der 06.03. separat


def test_entries_without_dry_run_flag_are_ignored_in_both_counts(tmp_path):
    """Ein Eintrag ohne dry_run-Feld wird weder als echt noch als
    simuliert gezählt - nicht raten."""
    result = _activity(
        tmp_path,
        dca=[{"timestamp": "2026-03-05T09:00:00+00:00", "symbol": "BTCUSDT", "quantity": 1.0}],
    )

    assert result["status"] == "no_data"
    assert result["days_with_dry_run_activity"] == 0


# --- Randfall: der heutige, unvollständige Tag ----------------------------


def test_today_is_excluded_from_the_window(tmp_path):
    """Kauf am 09.03. (gestern) und am 10.03. (heute): heute zählt weder
    als Fenstertag noch als Aktivitätstag."""
    result = _activity(tmp_path, dca=[_dca_buy("2026-03-09"), _dca_buy("2026-03-10")])

    assert result["total_days_tracked"] == 1  # nur der 09.03.
    assert result["days_with_activity"] == 1
    assert result["today_has_activity"] is True


def test_buy_only_today_yields_no_data_not_a_zero_percent_day(tmp_path):
    """Frisches System, erster Kauf heute: es gibt noch keinen
    abgeschlossenen Tag, also auch keine Quote."""
    result = _activity(tmp_path, dca=[_dca_buy("2026-03-10")])

    assert result["status"] == "no_data"
    assert result["total_days_tracked"] == 0
    assert result["days_without_activity_pct"] is None
    assert result["today_has_activity"] is True


def test_no_buy_today_sets_today_has_activity_false(tmp_path):
    result = _activity(tmp_path, dca=[_dca_buy("2026-03-08")])

    assert result["today_has_activity"] is False


def test_metric_is_stable_over_the_course_of_the_day(tmp_path):
    """Derselbe Datenstand, morgens und abends abgefragt, muss dieselbe
    Quote liefern - das ist der Grund, heute auszuschließen."""
    dca = [_dca_buy("2026-03-05"), _dca_buy("2026-03-08")]

    morgens = _activity(tmp_path, dca=dca, now=datetime(2026, 3, 10, 0, 5, tzinfo=timezone.utc))
    abends = _activity(tmp_path, dca=dca, now=datetime(2026, 3, 10, 23, 55, tzinfo=timezone.utc))

    assert morgens["days_without_activity_pct"] == abends["days_without_activity_pct"]
    assert morgens["total_days_tracked"] == abends["total_days_tracked"]


def test_timestamp_in_other_timezone_is_normalised_to_utc(tmp_path):
    """23:30 in UTC+2 ist der 08.03. um 21:30 UTC - der Tag muss nach
    UTC eingeordnet werden, nicht nach Lokalzeit."""
    result = _activity(
        tmp_path,
        dca=[{**_dca_buy("2026-03-08"), "timestamp": "2026-03-08T23:30:00+02:00"}],
    )

    assert result["days_with_activity"] == 1
    assert result["total_days_tracked"] == 2  # 08.03. (UTC) bis 09.03.


def test_unparseable_timestamp_is_skipped(tmp_path):
    result = _activity(
        tmp_path,
        dca=[{**_dca_buy("2026-03-05"), "timestamp": 1741000000}, _dca_buy("2026-03-08")],
    )

    assert result["status"] == "ok"
    assert result["days_with_activity"] == 1  # nur der 08.03.
