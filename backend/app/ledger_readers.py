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
from datetime import date, datetime, timedelta, timezone
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


def _int_or(value: Any, default: int) -> int:
    """Ganzzahl aus einem Ledger-Feld, sonst `default`.

    Wird für Sortier-Schlüssel gebraucht: ein Feld, das entgegen dem
    Schema einen String enthält, würde beim Vergleich mit einer Zahl
    sonst TypeError werfen und den ganzen Endpunkt auf 500 ziehen -
    also auch die Anzeige der drei Bots, mit denen alles in Ordnung ist.
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _realized_pnl_sum(closed_records: list[dict]) -> float | None:
    """Summe der realisierten PnL über geschlossene, ECHTE Positionen.

    Dry-Run-Einträge bleiben draußen - sonst stünde ein simulierter
    Gewinn in der Bot-Karte direkt neben dem echten in der
    Gesamtgewinn-Kachel (die schon immer filtert), und beide Zahlen auf
    demselben Bildschirm widersprächen sich.
    """
    values = [
        _num(r.get("realized_pnl"), default=None) for r in closed_records if r.get("dry_run") is False
    ]
    values = [v for v in values if v is not None]
    return sum(values) if values else None


def _latest(values: list[Any]) -> str | None:
    """Größter (= jüngster) ISO-Zeitstempel-String aus einer Liste, None wenn leer.

    ISO-8601-Zeitstempel sind lexikografisch sortierbar, ein echtes Parsen
    ist dafür nicht nötig.
    """
    present = [v for v in values if isinstance(v, str) and v]
    return max(present) if present else None


def _parse_utc_datetime(value: Any) -> datetime | None:
    """Zeitstempel aus dem Ledger als UTC-datetime, oder None.

    Ein Eintrag ohne Zeitzone wird als UTC gelesen - der Bot schreibt
    zwar durchgängig '+00:00', aber ein handgepflegter Eintrag ohne
    Offset soll den Tagesschnitt nicht verschieben.

    Die Umrechnung nach UTC steht mit im try: Ein Randdatum mit Offset
    ('0001-01-01T00:00:00+05:00', '9999-12-31T23:59:59-05:00') parst
    fehlerfrei, läuft aber bei astimezone aus dem datetime-Bereich und
    wirft OverflowError. Solche Werte werden übersprungen wie jeder
    andere unlesbare Zeitstempel.
    """
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return None


def _utc_date(value: Any) -> date | None:
    parsed = _parse_utc_datetime(value)
    return parsed.date() if parsed else None


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

    realized_pnl = _realized_pnl_sum(closed_records)

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
        for r in sorted(open_records, key=lambda r: _int_or(r.get("level_index"), -1))
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

    realized_pnl = _realized_pnl_sum(closed_records)

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


# Feld, das bei jedem Bot den KAUF-/Einstiegszeitpunkt trägt. Der DCA-Bot
# kennt nur Käufe, Grid und Trend tragen den Verkauf in eigenen Feldern.
_BUY_TIME_FIELDS = (("dca", "timestamp"), ("grid", "bought_at"), ("trend", "entry_time"))


def _buy_days_by_mode(
    records_by_bot: dict[str, list[dict]],
) -> tuple[set[date], set[date]]:
    """(Tage mit echtem Kauf, Tage mit Dry-Run-Kauf) über alle Bots hinweg.

    Einträge ohne auswertbares `dry_run`-Feld landen in keiner der beiden
    Mengen - dieselbe konservative Regel wie überall sonst: lieber nicht
    mitzählen als raten.
    """
    real_days: set[date] = set()
    dry_run_days: set[date] = set()

    for bot, time_field in _BUY_TIME_FIELDS:
        for record in records_by_bot.get(bot, []):
            day = _utc_date(record.get(time_field))
            if day is None:
                continue
            flag = record.get("dry_run")
            if flag is False:
                real_days.add(day)
            elif flag is True:
                dry_run_days.add(day)

    return real_days, dry_run_days


def summarize_investment_activity(
    dca_path: Path,
    grid_path: Path,
    trend_path: Path,
    *,
    now: datetime | None = None,
) -> dict:
    """An wie vielen Tagen hat das kombinierte System überhaupt investiert?

    Hintergrund: Skaliert der Allocator den DCA-Betrag unter das
    Mindestvolumen und hat der Trend-Bot am selben Tag kein bestätigtes
    Signal, kauft das System an diesem Tag gar nichts. Diese Tage sind
    sonst nirgends sichtbar.

    Der HEUTIGE UTC-Tag bleibt außen vor. Er ist noch nicht vorbei, ein
    Kauf könnte noch folgen - würde er mitgezählt, startete jeder Tag um
    00:00 UTC zwangsläufig als "ohne Aktivität", und die Quote schwankte
    im Tagesverlauf. Gezählt wird deshalb [erster echter Kauftag ...
    gestern]. Der erste Tag braucht dadurch keine Sonderbehandlung: er ist
    per Definition ein Kauftag.

    `days_with_dry_run_activity` zählt bewusst über die GESAMTE Historie
    (bis gestern), nicht nur im Fenster der echten Metrik - sonst wäre die
    Paper-Trade-Phase unsichtbar, solange es noch keinen einzigen echten
    Kauf gibt.

    WICHTIG für die Interpretation: Das Ledger enthält kein Signal dafür,
    ob der Bot überhaupt lief. Ein Tag ohne Kauf kann "Allocator hat
    heruntergefahren und Trend hatte kein Signal" bedeuten - oder schlicht
    "Bot war aus". Beides sieht in den Daten identisch aus.
    """
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    today = now.date()
    last_completed_day = today - timedelta(days=1)

    dca_records, dca_error = _load_list(dca_path)
    grid_records, grid_error = _load_list(grid_path)
    trend_records, trend_error = _load_list(trend_path)

    real_days, dry_run_days = _buy_days_by_mode(
        {
            "dca": [] if dca_error else dca_records,
            "grid": [] if grid_error else grid_records,
            "trend": [] if trend_error else trend_records,
        }
    )

    completed_dry_run_days = len({day for day in dry_run_days if day <= last_completed_day})
    today_has_activity = today in real_days

    completed_real_days = {day for day in real_days if day <= last_completed_day}
    if not completed_real_days:
        # Noch kein einziger abgeschlossener Tag mit echtem Kauf - eine
        # Quote wäre hier eine Division durch 0 und ohne Aussage.
        return {
            "status": "no_data",
            "total_days_tracked": 0,
            "days_with_activity": 0,
            "days_without_activity": 0,
            "days_without_activity_pct": None,
            "days_with_dry_run_activity": completed_dry_run_days,
            "today_has_activity": today_has_activity,
        }

    first_day = min(completed_real_days)
    total_days = (last_completed_day - first_day).days + 1
    days_with_activity = len(completed_real_days)
    days_without_activity = total_days - days_with_activity

    return {
        "status": "ok",
        "total_days_tracked": total_days,
        "days_with_activity": days_with_activity,
        "days_without_activity": days_without_activity,
        "days_without_activity_pct": round(days_without_activity / total_days * 100, 1),
        "days_with_dry_run_activity": completed_dry_run_days,
        "today_has_activity": today_has_activity,
    }


def summarize_pnl_history(grid_path: Path, trend_path: Path) -> list[dict]:
    """Realisierte PnL je Kalendertag (UTC) plus kumulierter Verlauf.

    Stichtag ist der VERKAUF (sold_at / exit_time), nicht der Kauf - erst
    dort entsteht ein realisierter Gewinn oder Verlust.

    Nur echte, geschlossene Positionen. DCA fehlt hier zwangsläufig: der
    Bot verkauft nie und führt deshalb kein realized_pnl. Tage ohne
    Abschluss bekommen keinen Eintrag - die Liste hat bewusst Lücken,
    das Frontend interpoliert beim Zeichnen.
    """
    grid_records, grid_error = _load_list(grid_path)
    trend_records, trend_error = _load_list(trend_path)

    per_day: dict[date, float] = {}
    for records, time_field in (
        ([] if grid_error else grid_records, "sold_at"),
        ([] if trend_error else trend_records, "exit_time"),
    ):
        for record in records:
            if record.get("status") == "open" or record.get("dry_run") is not False:
                continue
            pnl = _num(record.get("realized_pnl"), default=None)
            if pnl is None:
                continue
            day = _utc_date(record.get(time_field))
            if day is None:
                continue
            per_day[day] = per_day.get(day, 0.0) + pnl

    verlauf = []
    kumuliert = 0.0
    for day in sorted(per_day):
        kumuliert += per_day[day]
        verlauf.append(
            {
                "datum": day.isoformat(),
                "realisierte_pnl_an_diesem_tag": per_day[day],
                "kumulierte_pnl_bis_zu_diesem_tag": kumuliert,
            }
        )
    return verlauf


HEARTBEAT_FILES = (
    ("dca", "heartbeat_dca.json"),
    ("grid", "heartbeat_grid.json"),
    ("trend", "heartbeat_trend.json"),
    ("allocator", "heartbeat_allocator.json"),
)

# Bewusst EINE großzügige, bot-unabhängige Schwelle. Die tatsächlichen
# Zyklus-Intervalle stehen auf Bot-Seite und sind dort konfigurierbar -
# diese App erführe eine Änderung nie. Eine geratene, bot-spezifische
# Schwelle würde deshalb entweder Fehlalarme erzeugen oder einen echten
# Ausfall verschweigen. 48 Stunden liegen sicher über dem längsten
# bekannten Takt (24h) samt Puffer.
STALE_SUCCESS_SECONDS = 48 * 3600


def _heartbeat_status(
    success_dt: datetime | None, failures: float, seconds_since_success: float | None
) -> tuple[str, str | None]:
    """(status, reason) aus den beiden robusten Signalen.

    Nur zwei Dinge lösen eine Warnung aus, beide ohne Raten:
    ein vom Bot selbst gemeldeter Fehlschlag, und eine bestätigte
    Erfolgsmeldung, die älter als STALE_SUCCESS_SECONDS ist.

    Ein Bot ohne jede Erfolgsmeldung, aber auch ohne Fehlschlag, ist
    ausdrücklich KEINE Warnung: Nach einem Neustart ist genau das der
    Normalzustand, bei einem 24h-Takt möglicherweise einen ganzen Tag
    lang. Der Fall wird als 'ok' mit eigenem reason gemeldet, damit das
    Frontend ihn sachlich benennen kann, statt eine Dauer zu behaupten,
    die es nicht gibt.
    """
    if failures > 0:
        return "warn", "consecutive_failures"
    if success_dt is None:
        return "ok", "no_confirmed_success"
    if seconds_since_success is not None and seconds_since_success > STALE_SUCCESS_SECONDS:
        return "warn", "stale_success"
    return "ok", None


def summarize_heartbeats(data_dir: Path, *, now: datetime | None = None) -> dict:
    """Heartbeat-Status der vier Bot-Prozesse.

    Der Bot schreibt je Prozess eine Datei mit last_successful_cycle,
    last_cycle_attempt und consecutive_failures. Die Altersangaben werden
    hier SERVERSEITIG berechnet: Die Dateien entstehen auf derselben
    Maschine, die diese API bedient - damit ist die Differenz frei von
    Uhren-Versatz zwischen Server und Endgerät. Bei einer
    Lebendigkeits-Anzeige wäre eine falsch gehende Handy-Uhr sonst genau
    die gefährliche Fehlerart: sie behauptete Stillstand, wo keiner ist.

    Die Werte gelten nur für den aktuell laufenden Prozess - nach einem
    Neustart beginnt die Zählung bei 0, auch wenn vorher lange erfolgreich
    gelaufen wurde.
    """
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    result: dict[str, dict] = {}

    for bot, filename in HEARTBEAT_FILES:
        data, error = _load_dict(data_dir / filename)
        if error or not data:
            # Fehlende Datei ist ausdrücklich keine Warnung - ein älteres
            # crypto-bot-Deployment kennt das Feature schlicht noch nicht.
            result[bot] = {
                "status": "no_data",
                "reason": None,
                "error": error or f"Heartbeat-Datei {filename} ist leer.",
                "last_successful_cycle": None,
                "last_cycle_attempt": None,
                "consecutive_failures": None,
                "seconds_since_success": None,
                "seconds_since_attempt": None,
            }
            continue

        success_dt = _parse_utc_datetime(data.get("last_successful_cycle"))
        attempt_dt = _parse_utc_datetime(data.get("last_cycle_attempt"))
        seconds_since_success = (now - success_dt).total_seconds() if success_dt else None
        seconds_since_attempt = (now - attempt_dt).total_seconds() if attempt_dt else None

        # Für die Entscheidung wird der Wert in eine Zahl gezwungen, im
        # Response bleibt der Rohwert stehen - ein unsinniger Eintrag soll
        # sichtbar sein und nicht stillschweigend zu 0 werden.
        failures = _num(data.get("consecutive_failures"), default=0) or 0.0
        status, reason = _heartbeat_status(success_dt, failures, seconds_since_success)

        result[bot] = {
            "status": status,
            "reason": reason,
            "last_successful_cycle": data.get("last_successful_cycle"),
            "last_cycle_attempt": data.get("last_cycle_attempt"),
            "consecutive_failures": data.get("consecutive_failures"),
            "seconds_since_success": seconds_since_success,
            "seconds_since_attempt": seconds_since_attempt,
        }

    return result
