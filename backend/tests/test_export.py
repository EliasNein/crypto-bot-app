import csv
import io
import json
from datetime import datetime, timezone

import pytest

from app.export import build_trades_csv


def _write(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


def _parse_data_rows(csv_text: str) -> list[dict]:
    """Nur die echten CSV-Datenzeilen (ohne den '#'-Kommentarblock am Ende)."""
    lines = [line for line in csv_text.splitlines() if not line.startswith("#")]
    reader = csv.DictReader(io.StringIO("\n".join(lines)))
    return list(reader)


def _empty_ledgers(tmp_path):
    dca_path = tmp_path / "trade_ledger.json"
    grid_path = tmp_path / "grid_positions.json"
    trend_path = tmp_path / "trend_ledger.json"
    _write(dca_path, [])
    _write(grid_path, [])
    _write(trend_path, [])
    return dca_path, grid_path, trend_path


def test_export_excludes_dry_run_and_includes_real_dca_buy(tmp_path):
    dca_path, grid_path, trend_path = _empty_ledgers(tmp_path)
    _write(
        dca_path,
        [
            {"timestamp": "2026-01-01T00:00:00+00:00", "symbol": "BTCUSDT", "quote_spent": 15.0, "quantity": 0.0002, "price": 75000.0, "dry_run": False},
            {"timestamp": "2026-01-02T00:00:00+00:00", "symbol": "BTCUSDT", "quote_spent": 15.0, "quantity": 0.0002, "price": 75000.0, "dry_run": True},
        ],
    )

    csv_text = build_trades_csv(dca_path, grid_path, trend_path)
    rows = _parse_data_rows(csv_text)

    assert len(rows) == 1
    row = rows[0]
    assert row["bot"] == "dca"
    assert row["symbol"] == "BTCUSDT"
    assert row["waehrung"] == "USDT"
    assert row["seite"] == "BUY"
    assert row["betrag"] == "15.0"
    assert row["realisierter_pnl"] == ""
    assert row["position_id"] == ""


def test_export_grid_closed_position_produces_buy_and_sell_row(tmp_path):
    dca_path, grid_path, trend_path = _empty_ledgers(tmp_path)
    _write(
        grid_path,
        [
            {
                "id": "closed-1",
                "level_index": 0,
                "buy_price": 100.0,
                "target_sell_price": 105.0,
                "quantity": 1.0,
                "quote_spent": 100.0,
                "bought_at": "2026-01-01T00:00:00+00:00",
                "dry_run": False,
                "status": "closed",
                "sell_price": 105.0,
                "sold_at": "2026-01-02T00:00:00+00:00",
                "realized_pnl": 5.0,
            }
        ],
    )

    csv_text = build_trades_csv(dca_path, grid_path, trend_path)
    rows = _parse_data_rows(csv_text)

    assert len(rows) == 2
    buy, sell = rows
    assert buy["seite"] == "BUY"
    assert buy["preis"] == "100.0"
    assert buy["realisierter_pnl"] == ""
    assert buy["position_id"] == "closed-1"

    assert sell["seite"] == "SELL"
    assert sell["preis"] == "105.0"
    assert sell["realisierter_pnl"] == "5.0"
    assert sell["betrag"] == "105.0"  # quote_spent(100) + realized_pnl(5)
    assert sell["position_id"] == "closed-1"

    # Grid-Eintrag ohne symbol-Feld = Altbestand, beide Zeilen BTCUSDT.
    assert [(r["symbol"], r["waehrung"]) for r in rows] == [("BTCUSDT", "USDT")] * 2


def test_export_grid_open_position_produces_only_buy_row(tmp_path):
    dca_path, grid_path, trend_path = _empty_ledgers(tmp_path)
    _write(
        grid_path,
        [
            {
                "id": "open-1",
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

    csv_text = build_trades_csv(dca_path, grid_path, trend_path)
    rows = _parse_data_rows(csv_text)

    assert len(rows) == 1
    assert rows[0]["seite"] == "BUY"


def test_export_trend_closed_and_open_positions(tmp_path):
    dca_path, grid_path, trend_path = _empty_ledgers(tmp_path)
    _write(
        trend_path,
        [
            {
                "id": "t-closed",
                "entry_price": 100.0,
                "entry_time": "2026-01-01T00:00:00+00:00",
                "quantity": 1.0,
                "quote_spent": 100.0,
                "dry_run": False,
                "status": "closed",
                "exit_price": 90.0,
                "exit_time": "2026-01-02T00:00:00+00:00",
                "exit_reason": "stop_loss",
                "realized_pnl": -10.0,
            },
            {
                "id": "t-open",
                "entry_price": 200.0,
                "entry_time": "2026-01-03T00:00:00+00:00",
                "quantity": 1.0,
                "quote_spent": 200.0,
                "dry_run": False,
                "status": "open",
                "exit_price": None,
                "exit_time": None,
                "exit_reason": None,
                "realized_pnl": None,
            },
        ],
    )

    csv_text = build_trades_csv(dca_path, grid_path, trend_path)
    rows = _parse_data_rows(csv_text)

    by_id = {}
    for row in rows:
        by_id.setdefault(row["position_id"], []).append(row)

    assert len(by_id["t-closed"]) == 2
    assert len(by_id["t-open"]) == 1
    sell = next(r for r in by_id["t-closed"] if r["seite"] == "SELL")
    assert sell["realisierter_pnl"] == "-10.0"
    assert sell["betrag"] == "90.0"  # quote_spent(100) + realized_pnl(-10)


def test_export_dry_run_grid_and_trend_produce_no_rows(tmp_path):
    dca_path, grid_path, trend_path = _empty_ledgers(tmp_path)
    _write(
        grid_path,
        [
            {
                "id": "dry-1",
                "level_index": 0,
                "buy_price": 100.0,
                "target_sell_price": 105.0,
                "quantity": 1.0,
                "quote_spent": 100.0,
                "bought_at": "2026-01-01T00:00:00+00:00",
                "dry_run": True,
                "status": "closed",
                "sell_price": 105.0,
                "sold_at": "2026-01-02T00:00:00+00:00",
                "realized_pnl": 5.0,
            }
        ],
    )

    csv_text = build_trades_csv(dca_path, grid_path, trend_path)
    rows = _parse_data_rows(csv_text)

    assert rows == []


def test_export_only_dry_run_data_yields_header_and_comment_block_only(tmp_path):
    dca_path, grid_path, trend_path = _empty_ledgers(tmp_path)
    _write(
        dca_path,
        [{"timestamp": "t", "symbol": "BTCUSDT", "quote_spent": 15.0, "quantity": 0.0002, "price": 75000.0, "dry_run": True}],
    )

    csv_text = build_trades_csv(dca_path, grid_path, trend_path)
    rows = _parse_data_rows(csv_text)
    lines = csv_text.splitlines()

    assert rows == []
    assert lines[0].startswith("datum_zeit_utc")
    assert lines[1] == ""  # keine Datenzeile - direkt zum Kommentarblock... siehe unten

    # Kein Datensatz zwischen Header und Kommentarblock.
    non_comment_lines = [line for line in lines if not line.startswith("#") and line.strip()]
    assert non_comment_lines == [lines[0]]


def _comments(csv_text: str) -> str:
    return "\n".join(line for line in csv_text.splitlines() if line.startswith("#"))


def test_export_comment_block_present_with_required_hints(tmp_path):
    dca_path, grid_path, trend_path = _empty_ledgers(tmp_path)

    joined = _comments(build_trades_csv(dca_path, grid_path, trend_path))

    assert len(joined.splitlines()) == 4
    # Ohne Zeilen gibt es auch keine Währung, über die etwas zu sagen wäre.
    assert "Keine Trades im gewählten Zeitraum" in joined
    assert "NICHT in Euro" not in joined
    assert "Export erstellt am:" in joined
    assert "keine Steuerberatung" in joined


def test_export_usdt_rows_carry_the_conversion_warning(tmp_path):
    dca_path, grid_path, trend_path = _empty_ledgers(tmp_path)
    _write(dca_path, [_dca_buy("2026-06-01T00:00:00+00:00")])

    joined = _comments(build_trades_csv(dca_path, grid_path, trend_path, now=NOW))

    assert "# USDT (US-Dollar-Stablecoin): NICHT in Euro" in joined
    assert "KEINE Währungsumrechnung" in joined
    assert "EUR" not in joined.replace("Euro", "")


def test_export_rows_sorted_chronologically(tmp_path):
    dca_path, grid_path, trend_path = _empty_ledgers(tmp_path)
    _write(
        dca_path,
        [
            {"timestamp": "2026-03-01T00:00:00+00:00", "symbol": "BTCUSDT", "quote_spent": 10.0, "quantity": 0.0001, "price": 10.0, "dry_run": False},
            {"timestamp": "2026-01-01T00:00:00+00:00", "symbol": "BTCUSDT", "quote_spent": 10.0, "quantity": 0.0001, "price": 10.0, "dry_run": False},
        ],
    )

    csv_text = build_trades_csv(dca_path, grid_path, trend_path)
    rows = _parse_data_rows(csv_text)

    timestamps = [r["datum_zeit_utc"] for r in rows]
    assert timestamps == sorted(timestamps)


# --- Zeitraum-Filterung (period) -------------------------------------------

NOW = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


def _dca_buy(timestamp, quantity=0.0001, price=10.0, quote_spent=1.0):
    return {
        "timestamp": timestamp,
        "symbol": "BTCUSDT",
        "quote_spent": quote_spent,
        "quantity": quantity,
        "price": price,
        "dry_run": False,
    }


def test_period_all_is_default_and_unfiltered(tmp_path):
    dca_path, grid_path, trend_path = _empty_ledgers(tmp_path)
    _write(dca_path, [_dca_buy("2020-01-01T00:00:00+00:00")])

    csv_text = build_trades_csv(dca_path, grid_path, trend_path, now=NOW)  # period default = "all"
    rows = _parse_data_rows(csv_text)

    assert len(rows) == 1


def test_period_week_excludes_older_trades(tmp_path):
    dca_path, grid_path, trend_path = _empty_ledgers(tmp_path)
    _write(
        dca_path,
        [
            _dca_buy("2026-06-14T08:00:00+00:00"),  # innerhalb der letzten 7 Tage
            _dca_buy("2026-05-01T00:00:00+00:00"),  # zu alt
        ],
    )

    csv_text = build_trades_csv(dca_path, grid_path, trend_path, period="week", now=NOW)
    rows = _parse_data_rows(csv_text)

    assert len(rows) == 1
    assert rows[0]["datum_zeit_utc"] == "2026-06-14T08:00:00+00:00"


def test_period_month_excludes_previous_month(tmp_path):
    dca_path, grid_path, trend_path = _empty_ledgers(tmp_path)
    _write(
        dca_path,
        [
            _dca_buy("2026-06-01T00:00:00+00:00"),  # aktueller Monat
            _dca_buy("2026-05-31T23:59:59+00:00"),  # Vormonat
        ],
    )

    csv_text = build_trades_csv(dca_path, grid_path, trend_path, period="month", now=NOW)
    rows = _parse_data_rows(csv_text)

    assert len(rows) == 1
    assert rows[0]["datum_zeit_utc"] == "2026-06-01T00:00:00+00:00"


def test_period_year_excludes_previous_year(tmp_path):
    dca_path, grid_path, trend_path = _empty_ledgers(tmp_path)
    _write(
        dca_path,
        [
            _dca_buy("2026-01-01T00:00:00+00:00"),  # aktuelles Jahr
            _dca_buy("2025-12-31T23:59:59+00:00"),  # Vorjahr
        ],
    )

    csv_text = build_trades_csv(dca_path, grid_path, trend_path, period="year", now=NOW)
    rows = _parse_data_rows(csv_text)

    assert len(rows) == 1
    assert rows[0]["datum_zeit_utc"] == "2026-01-01T00:00:00+00:00"


def test_period_year_boundary_shows_only_sell_row_for_position_opened_last_year(tmp_path):
    """Grenzfall aus der Anforderung: im Dezember gekauft, im Januar
    verkauft - bei period=year (aktuelles Jahr) darf nur die
    Verkaufs-Zeile erscheinen, nicht die Kauf-Zeile aus dem Vorjahr.
    """
    dca_path, grid_path, trend_path = _empty_ledgers(tmp_path)
    _write(
        grid_path,
        [
            {
                "id": "cross-year",
                "level_index": 0,
                "buy_price": 100.0,
                "target_sell_price": 110.0,
                "quantity": 1.0,
                "quote_spent": 100.0,
                "bought_at": "2025-12-20T00:00:00+00:00",
                "dry_run": False,
                "status": "closed",
                "sell_price": 110.0,
                "sold_at": "2026-01-05T00:00:00+00:00",
                "realized_pnl": 10.0,
            }
        ],
    )

    csv_text = build_trades_csv(dca_path, grid_path, trend_path, period="year", now=NOW)
    rows = _parse_data_rows(csv_text)

    assert len(rows) == 1
    assert rows[0]["seite"] == "SELL"
    assert rows[0]["datum_zeit_utc"] == "2026-01-05T00:00:00+00:00"


def test_period_invalid_value_raises_value_error(tmp_path):
    dca_path, grid_path, trend_path = _empty_ledgers(tmp_path)

    with pytest.raises(ValueError):
        build_trades_csv(dca_path, grid_path, trend_path, period="decade", now=NOW)


def test_period_comment_line_names_year_and_range(tmp_path):
    dca_path, grid_path, trend_path = _empty_ledgers(tmp_path)

    csv_text = build_trades_csv(dca_path, grid_path, trend_path, period="year", now=NOW)
    comment_lines = [line for line in csv_text.splitlines() if line.startswith("#")]

    period_line = next(line for line in comment_lines if line.startswith("# Zeitraum:"))
    assert "Jahr 2026" in period_line
    assert "01.01.2026 00:00 UTC" in period_line
    assert "15.06.2026 23:59 UTC" in period_line
    assert "Verkaufs-Zeile" in period_line


def test_period_comment_line_for_all_states_no_filtering(tmp_path):
    dca_path, grid_path, trend_path = _empty_ledgers(tmp_path)

    csv_text = build_trades_csv(dca_path, grid_path, trend_path, now=NOW)
    comment_lines = [line for line in csv_text.splitlines() if line.startswith("#")]

    period_line = next(line for line in comment_lines if line.startswith("# Zeitraum:"))
    assert "keine Zeitraum-Filterung" in period_line


# --- Währung je Zeile (Paarwechsel BTCUSDT -> BTCEUR) -----------------------


def _grid_round_trip(pid, pnl, symbol=None, day="2026-06-01"):
    """symbol=None: Feld fehlt (Altbestand vor der Symbolbindung)."""
    record = {
        "id": pid, "level_index": 0, "buy_price": 100.0, "target_sell_price": 105.0,
        "quantity": 1.0, "quote_spent": 100.0, "bought_at": f"{day}T08:00:00+00:00",
        "dry_run": False, "status": "closed", "sell_price": 100.0 + pnl,
        "sold_at": f"{day}T12:00:00+00:00", "realized_pnl": pnl,
    }
    return record if symbol is None else {**record, "symbol": symbol}


def test_export_rows_carry_their_own_symbol_and_currency(tmp_path):
    """Früher stand in JEDER Grid-/Trend-Zeile fest BTCUSDT - eine
    EUR-Position gab sich im Steuer-Export als USDT aus."""
    dca_path, grid_path, trend_path = _empty_ledgers(tmp_path)
    _write(dca_path, [{**_dca_buy("2026-06-02T00:00:00+00:00"), "symbol": "BTCEUR"}])
    _write(grid_path, [_grid_round_trip("alt", 5.0), _grid_round_trip("neu", -3.0, symbol="BTCEUR")])
    _write(trend_path, [{
        "id": "t-null", "entry_price": 100.0, "entry_time": "2026-06-03T00:00:00+00:00",
        "quantity": 1.0, "quote_spent": 100.0, "dry_run": False, "status": "open", "symbol": None,
    }])

    rows = _parse_data_rows(build_trades_csv(dca_path, grid_path, trend_path, now=NOW))

    got = {(r["bot"], r["position_id"], r["seite"]): (r["symbol"], r["waehrung"]) for r in rows}
    assert got == {
        ("grid", "alt", "BUY"): ("BTCUSDT", "USDT"),
        ("grid", "alt", "SELL"): ("BTCUSDT", "USDT"),
        ("grid", "neu", "BUY"): ("BTCEUR", "EUR"),
        ("grid", "neu", "SELL"): ("BTCEUR", "EUR"),
        ("dca", "", "BUY"): ("BTCEUR", "EUR"),
        ("trend", "t-null", "BUY"): ("BTCUSDT", "USDT"),  # null = Altbestand, wie beim Bot
    }


def test_export_eur_only_says_no_conversion_is_needed(tmp_path):
    """Der alte Pauschalhinweis "Alle Beträge in USDT, NICHT in Euro" wäre
    bei einem EUR-Paar schlicht falsch."""
    dca_path, grid_path, trend_path = _empty_ledgers(tmp_path)
    _write(grid_path, [_grid_round_trip("neu", 2.0, symbol="BTCEUR")])

    joined = _comments(build_trades_csv(dca_path, grid_path, trend_path, now=NOW))

    assert "# EUR (Euro): Beträge bereits in Euro - keine Umrechnung nötig." in joined
    assert "NICHT in Euro" not in joined
    assert "USDT" not in joined
    assert "Umrechnung" not in joined.replace("keine Umrechnung nötig", "")


def test_export_mixed_names_every_currency_separately(tmp_path):
    dca_path, grid_path, trend_path = _empty_ledgers(tmp_path)
    _write(grid_path, [
        _grid_round_trip("alt", 5.0),
        _grid_round_trip("neu", -3.0, symbol="BTCEUR"),
        _grid_round_trip("usdc", 1.0, symbol="BTCUSDC"),
    ])

    comment_lines = _comments(build_trades_csv(dca_path, grid_path, trend_path, now=NOW)).splitlines()

    assert "# EUR (Euro): Beträge bereits in Euro - keine Umrechnung nötig." in comment_lines
    for stablecoin in ("USDC", "USDT"):
        line = next(line for line in comment_lines if line.startswith(f"# {stablecoin} "))
        assert "NICHT in Euro" in line and "KEINE Währungsumrechnung" in line


def test_export_hint_only_names_currencies_in_the_chosen_period(tmp_path):
    """Die USDT-Zeilen liegen vor dem Zeitraum - ihr Hinweis gehört nicht
    in einen Export, der nur EUR-Zeilen enthält."""
    dca_path, grid_path, trend_path = _empty_ledgers(tmp_path)
    _write(grid_path, [
        _grid_round_trip("alt", 5.0, day="2026-05-01"),
        _grid_round_trip("neu", -3.0, symbol="BTCEUR", day="2026-06-10"),
    ])

    joined = _comments(build_trades_csv(dca_path, grid_path, trend_path, period="month", now=NOW))

    assert "# EUR (Euro)" in joined
    assert "USDT" not in joined


def test_export_keeps_rows_without_determinable_currency_and_warns(tmp_path):
    """Sicherheitsnetz: ein echter Trade wird für die Steuer NICHT
    weggelassen, aber auch keiner Währung zugeraten."""
    dca_path, grid_path, trend_path = _empty_ledgers(tmp_path)
    _write(grid_path, [_grid_round_trip("gut", 1.0), _grid_round_trip("fremd", 50.0, symbol="ETHEUR")])

    csv_text = build_trades_csv(dca_path, grid_path, trend_path, now=NOW)
    rows = _parse_data_rows(csv_text)

    fremd = [r for r in rows if r["position_id"] == "fremd"]
    assert len(fremd) == 2
    assert {(r["symbol"], r["waehrung"]) for r in fremd} == {("ETHEUR", "")}
    joined = _comments(csv_text)
    assert "# ACHTUNG: 2 Zeilen ohne bestimmbare Währung (Spalte waehrung leer) - bitte manuell prüfen." in joined
    assert "# USDT (US-Dollar-Stablecoin): NICHT in Euro" in joined
