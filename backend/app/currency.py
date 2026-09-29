"""Zu welchem Handelspaar - und damit zu welcher Währung - gehört ein
Ledger-Eintrag?

Die EINZIGE Stelle, die diese Regel kennt. ledger_readers.py (Summen)
und export.py (CSV) fragen beide hier nach, damit Anzeige und Export
einen Eintrag nie unterschiedlich einordnen.

Hintergrund: Binance hat für Kunden im EWR die USDT-Spot-Paare entfernt,
für echtes Geld wechselt der Bot auf BTCEUR. Beträge verschiedener
Währungen dürfen nie addiert werden - jede Summe dieser App wird deshalb
je Währung gebildet.
"""

from __future__ import annotations

from typing import Any

# Stand 29.09.2026. Bis zur "Symbolbindung" im crypto-bot (Commits
# e2a37bd bis 9ef7d60, auf dem Homeserver deployt mit Stand 980f3c3 am
# 29.09.2026) trugen nur DCA-Einträge ein Feld `symbol`, Grid- und
# Trend-Einträge nicht - das Paar war damals reine Bot-Konfiguration.
# Seitdem schreibt der Bot `symbol` in jeden NEUEN Grid-/Trend-Eintrag;
# alte Einträge werden nicht nachträglich gestempelt.
#
# Für Einträge ohne Feld gilt auf Bot-Seite BTCUSDT (Entscheidung E1 vom
# 28.09.2026, dca_bot/symbol_guard.py:effective_symbol): Jedes bis dahin
# existierende Ledger stammt aus BTCUSDT-Läufen. Diese App übernimmt
# genau dieselbe Regel - auch für `null`, das der Bot ebenfalls als
# Altbestand liest -, damit beide Repos Altbestände identisch einordnen.
# Eine eigene, abweichende Regel wäre Raten. Nicht ändern: die Konstante
# beschreibt Vergangenheit.
LEGACY_SYMBOL = "BTCUSDT"

# Das Dashboard zeigt Mengen in BTC - ein Paar mit anderer Basis würde
# seine Menge still in die BTC-Summen tragen und ist deshalb unbekannt.
BASE_ASSET = "BTC"

# Bekannte Quote-Assets: (Bezeichnung, braucht die Steuer eine Umrechnung
# in Euro?). Alles andere gilt als unbestimmbar. Ein weiteres Paar
# nachzutragen ist eine Zeile.
QUOTES = {
    "USDT": ("US-Dollar-Stablecoin", True),
    "USDC": ("US-Dollar-Stablecoin", True),
    "EUR": ("Euro", False),
}


def resolve(record: dict) -> tuple[Any, str | None]:
    """(symbol, währung) eines Ledger-Eintrags.

    - Feld fehlt oder ist null: (LEGACY_SYMBOL, "USDT") - siehe oben.
    - Text der Form BTC<bekannte Quote> (Leerraum am Rand wird wie beim
      Bot ignoriert): (symbol, quote).
    - Alles andere (leerer Text, Zahl, anderes Paar wie ETHEUR oder
      BTCXYZ): (Rohwert, None). Die Währung ist dann UNBESTIMMBAR - der
      Eintrag fließt in keine Summe ein, statt geraten zu werden.

    Beim Bot verhindert eine Startprüfung, dass ein fremdes Paar
    überhaupt ins Ledger kommt; der Fall ist also eine Anomalie
    (manuelles Editieren), aber dann soll er sichtbar sein.
    """
    value = record.get("symbol")
    if value is None:
        return LEGACY_SYMBOL, "USDT"
    if not isinstance(value, str) or not value.strip():
        return value, None

    symbol = value.strip()
    quote = symbol[len(BASE_ASSET):] if symbol.startswith(BASE_ASSET) else None
    if quote not in QUOTES:
        return symbol, None
    return symbol, quote


def currency_of(record: dict) -> str | None:
    """Nur die Währung - None heißt: unbestimmbar, nicht mitzählen."""
    return resolve(record)[1]
