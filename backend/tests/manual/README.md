# Manuelle Browser-Prüfungen (noch nicht in der Test-Suite)

> **Status:** Diese Skripte sind **nicht** Teil von `pytest`. Sie heißen
> bewusst nicht `test_*.py` und werden deshalb von der Suite ignoriert.
> Sie sichern die Browser-Prüfungen aus den Design-Runden P1–P8 vom
> 26.09.2026, bis sie als echte Tests übernommen sind.

## Warum es sie gibt

Beim App-Check vom 26.09.2026 fiel auf (Befund 2): Die gesamte
Design-Überarbeitung P1–P8 hat im Frontend **keine automatisierten Tests**.
Die drei vorhandenen Browser-Tests (`tests/test_frontend_login_flow.py`)
prüfen nur Login und Overlay. Besonders heikel:

- **Das Netto-Ergebnis** (die wichtigste Zahl der Seite) wird nur im
  Frontend berechnet (`renderHero` in `frontend/app.js`), das Backend
  liefert es nicht. Kein Backend-Test deckt es ab.
- **Die Behebung des stillen Abschneidens:** Die DCA-Karte zeigte früher
  nur 5 Käufe, ältere verschwanden ohne Hinweis. Mit den Demo-Daten liefert
  die API 13 Positionen, vorher standen 10 auf der Seite.
- **Die Aufklapp-Logik**, die „+1"-Regel und das Offenhalten beim
  45-Sekunden-Refresh.

## Ausführen

Voraussetzung wie für die Browser-Tests: `pip install -r requirements-dev.txt`
und einmalig `python -m playwright install chromium`.

```bash
cd backend
python tests/manual/run_checks.py
```

`run_checks.py` erzeugt die Datensätze, startet drei Server auf freien
Ports, führt beide Skripte aus und beendet die Server wieder. Screenshots
landen in `tests/manual/out/` (von git ignoriert).

## Inhalt

| Datei | Zweck |
|---|---|
| `fixtures.py` | Drei **synthetische** Datensätze, zeitlich relativ zu „jetzt": `demo` (alles sichtbar, 8 DCA-Käufe, alle Heartbeat-Zustände), `nur_dry_run` (kein echter Trade), `ein_abschluss` (genau ein Abschluss). Bewusst keine Kopie echter Bot-Ledger, das Repo liegt auf GitHub. |
| `verify_round2.py` | 12 Prüfungen: Aufklappen bleibt beim Refresh erhalten, „+1"-Regel, Ergebnis-Block ohne echte Trades („Noch kein realisiertes Ergebnis" statt 0,00), Ergebnis-Block mit einem Abschluss (Zahl ohne Diagramm, Verlust als „0,00" statt „+0,00"). |
| `measure_round2.py` | Strukturmessung aus Runde 2 (Kästen, Titel-Stile, Abstände, Radien) plus die harte Prüfung **„kein Informationsverlust"**: Jede Position und jeder Betrag aus der API muss nach dem Aufklappen auf der Seite stehen. |
| `run_checks.py` | Startet alles, siehe oben. |

## Nächster Schritt (Befund 2)

In die Suite übernehmen, nach dem Muster von
`tests/test_frontend_login_flow.py`: Dort gibt es bereits Fixtures für einen
echten uvicorn-Prozess und einen Browser. Die Prüfungen aus
`verify_round2.py` und die Kein-Informationsverlust-Prüfung aus
`measure_round2.py` werden zu `test_*`-Funktionen, `fixtures.py` liefert die
Daten. Danach kann dieser Ordner weg.

Hinweis zur Messung: Sichtbarkeit wird mit `element.checkVisibility()`
geprüft, nicht über `display`/`visibility`/Größe. Chromium versteckt den
Inhalt eines geschlossenen `<details>` über `content-visibility`, und das
erkennt nur `checkVisibility()`. Mit der einfachen Prüfung werden
eingeklappte Zeilen fälschlich als sichtbar gezählt.
