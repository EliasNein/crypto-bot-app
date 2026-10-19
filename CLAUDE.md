# Crypto-Bot-App – Projektkontext für Claude Code

Read-only FastAPI-Backend + Vanilla-JS-Frontend, zeigt Live-Status des
Trading-Bots an. Liest NUR data/*.json-Ledger, hat KEINEN Binance-Zugriff.

## Tests
pytest backend/tests/ (Playwright-Browsertests brauchen Chromium, siehe README)

## Arbeitsweise
- Design-Änderungen: vorher messen (Anzahl Kästen, Schriftgrößen etc.),
  nachher denselben Maßstab zum Vergleich zeigen
- Kein Binance-Zugriff, keine Schreibrechte auf die Ledger - diese Trennung
  ist bewusst und darf nie aufgeweicht werden
- Commits ohne Co-Authored-By-Zeile und ohne 'Generated with'-Zeile.
  Nur der Betreiber pusht.

  ## Umfang des Einlesens
Nicht bei jeder Aufgabe alles lesen. Zwei Modi:

- Gezielt (Standard): Bei einer klar umrissenen Aufgabe (ein Bug, eine
  einzelne Funktion, eine Doku-Korrektur) nur die tatsächlich betroffenen
  Module lesen, nicht den ganzen dca_bot/-Ordner. Bei Unsicherheit, welche
  Module betroffen sind, gezielt danach suchen (grep/Suche), nicht
  vorsorglich alles öffnen.
- Vollständig: Nur bei ausdrücklich verlangten Audits, Sicherheitsüber-
  prüfungen oder wenn ich das Wort "vollständig"/"kompletter Systemcheck"
  verwende. Dann wie bisher: alles lesen, nichts überspringen.

Im Zweifel nachfragen, welcher Modus gemeint ist, statt zu raten.