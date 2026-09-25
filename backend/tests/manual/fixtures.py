"""Synthetische Demo-Datensätze für die manuellen Browser-Prüfungen.

Aufruf: python fixtures.py <zielordner>
Legt drei Unterordner an, jeder ein vollständiges DATA_DIR:

  demo/          Alles gleichzeitig sichtbar: 8 echte DCA-Käufe (mehr als die
                 früheren 5, damit stilles Abschneiden auffiele), Grid mit
                 Abschlüssen über und unter der Nulllinie plus 4 offenen
                 Positionen, alle vier Heartbeat-Zustände.
  nur_dry_run/   Keine einzige echte Position - Ergebnis-Block muss "Noch kein
                 realisiertes Ergebnis" zeigen. Enthält bewusst einen
                 geschlossenen Dry-Run-Gewinn, der NICHT zählen darf.
  ein_abschluss/ Genau ein echter Abschluss (+0,62) - Zahl ohne Diagramm.

Alle Zeitstempel relativ zu "jetzt": Fest gespeicherte Heartbeats wie
"vor 4 Min." wären schon am nächsten Tag Warnungen. Alle Werte sind
erfunden - bewusst keine Kopie echter Bot-Ledger, dieses Repo liegt auf GitHub.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

JETZT = datetime.now(timezone.utc)
HEUTE = JETZT.date()


def tag(n: int) -> str:
    """Datum n Tage vor heute als 'YYYY-MM-DD'."""
    return (HEUTE - timedelta(days=n)).isoformat()


def vor(**delta) -> str:
    return (JETZT - timedelta(**delta)).isoformat()


def _grid_geschlossen(kauf_tag, verkauf_tag, pnl, idx, dry_run=False):
    return {
        "id": f"g{idx}", "level_index": idx, "buy_price": 100.0, "target_sell_price": 105.0,
        "quantity": 0.0002, "quote_spent": 15.0, "bought_at": f"{kauf_tag}T10:00:00+00:00",
        "dry_run": dry_run, "status": "closed", "sell_price": 100.0 + pnl,
        "sold_at": f"{verkauf_tag}T15:00:00+00:00", "realized_pnl": pnl,
    }


def _allocator():
    return {"trend_fraction": 0.34, "raw_target_fraction": 0.4, "gap_pct": 1.85,
            "direction": "up", "updated_at": JETZT.isoformat()}


def demo() -> dict[str, object]:
    preise = [76120.5, 77340.0, 75980.25, 78210.0, 77055.75, 76400.0, 78890.5, 77610.0]
    dca = [
        {"timestamp": f"{tag(20 - 2 * i)}T09:00:00+00:00", "symbol": "BTCUSDT", "quote_spent": 15.0,
         "quantity": round(15.0 / preis, 8), "price": preis, "dry_run": False}
        for i, preis in enumerate(preise)
    ]
    dca.append({"timestamp": f"{tag(1)}T09:00:00+00:00", "symbol": "BTCUSDT", "quote_spent": 15.0,
                "quantity": 0.0002, "price": 75000.0, "dry_run": True})

    # Netto 2,40 + 1,10 - 5,80 - 1,20 + 3,75 + 2,90 = +3,15 (Gewinn 10,15 / Verlust -7,00);
    # der Verlauf kreuzt die Nulllinie. Der Dry-Run-Abschluss (+999) darf nirgends auftauchen.
    grid = [
        _grid_geschlossen(tag(20), tag(18), 2.40, 1),
        _grid_geschlossen(tag(17), tag(15), 1.10, 2),
        _grid_geschlossen(tag(14), tag(12), -5.80, 3),
        _grid_geschlossen(tag(11), tag(11), -1.20, 4),
        _grid_geschlossen(tag(9), tag(6), 3.75, 5),
        _grid_geschlossen(tag(5), tag(3), 2.90, 6),
        _grid_geschlossen(tag(4), tag(3), 999.0, 7, dry_run=True),
    ]
    for i, kauf in enumerate([76800.0, 77200.0, 77600.0, 78000.0]):
        grid.append({
            "id": f"offen-{i}", "level_index": 10 + i, "buy_price": kauf,
            "target_sell_price": kauf * 1.004, "quantity": 0.0002, "quote_spent": 15.0,
            "bought_at": f"{tag(2)}T1{i}:00:00+00:00", "dry_run": False, "status": "open",
            "sell_price": None, "sold_at": None, "realized_pnl": None,
        })

    trend = [{
        "id": "t-offen", "entry_price": 76901.56, "entry_time": f"{tag(5)}T12:00:00+00:00",
        "quantity": 0.000195, "quote_spent": 15.0, "dry_run": True, "status": "open",
        "exit_price": None, "exit_time": None, "exit_reason": None, "realized_pnl": None,
        "stop_loss_order_id": None,
    }]

    return {
        "trade_ledger.json": dca,
        "grid_positions.json": grid,
        "trend_ledger.json": trend,
        "allocator_state.json": _allocator(),
        # Alle vier Heartbeat-Zustände auf einmal
        "heartbeat_dca.json": {"last_successful_cycle": vor(minutes=4),
                               "last_cycle_attempt": vor(minutes=4), "consecutive_failures": 0},
        "heartbeat_grid.json": {"last_successful_cycle": vor(hours=3),
                                "last_cycle_attempt": vor(minutes=1), "consecutive_failures": 4},
        "heartbeat_trend.json": {"last_successful_cycle": None,
                                 "last_cycle_attempt": vor(minutes=2), "consecutive_failures": 0},
        "heartbeat_allocator.json": {"last_successful_cycle": vor(hours=53),
                                     "last_cycle_attempt": vor(minutes=1), "consecutive_failures": 0},
    }


def nur_dry_run() -> dict[str, object]:
    return {
        "trade_ledger.json": [
            {"timestamp": f"{tag(n)}T09:00:00+00:00", "symbol": "BTCUSDT", "quote_spent": 15.0,
             "quantity": 0.0002, "price": 77000.0, "dry_run": True} for n in (4, 3, 2)
        ],
        "grid_positions.json": [
            _grid_geschlossen(tag(6), tag(5), 5.0, 1, dry_run=True),  # simulierter Gewinn: zählt nicht
            {"id": "g2", "level_index": 2, "buy_price": 77000.0, "target_sell_price": 77300.0,
             "quantity": 0.0002, "quote_spent": 15.0, "bought_at": f"{tag(2)}T10:00:00+00:00",
             "dry_run": True, "status": "open", "sell_price": None, "sold_at": None, "realized_pnl": None},
        ],
        "trend_ledger.json": [{
            "id": "t1", "entry_price": 76900.0, "entry_time": f"{tag(3)}T12:00:00+00:00",
            "quantity": 0.000195, "quote_spent": 15.0, "dry_run": True, "status": "open",
            "exit_price": None, "exit_time": None, "exit_reason": None, "realized_pnl": None,
        }],
        "allocator_state.json": _allocator(),
    }


def ein_abschluss() -> dict[str, object]:
    return {
        "trade_ledger.json": [{"timestamp": f"{tag(6)}T09:00:00+00:00", "symbol": "BTCUSDT",
                               "quote_spent": 15.0, "quantity": 0.0002, "price": 75000.0,
                               "dry_run": False}],
        "grid_positions.json": [_grid_geschlossen(tag(6), tag(4), 0.62, 1)],
        "trend_ledger.json": [],
        "allocator_state.json": _allocator(),
    }


DATENSAETZE = {"demo": demo, "nur_dry_run": nur_dry_run, "ein_abschluss": ein_abschluss}


def schreibe_alle(ziel: Path) -> dict[str, Path]:
    ordner = {}
    for name, erzeuge in DATENSAETZE.items():
        pfad = ziel / name
        pfad.mkdir(parents=True, exist_ok=True)
        for datei, inhalt in erzeuge().items():
            (pfad / datei).write_text(json.dumps(inhalt, indent=2), encoding="utf-8")
        ordner[name] = pfad
    return ordner


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Aufruf: python fixtures.py <zielordner>")
    for name, pfad in schreibe_alle(Path(sys.argv[1])).items():
        print(f"{name:<14} {pfad}")
