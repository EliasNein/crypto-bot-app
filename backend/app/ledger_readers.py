"""Rein lesende Auswertung der vier Ledger-Dateien des Trading-Bots.

Dieses Modul liest ausschließlich JSON-Dateien von der Platte (json.load).
Es importiert nichts aus dem Bot-Projekt, hat keine Binance-Anbindung und
schreibt nirgendwo hin. Jede Lese-Funktion fängt fehlende oder kaputte
Dateien selbst ab und gibt einen "no_data"-Status zurück statt eine
Exception zu werfen - ein Problem bei einem Bot darf die Anzeige der
anderen drei nicht verhindern.

Die Feldnamen (buy_price, target_sell_price, entry_price, trend_fraction,
...) folgen dem tatsächlichen Ledger-Format des Bots, wie es in
dca_bot/audit_positions.py und dca_bot/allocator.py zu sehen ist - dieses
Modul liest diese Struktur nur nach, importiert aber keinen Code von dort.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _load_json(path: Path, expected_type: type) -> tuple[Any, str | None]:
    if not path.exists():
        return None, f"Datei nicht gefunden: {path.name}"
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        return None, f"Ungültiges JSON in {path.name}: {exc}"
    except OSError as exc:
        return None, f"Datei nicht lesbar ({path.name}): {exc}"

    if not isinstance(data, expected_type):
        return None, f"Unerwartetes Format in {path.name} (erwartet {expected_type.__name__})."
    return data, None


def _load_list(path: Path) -> tuple[list[dict], str | None]:
    data, error = _load_json(path, list)
    if error:
        return [], error
    return [r for r in data if isinstance(r, dict)], None


def _load_dict(path: Path) -> tuple[dict, str | None]:
    data, error = _load_json(path, dict)
    if error:
        return {}, error
    return data, None


def _num(value: Any, default: float | None = 0.0) -> float | None:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _latest(values: list[Any]) -> str | None:
    """Größter (= jüngster) ISO-Zeitstempel-String aus einer Liste, None wenn leer.

    ISO-8601-Zeitstempel sind lexikografisch sortierbar, ein echtes Parsen
    ist dafür nicht nötig.
    """
    present = [v for v in values if isinstance(v, str) and v]
    return max(present) if present else None


def _cost_basis(records: list[dict]) -> dict:
    """Menge und durchschnittlicher Einstandspreis (quote_spent / quantity)
    über die übergebenen Records - ohne jeden aktuellen Kurs, also ohne
    Aussage über einen unrealisierten Gewinn/Verlust.
    """
    quantity = sum(_num(r.get("quantity")) or 0.0 for r in records)
    spent = sum(_num(r.get("quote_spent")) or 0.0 for r in records)
    avg_price = (spent / quantity) if quantity else None
    return {"quantity": quantity, "avg_price": avg_price}


def summarize_dca(path: Path) -> dict:
    """DCA-Bot: reine Kauf-Liste, kein 'status'-Feld, es wird nie verkauft.

    Jeder echte (nicht Dry-Run-) Kauf ist damit dauerhaft Bestand - siehe
    audit_positions.py:dca_claim(). Genau diese Käufe werden hier als
    "offene Positionen" gezeigt.
    """
    records, error = _load_list(path)
    if error:
        return {"status": "no_data", "error": error}

    real = [r for r in records if r.get("dry_run") is False]
    dry_run_count = sum(1 for r in records if r.get("dry_run") is True)

    basis = _cost_basis(real)
    total_quantity = basis["quantity"]
    total_spent = sum(_num(r.get("quote_spent")) or 0.0 for r in real)
    avg_price = basis["avg_price"]

    open_positions = [
        {
            "symbol": r.get("symbol"),
            "price": r.get("price"),
            "quantity": r.get("quantity"),
            "quote_spent": r.get("quote_spent"),
            "timestamp": r.get("timestamp"),
        }
        for r in real
    ]

    return {
        "status": "ok",
        "open_positions": open_positions,
        "last_activity": _latest([r.get("timestamp") for r in records]),
        "metrics": {
            "total_trades": len(records),
            "real_trades": len(real),
            "dry_run_trades": dry_run_count,
            "total_quantity": total_quantity,
            "total_spent": total_spent,
            "avg_entry_price": avg_price,
        },
    }


def summarize_grid(path: Path) -> dict:
    """Grid-Bot: Liste von Positionen mit status open/closed."""
    records, error = _load_list(path)
    if error:
        return {"status": "no_data", "error": error}

    open_records = [r for r in records if r.get("status") == "open"]
    closed_records = [r for r in records if r.get("status") != "open"]

    realized_pnl_values = [_num(r.get("realized_pnl"), default=None) for r in closed_records]
    realized_pnl_values = [v for v in realized_pnl_values if v is not None]
    realized_pnl = sum(realized_pnl_values) if realized_pnl_values else None

    open_positions = [
        {
            "id": r.get("id"),
            "level_index": r.get("level_index"),
            "buy_price": r.get("buy_price"),
            "target_sell_price": r.get("target_sell_price"),
            "quantity": r.get("quantity"),
            "quote_spent": r.get("quote_spent"),
            "bought_at": r.get("bought_at"),
            "dry_run": r.get("dry_run"),
        }
        for r in sorted(open_records, key=lambda r: r.get("level_index") if r.get("level_index") is not None else -1)
    ]

    return {
        "status": "ok",
        "open_positions": open_positions,
        "last_activity": _latest([r.get("sold_at") or r.get("bought_at") for r in records]),
        "metrics": {
            "total_positions": len(records),
            "open_positions": len(open_records),
            "closed_positions": len(closed_records),
            "realized_pnl": realized_pnl,
        },
    }


def summarize_trend(path: Path) -> dict:
    """Trend-Bot: Liste von Trades, per Design höchstens einer offen."""
    records, error = _load_list(path)
    if error:
        return {"status": "no_data", "error": error}

    open_records = [r for r in records if r.get("status") == "open"]
    closed_records = [r for r in records if r.get("status") != "open"]

    realized_pnl_values = [_num(r.get("realized_pnl"), default=None) for r in closed_records]
    realized_pnl_values = [v for v in realized_pnl_values if v is not None]
    realized_pnl = sum(realized_pnl_values) if realized_pnl_values else None

    open_positions = [
        {
            "id": r.get("id"),
            "entry_price": r.get("entry_price"),
            "entry_time": r.get("entry_time"),
            "quantity": r.get("quantity"),
            "quote_spent": r.get("quote_spent"),
            "dry_run": r.get("dry_run"),
            "stop_loss_order_id": r.get("stop_loss_order_id"),
        }
        for r in open_records
    ]

    return {
        "status": "ok",
        "open_positions": open_positions,
        "last_activity": _latest([r.get("exit_time") or r.get("entry_time") for r in records]),
        "metrics": {
            "total_trades": len(records),
            "open_trades": len(open_records),
            "closed_trades": len(closed_records),
            "realized_pnl": realized_pnl,
        },
    }


def summarize_allocator(path: Path) -> dict:
    """Allocator: einzelnes State-Objekt (Dict), keine Liste.

    Feldnamen entsprechen allocator.py:execute_once() (trend_fraction,
    raw_target_fraction, gap_pct, direction, updated_at).
    """
    data, error = _load_dict(path)
    if error:
        return {"status": "no_data", "error": error}
    if not data:
        return {"status": "no_data", "error": "Allocator-State-Datei ist leer."}

    trend_fraction = _num(data.get("trend_fraction"), default=None)
    dca_fraction = (1 - trend_fraction) if trend_fraction is not None else None

    return {
        "status": "ok",
        "trend_fraction": trend_fraction,
        "dca_fraction": dca_fraction,
        "raw_target_fraction": data.get("raw_target_fraction"),
        "gap_pct": data.get("gap_pct"),
        "direction": data.get("direction"),
        "last_activity": data.get("updated_at"),
    }


def _realized_pnl_totals(records: list[dict]) -> tuple[float, float]:
    """Summe positiver bzw. negativer realized_pnl-Werte aus geschlossenen,
    ECHTEN (dry_run=False) Positionen.

    Dry-Run-Positionen fließen bewusst nicht ein: sie existierten nie an
    der Börse, ein simulierter Gewinn/Verlust wäre neben einem echten
    schlicht Fantasie.
    """
    gain = 0.0
    loss = 0.0
    for r in records:
        if r.get("status") == "open" or r.get("dry_run") is not False:
            continue
        pnl = _num(r.get("realized_pnl"), default=None)
        if pnl is None:
            continue
        if pnl > 0:
            gain += pnl
        elif pnl < 0:
            loss += pnl
    return gain, loss


def summarize_overview(dca_path: Path, grid_path: Path, trend_path: Path) -> dict:
    """Bot-übergreifende Kennzahlen: realisierter Gewinn/Verlust (nur echte,
    geschlossene Grid-/Trend-Positionen) sowie eine grobe, kursfreie
    Schätzung des unrealisierten Bestands je Bot.

    Bewusst KEIN berechneter unrealisierter Gewinn/Verlust: dafür fehlt
    dem Backend der aktuelle Kurs (kein Binance-Zugriff), und ein Wert
    mit geratenem/veraltetem Kurs wäre irreführender als gar keiner.
    """
    dca_records, dca_error = _load_list(dca_path)
    grid_records, grid_error = _load_list(grid_path)
    trend_records, trend_error = _load_list(trend_path)

    gesamtgewinn = 0.0
    gesamtverlust = 0.0
    for records, error in ((grid_records, grid_error), (trend_records, trend_error)):
        if error:
            continue
        gain, loss = _realized_pnl_totals(records)
        gesamtgewinn += gain
        gesamtverlust += loss

    dca_unrealized = None if dca_error else _cost_basis([r for r in dca_records if r.get("dry_run") is False])
    grid_unrealized = (
        None
        if grid_error
        else _cost_basis([r for r in grid_records if r.get("status") == "open" and r.get("dry_run") is False])
    )
    trend_unrealized = (
        None
        if trend_error
        else _cost_basis([r for r in trend_records if r.get("status") == "open" and r.get("dry_run") is False])
    )

    return {
        "gesamtgewinn": gesamtgewinn,
        "gesamtverlust": gesamtverlust,
        "unrealisiert_geschätzt": {
            "dca": dca_unrealized,
            "grid": grid_unrealized,
            "trend": trend_unrealized,
            "hinweis": "kein Live-Kurs, daher keine Berechnung des unrealisierten Gewinns/Verlusts",
        },
    }
