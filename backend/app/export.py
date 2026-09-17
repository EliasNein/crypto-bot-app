"""CSV-Export aller ECHTEN Trades (dry_run: false) aus den drei Bot-Ledgern.

Gedacht als Rohdaten-Vorbereitung für eine spätere steuerliche Bewertung
durch einen Steuerberater - keine Steuerberatung, keine Währungsumrechnung.

Nur echte Trades: eine Auswertung auf Basis simulierter Dry-Run-Positionen
wäre für eine Steuererklärung grundlegend falsch, deshalb werden sie hier
komplett ausgeschlossen statt nur markiert - dieselbe Regel wie bei den
gesamtgewinn/gesamtverlust-Kennzahlen in ledger_readers.py.

Grid und Trend führen in ihrem Ledger kein eigenes 'symbol'-Feld (nur der
DCA-Ledger hat eins) - das Symbol ist Konfiguration des jeweiligen Bots,
nicht Teil des Eintrags (siehe dca_bot/audit_positions.py, das dafür
GRID_SYMBOL/TREND_SYMBOL mit Default BTCUSDT aus der Umgebung liest).
Für den Export wird deshalb derselbe Standardwert verwendet.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .ledger_readers import _load_list, _num

DEFAULT_SYMBOL = "BTCUSDT"

VALID_PERIODS = ("all", "week", "month", "year")

CSV_HEADER = [
    "datum_zeit_utc",
    "bot",
    "symbol",
    "seite",
    "menge_btc",
    "preis_usdt",
    "betrag_usdt",
    "realisierter_pnl_usdt",
    "position_id",
]


def _dca_rows(records: list[dict]) -> list[list[Any]]:
    rows = []
    for r in records:
        if r.get("dry_run") is not False:
            continue
        rows.append(
            [
                r.get("timestamp"),
                "dca",
                r.get("symbol", DEFAULT_SYMBOL),
                "BUY",
                r.get("quantity"),
                r.get("price"),
                r.get("quote_spent"),
                None,  # DCA verkauft nie - kein realisierter PnL
                None,  # DCA-Einträge tragen keine eigene Positions-ID
            ]
        )
    return rows


def _round_trip_rows(
    records: list[dict],
    *,
    bot: str,
    buy_time_field: str,
    buy_price_field: str,
    sell_time_field: str,
    sell_price_field: str,
) -> list[list[Any]]:
    """Gemeinsame Kauf/Verkauf-Logik für Grid und Trend: eine Kauf-Zeile
    immer, eine Verkauf-Zeile nur wenn die Position bereits geschlossen ist.
    """
    rows: list[list[Any]] = []
    for r in records:
        if r.get("dry_run") is not False:
            continue

        quantity = r.get("quantity")
        quote_spent = _num(r.get("quote_spent"), default=None)
        position_id = r.get("id")

        rows.append(
            [
                r.get(buy_time_field),
                bot,
                DEFAULT_SYMBOL,
                "BUY",
                quantity,
                r.get(buy_price_field),
                quote_spent,
                None,
                position_id,
            ]
        )

        if r.get("status") == "open":
            continue  # Verkauf steht noch aus - keine zweite Zeile

        realized_pnl = _num(r.get("realized_pnl"), default=None)
        # Verkaufserlös direkt aus den Ledger-Feldern abgeleitet
        # (Einsatz + realisierter PnL), statt neu aus Preis*Menge zu
        # rechnen - das bleibt konsistent mit dem PnL, den das Ledger
        # selbst führt.
        sell_amount = quote_spent + realized_pnl if quote_spent is not None and realized_pnl is not None else None

        rows.append(
            [
                r.get(sell_time_field),
                bot,
                DEFAULT_SYMBOL,
                "SELL",
                quantity,
                r.get(sell_price_field),
                sell_amount,
                realized_pnl,
                position_id,
            ]
        )
    return rows


def _grid_rows(records: list[dict]) -> list[list[Any]]:
    return _round_trip_rows(
        records,
        bot="grid",
        buy_time_field="bought_at",
        buy_price_field="buy_price",
        sell_time_field="sold_at",
        sell_price_field="sell_price",
    )


def _trend_rows(records: list[dict]) -> list[list[Any]]:
    return _round_trip_rows(
        records,
        bot="trend",
        buy_time_field="entry_time",
        buy_price_field="entry_price",
        sell_time_field="exit_time",
        sell_price_field="exit_price",
    )


def _period_range(period: str, now: datetime) -> tuple[datetime | None, datetime]:
    """(start, end) für den gewählten Zeitraum, in UTC.

    `end` ist immer "heute 23:59:59 UTC" - funktional identisch mit "jetzt",
    da kein Ledger-Eintrag je in der Zukunft liegt, aber als runde Anzeige
    im Kommentarblock verständlicher als eine krumme Uhrzeit.

    `start=None` bedeutet "keine Filterung" (period="all").
    """
    end = now.replace(hour=23, minute=59, second=59, microsecond=999999)

    if period == "all":
        return None, end
    if period == "week":
        return end - timedelta(days=7), end
    if period == "month":
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0), end
    if period == "year":
        return now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0), end

    raise ValueError(f"Ungültiger period-Wert '{period}'. Erlaubt: {', '.join(VALID_PERIODS)}.")


def _parse_iso(ts: Any) -> datetime | None:
    """Zeitstempel aus dem Ledger, oder None wenn er nicht auswertbar ist.

    Fängt auch TypeError: steht im Ledger entgegen dem Schema eine Zahl
    statt eines ISO-Strings, wirft fromisoformat TypeError statt
    ValueError - ungefangen würde das den Export auf 500 ziehen.
    """
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None


def _sort_key(ts: Any) -> str:
    """Sortier-Schlüssel, der garantiert ein String ist.

    Ein nicht-stringiger Zeitstempel im Ledger würde beim Vergleich mit
    den übrigen Zeilen sonst TypeError werfen (str vs. int).
    """
    return ts if isinstance(ts, str) else ""


def _row_in_range(row: list[Any], start: datetime | None, end: datetime) -> bool:
    if start is None:
        return True  # period="all" - keine Filterung

    parsed = _parse_iso(row[0])
    if parsed is None:
        return False  # kein auswertbarer Zeitstempel - im gefilterten Export lieber weglassen als raten

    return start <= parsed <= end


def _period_comment(period: str, start: datetime | None, end: datetime, now: datetime) -> str:
    if period == "all" or start is None:
        return "# Zeitraum: Alle Daten (keine Zeitraum-Filterung, alle echten Trades enthalten)."

    fmt = "%d.%m.%Y %H:%M UTC"
    label = {
        "week": "Woche",
        "month": f"Monat {now.month:02d}.{now.year}",
        "year": f"Jahr {now.year}",
    }[period]

    return (
        f"# Zeitraum: {label} ({start.strftime(fmt)} bis {end.strftime(fmt)}) - "
        "HINWEIS: Positionen, die vor diesem Zeitraum eröffnet wurden, "
        "zeigen ggf. nur die Verkaufs-Zeile."
    )


def _comment_block(period: str, start: datetime | None, end: datetime, now: datetime) -> str:
    generated_at = now.strftime("%Y-%m-%d %H:%M UTC")
    return "\n".join(
        [
            "# HINWEIS: Alle Preise/Beträge in USDT (US-Dollar-Stablecoin), NICHT in Euro.",
            "# Für eine steuerliche Bewertung ist der Euro-Gegenwert zum jeweiligen Transaktionszeitpunkt erforderlich - diese CSV enthält KEINE Währungsumrechnung.",
            f"# Export erstellt am: {generated_at}, Datenquelle: Homeserver-Ledger, nur echte Trades (dry_run: false).",
            _period_comment(period, start, end, now),
            "# Dies ist keine Steuerberatung, nur eine Rohdatenaufbereitung.",
        ]
    )


def build_trades_csv(
    dca_path: Path,
    grid_path: Path,
    trend_path: Path,
    *,
    period: str = "all",
    now: datetime | None = None,
) -> str:
    """Baut die CSV. `now` ist injizierbar, damit Tests feste Zeitpunkte
    verwenden können statt gegen die echte Uhrzeit zu laufen.

    Wirft ValueError bei einem unbekannten period-Wert - main.py wandelt
    das in eine 400-Antwort um.
    """
    now = now or datetime.now(timezone.utc)
    start, end = _period_range(period, now)

    dca_records, _ = _load_list(dca_path)
    grid_records, _ = _load_list(grid_path)
    trend_records, _ = _load_list(trend_path)

    rows = _dca_rows(dca_records) + _grid_rows(grid_records) + _trend_rows(trend_records)
    rows = [row for row in rows if _row_in_range(row, start, end)]
    rows.sort(key=lambda row: _sort_key(row[0]))

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_HEADER)
    writer.writerows(rows)

    return buffer.getvalue() + "\n" + _comment_block(period, start, end, now) + "\n"
