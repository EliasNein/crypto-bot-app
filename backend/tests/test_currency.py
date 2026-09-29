"""Währung je Ledger-Eintrag und Summen je Währung.

Befund aus dem Audit vom 28.09.2026: Bei gemischten Ledgern (BTCUSDT vor,
BTCEUR nach dem Paarwechsel) addierte das Backend USDT- und EUR-Beträge
stumm zu einer Zahl - plausibel aussehend, weil beide Währungen nahe
beieinander liegen. Grid und Trend trugen bis zur Symbolbindung im Bot
(29.09.2026) gar kein symbol-Feld.

Die Fixtures bilden genau das ab: Altbestand OHNE symbol-Feld (gilt als
BTCUSDT, wie beim Bot), neue Einträge MIT symbol.
"""

import json

import pytest

from app.currency import LEGACY_SYMBOL, resolve
from app.ledger_readers import (
    summarize_dca,
    summarize_grid,
    summarize_overview,
    summarize_pnl_history,
    summarize_trend,
)


def _write(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


def _with_symbol(record, symbol):
    """symbol=None heißt hier: Feld fehlt (Altbestand vor der Symbolbindung)."""
    return record if symbol is None else {**record, "symbol": symbol}


def _dca(day, price, quote_spent, symbol, dry_run=False):
    return {"timestamp": f"{day}T09:00:00+00:00", "symbol": symbol, "quote_spent": quote_spent,
            "quantity": 0.0002, "price": price, "dry_run": dry_run}


def _grid(pid, *, bought, sold=None, spent, pnl=None, symbol=None, dry_run=False):
    record = {"id": pid, "level_index": 0, "buy_price": spent * 1000, "target_sell_price": spent * 1010,
              "quantity": 0.001, "quote_spent": spent, "bought_at": f"{bought}T10:00:00+00:00",
              "dry_run": dry_run, "status": "open" if sold is None else "closed",
              "sell_price": None, "sold_at": None if sold is None else sold, "realized_pnl": pnl}
    return _with_symbol(record, symbol)


def _trend(tid, *, entry, exit_at=None, spent, pnl=None, symbol=None):
    record = {"id": tid, "entry_price": spent * 1000, "entry_time": f"{entry}T10:00:00+00:00",
              "quantity": 0.001, "quote_spent": spent, "dry_run": False,
              "status": "open" if exit_at is None else "closed", "exit_price": None,
              "exit_time": exit_at, "exit_reason": None if exit_at is None else "signal",
              "realized_pnl": pnl}
    return _with_symbol(record, symbol)


def _paths(tmp_path, *, dca=(), grid=(), trend=()):
    paths = (tmp_path / "trade_ledger.json", tmp_path / "grid_positions.json", tmp_path / "trend_ledger.json")
    for path, data in zip(paths, (dca, grid, trend)):
        _write(path, list(data))
    return paths


# --- Die Zuordnungsregel ------------------------------------------------------


def test_legacy_symbol_is_the_bot_convention():
    """Muss mit crypto-bot dca_bot/symbol_guard.LEGACY_SYMBOL übereinstimmen."""
    assert LEGACY_SYMBOL == "BTCUSDT"


@pytest.mark.parametrize(
    "record",
    [pytest.param({}, id="feld-fehlt"), pytest.param({"symbol": None}, id="feld-null")],
)
def test_missing_or_null_symbol_is_legacy_btcusdt(record):
    """Genau die Bot-Regel (symbol_guard.effective_symbol): fehlt ODER null
    = Altbestand. Eine eigene Regel wäre Raten - und beide Repos läsen
    denselben Eintrag verschieden."""
    assert resolve(record) == ("BTCUSDT", "USDT")


@pytest.mark.parametrize(
    "symbol, expected",
    [
        ("BTCUSDT", ("BTCUSDT", "USDT")),
        ("BTCUSDC", ("BTCUSDC", "USDC")),
        ("BTCEUR", ("BTCEUR", "EUR")),
        (" BTCEUR ", ("BTCEUR", "EUR")),  # Leerraum am Rand ignoriert der Bot ebenfalls
    ],
)
def test_known_pairs_resolve_to_their_quote(symbol, expected):
    assert resolve({"symbol": symbol}) == expected


@pytest.mark.parametrize(
    "symbol",
    ["", "   ", 42, ["BTCEUR"], "ETHEUR", "BTCXYZ", "BTC", "btceur"],
)
def test_anything_else_is_undeterminable(symbol):
    """Kein Raten: leerer Text, falscher Typ, fremde Basis (ETH wäre keine
    BTC-Menge), unbekannte Quote."""
    assert resolve({"symbol": symbol})[1] is None


# --- Gemischter Ledger: das Szenario aus dem Audit -----------------------------
#
# Vor dem Wechsel: BTCUSDT (Grid/Trend ohne Feld = Altbestand).
# Nach dem Wechsel: BTCEUR (mit Feld).


def _mixed(tmp_path):
    return _paths(
        tmp_path,
        dca=[
            _dca("2026-09-01", 75000.0, 15.0, "BTCUSDT"),
            _dca("2026-10-01", 65000.0, 13.0, "BTCEUR"),
        ],
        grid=[
            _grid("g-usdt", bought="2026-09-02", sold="2026-10-02T15:00:00+00:00", spent=75.0, pnl=5.0),
            _grid("g-eur", bought="2026-10-01", sold="2026-10-02T16:00:00+00:00", spent=65.0, pnl=-3.0,
                  symbol="BTCEUR"),
            _grid("g-offen-usdt", bought="2026-09-20", spent=75.0),
            _grid("g-offen-eur", bought="2026-10-02", spent=65.0, symbol="BTCEUR"),
        ],
        trend=[
            _trend("t-eur", entry="2026-10-01", exit_at="2026-10-03T09:00:00+00:00", spent=65.0, pnl=1.2,
                   symbol="BTCEUR"),
        ],
    )


def test_mixed_overview_keeps_gain_and_loss_apart_per_currency(tmp_path):
    """Früher: gesamtgewinn 6,2 und gesamtverlust −3 - als "USDT" angezeigt."""
    overview = summarize_overview(*_mixed(tmp_path))

    assert overview["gesamtgewinn"] == {"USDT": pytest.approx(5.0), "EUR": pytest.approx(1.2)}
    assert overview["gesamtverlust"] == {"USDT": pytest.approx(0.0), "EUR": pytest.approx(-3.0)}


def test_mixed_card_realized_pnl_is_per_currency(tmp_path):
    """Früher: Grid-Karte "Realisiert 2,00 USDT" (= +5 USDT − 3 EUR)."""
    _, grid_path, trend_path = _mixed(tmp_path)

    assert summarize_grid(grid_path)["metrics"]["realized_pnl"] == {
        "USDT": pytest.approx(5.0),
        "EUR": pytest.approx(-3.0),
    }
    assert summarize_trend(trend_path)["metrics"]["realized_pnl"] == {"EUR": pytest.approx(1.2)}


def test_mixed_pnl_history_has_one_series_per_currency(tmp_path):
    """Früher: EIN Tagespunkt 2,0 am 02.10., weil beide Abschlüsse am
    selben Tag in dieselbe Tagessumme liefen."""
    _, grid_path, trend_path = _mixed(tmp_path)

    verlauf = summarize_pnl_history(grid_path, trend_path)

    assert verlauf == {
        "USDT": [
            {"datum": "2026-10-02", "realisierte_pnl_an_diesem_tag": pytest.approx(5.0),
             "kumulierte_pnl_bis_zu_diesem_tag": pytest.approx(5.0)},
        ],
        "EUR": [
            {"datum": "2026-10-02", "realisierte_pnl_an_diesem_tag": pytest.approx(-3.0),
             "kumulierte_pnl_bis_zu_diesem_tag": pytest.approx(-3.0)},
            {"datum": "2026-10-03", "realisierte_pnl_an_diesem_tag": pytest.approx(1.2),
             "kumulierte_pnl_bis_zu_diesem_tag": pytest.approx(-1.8)},
        ],
    }


def test_mixed_cost_basis_is_per_currency(tmp_path):
    """Früher: "Eingesetzt 28,00 USDT" und Ø 70.000 - ein Kurs, den es in
    keiner der beiden Währungen gab."""
    dca_path, grid_path, trend_path = _mixed(tmp_path)

    metrics = summarize_dca(dca_path)["metrics"]
    assert metrics["total_spent"] == {"USDT": pytest.approx(15.0), "EUR": pytest.approx(13.0)}
    assert metrics["avg_entry_price"] == {"USDT": pytest.approx(75000.0), "EUR": pytest.approx(65000.0)}
    # BTC ist BTC - die Menge darf über beide Paare summiert werden.
    assert metrics["total_quantity"] == pytest.approx(0.0004)

    unrealized = summarize_overview(dca_path, grid_path, trend_path)["unrealisiert_geschätzt"]
    assert unrealized["dca"] == {
        "USDT": {"quantity": pytest.approx(0.0002), "avg_price": pytest.approx(75000.0)},
        "EUR": {"quantity": pytest.approx(0.0002), "avg_price": pytest.approx(65000.0)},
    }
    assert unrealized["grid"] == {
        "USDT": {"quantity": pytest.approx(0.001), "avg_price": pytest.approx(75000.0)},
        "EUR": {"quantity": pytest.approx(0.001), "avg_price": pytest.approx(65000.0)},
    }
    assert unrealized["trend"] == {}


def test_mixed_currencies_are_ordered_by_most_recent_activity(tmp_path):
    """Die jüngste Aktivität (hier der Trend-Ausstieg am 03.10. in EUR)
    macht EUR zur Hauptwährung, die das Frontend groß zeigt."""
    overview = summarize_overview(*_mixed(tmp_path))

    assert overview["waehrungen"] == ["EUR", "USDT"]
    assert overview["ohne_waehrung"] == {"dca": 0, "grid": 0, "trend": 0}


def test_order_follows_activity_not_the_alphabet(tmp_path):
    """Gegenprobe: liegt USDT zeitlich vorn, steht USDT vorn."""
    paths = _paths(
        tmp_path,
        dca=[_dca("2026-09-01", 65000.0, 13.0, "BTCEUR"), _dca("2026-09-05", 75000.0, 15.0, "BTCUSDT")],
    )

    assert summarize_overview(*paths)["waehrungen"] == ["USDT", "EUR"]


def test_open_positions_carry_symbol_and_currency(tmp_path):
    dca_path, grid_path, _ = _mixed(tmp_path)

    offen = {p["id"]: (p["symbol"], p["waehrung"]) for p in summarize_grid(grid_path)["open_positions"]}
    assert offen == {"g-offen-usdt": ("BTCUSDT", "USDT"), "g-offen-eur": ("BTCEUR", "EUR")}
    assert [p["waehrung"] for p in summarize_dca(dca_path)["open_positions"]] == ["USDT", "EUR"]


# --- Altbestand und neuer Eintrag desselben Paars ------------------------------


def test_legacy_and_explicit_btcusdt_land_in_the_same_bucket(tmp_path):
    """Ohne Feld, mit null und mit "BTCUSDT" ist dasselbe Paar - nach dem
    Symbolbindungs-Deploy stehen alle drei Formen im selben Ledger."""
    grid = [
        _grid("alt", bought="2026-09-01", sold="2026-09-02T10:00:00+00:00", spent=15.0, pnl=1.0),
        {**_grid("null", bought="2026-09-03", sold="2026-09-04T10:00:00+00:00", spent=15.0, pnl=2.0),
         "symbol": None},
        _grid("neu", bought="2026-09-29", sold="2026-09-30T10:00:00+00:00", spent=15.0, pnl=4.0,
              symbol="BTCUSDT"),
    ]
    paths = _paths(tmp_path, grid=grid)

    overview = summarize_overview(*paths)
    assert overview["gesamtgewinn"] == {"USDT": pytest.approx(7.0)}
    assert overview["waehrungen"] == ["USDT"]
    assert overview["ohne_waehrung"]["grid"] == 0


# --- Reiner BTCEUR-Ledger ------------------------------------------------------


def test_pure_eur_ledger_has_no_usdt_anywhere(tmp_path):
    paths = _paths(
        tmp_path,
        dca=[_dca("2026-10-01", 65000.0, 13.0, "BTCEUR")],
        grid=[_grid("g", bought="2026-10-01", sold="2026-10-02T10:00:00+00:00", spent=65.0, pnl=0.8,
                    symbol="BTCEUR")],
        trend=[_trend("t", entry="2026-10-02", spent=65.0, symbol="BTCEUR")],
    )

    overview = summarize_overview(*paths)
    assert overview["gesamtgewinn"] == {"EUR": pytest.approx(0.8)}
    assert overview["gesamtverlust"] == {"EUR": pytest.approx(0.0)}
    assert overview["waehrungen"] == ["EUR"]
    assert set(overview["unrealisiert_geschätzt"]["trend"]) == {"EUR"}
    assert set(summarize_pnl_history(paths[1], paths[2])) == {"EUR"}
    assert set(summarize_dca(paths[0])["metrics"]["total_spent"]) == {"EUR"}
    assert "USDT" not in json.dumps(overview)


# --- Sicherheitsnetz: Währung nicht bestimmbar ---------------------------------


def _with_unknown(tmp_path):
    return _paths(
        tmp_path,
        dca=[
            _dca("2026-09-01", 75000.0, 15.0, "BTCUSDT"),
            _dca("2026-09-02", 3000.0, 999.0, ""),  # kaputtes Feld
            _dca("2026-09-03", 3000.0, 777.0, "ETHEUR", dry_run=True),  # Dry-Run: zählt nie
        ],
        grid=[
            _grid("gut", bought="2026-09-01", sold="2026-09-02T10:00:00+00:00", spent=15.0, pnl=1.0),
            _grid("fremd", bought="2026-09-01", sold="2026-09-02T11:00:00+00:00", spent=15.0, pnl=50.0,
                  symbol="ETHEUR"),
            _grid("fremd-offen", bought="2026-09-05", spent=40.0, symbol=42),
        ],
    )


def test_unknown_currency_is_excluded_from_every_sum(tmp_path):
    """Lieber nicht mitzählen als raten - weder als USDT noch als EUR."""
    dca_path, grid_path, trend_path = _with_unknown(tmp_path)

    overview = summarize_overview(dca_path, grid_path, trend_path)
    assert overview["gesamtgewinn"] == {"USDT": pytest.approx(1.0)}
    assert overview["unrealisiert_geschätzt"]["grid"] == {}
    assert overview["unrealisiert_geschätzt"]["dca"] == {
        "USDT": {"quantity": pytest.approx(0.0002), "avg_price": pytest.approx(75000.0)}
    }
    assert overview["waehrungen"] == ["USDT"]
    assert summarize_pnl_history(grid_path, trend_path)["USDT"][0]["realisierte_pnl_an_diesem_tag"] == (
        pytest.approx(1.0)
    )

    grid = summarize_grid(grid_path)["metrics"]
    assert grid["realized_pnl"] == {"USDT": pytest.approx(1.0)}

    dca = summarize_dca(dca_path)["metrics"]
    assert dca["total_spent"] == {"USDT": pytest.approx(15.0)}
    assert dca["total_quantity"] == pytest.approx(0.0002)


def test_unknown_currency_is_reported_not_hidden(tmp_path):
    """Nicht gezählt heißt nicht verschwiegen: die Zähler stehen in der
    API, die Positionen selbst bleiben in den Listen."""
    dca_path, grid_path, trend_path = _with_unknown(tmp_path)

    overview = summarize_overview(dca_path, grid_path, trend_path)
    assert overview["ohne_waehrung"] == {"dca": 1, "grid": 2, "trend": 0}

    grid = summarize_grid(grid_path)
    assert grid["metrics"]["unknown_currency"] == 2
    assert [(p["symbol"], p["waehrung"]) for p in grid["open_positions"]] == [(42, None)]

    dca = summarize_dca(dca_path)
    assert dca["metrics"]["unknown_currency"] == 1  # der Dry-Run-Eintrag zählt nicht
    assert [p["waehrung"] for p in dca["open_positions"]] == ["USDT", None]
