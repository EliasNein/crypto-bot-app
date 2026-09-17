# Trading Bot Dashboard

Read-only, mobil-optimiertes Web-Dashboard zur Anzeige der Stats des
Trading-Bots (DCA, Grid, Trend, Allocator).

**Isolationsprinzip:** Diese App ist ein komplett eigenständiges Projekt.
Sie liest nur die vier Ledger-Dateien des Bots (`trade_ledger.json`,
`grid_positions.json`, `trend_ledger.json`, `allocator_state.json`) per
`json.load()`, ändert dort nie etwas, importiert keinen Code aus dem
Bot-Projekt, hat keinen Zugriff auf dessen `.env`/API-Keys und enthält
keinerlei Binance-Anbindung. Ein Trade auszulösen ist mit diesem Code
strukturell nicht möglich.

## Struktur

```
backend/    FastAPI-App (Python) - liest die Ledger-Dateien, liefert JSON
frontend/   Statisches HTML/CSS/JS ohne Build-Prozess
data/       Beispiel-JSON-Dateien für die lokale Entwicklung
```

## Starten (Backend + Frontend in einem Prozess)

Die FastAPI-Instanz liefert beides aus: die API-Endpunkte **und** das
Frontend (`frontend/` ist unter `/` gemountet). Es wird also nur ein
Prozess auf einem Port gebraucht, kein separater Webserver für die
statischen Dateien.

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/Mac
pip install -r requirements.txt

# Token setzen (Pflicht) - entweder als Umgebungsvariable oder in .env:
copy .env.example .env        # Windows
# cp .env.example .env        # Linux/Mac
# dann DASHBOARD_TOKEN in .env auf einen eigenen Wert setzen,
# z.B. erzeugt mit: openssl rand -hex 32

uvicorn app.main:app --reload --port 8000
```

Dann `http://localhost:8000/` im Browser öffnen - das ist das Dashboard.
Beim ersten Laden nach dem Token fragen lassen (das aus der `.env`); das
Feld "Backend-URL" bleibt dabei **leer**, weil API und Frontend von
derselben Adresse kommen.

Ohne `DATA_DIR`-Angabe liest das Backend automatisch aus `../data`
(die mitgelieferten Beispieldateien). Für den echten Server: `DATA_DIR`
auf den `data/`-Ordner des Bots setzen.

Endpunkte:
- `GET /health` - kein Token nötig, liefert `{"status": "ok"}`.
- `GET /api/status` - Token per Header `X-Dashboard-Token: <token>` oder
  Query-Parameter `?token=<token>`. Ohne/mit falschem Token: `401`.
- `GET /api/export/trades` - CSV-Export aller ECHTEN Trades (`dry_run: false`)
  aus allen drei Bots, chronologisch sortiert, als Download
  (`Content-Disposition: attachment`). Gleiche Token-Authentifizierung wie
  `/api/status`. Enthält am Ende einen `#`-Kommentarblock mit Hinweisen
  (Beträge in USDT, keine Euro-Umrechnung, kein Steuerberatungs-Ersatz) -
  gedacht als Rohdaten-Vorbereitung für einen Steuerberater, keine
  fertige Steuerauswertung.
  Optionaler Parameter `?period=week|month|year|all` (Default `all`)
  filtert nach Kauf- bzw. Verkaufs-Zeitpunkt der jeweiligen Zeile - eine
  Position, die vor dem Zeitraum eröffnet und erst darin verkauft wurde,
  zeigt dann nur die Verkaufs-Zeile. Ein ungültiger Wert liefert `400`.

### Tests

```bash
cd backend
pytest
```

## Frontend

Kein Build-Schritt, kein eigener Server - `frontend/` wird von der
FastAPI-Instanz direkt mit ausgeliefert (siehe oben).

Token und (optionale) Backend-URL werden im LocalStorage des Browsers
gespeichert; über das Zahnrad-Icon oben rechts lassen sie sich später
ändern. Die Backend-URL wird nur gebraucht, wenn das Frontend doch einmal
von einer anderen Adresse aus läuft als die API - dafür bleibt das
CORS-Setup (`CORS_ORIGINS`) erhalten.

Das Dashboard aktualisiert sich automatisch alle 45 Sekunden und zeigt bei
falschem Token oder nicht erreichbarem Backend eine klare Fehlermeldung.

Der Button "Export für Steuerberater (CSV)" lädt `/api/export/trades`
herunter (normaler Browser-Download, keine Vorschau im Frontend).

### "Zum Startbildschirm hinzufügen" (Android)

Die Seite bringt ein `manifest.json` mit (PWA-light, ohne Service Worker).
Im mobilen Chrome über das Menü "Zum Startbildschirm hinzufügen" wählen,
sobald das Dashboard über eine echte URL erreichbar ist (z.B. über den
Cloudflare Tunnel).

## Später auf dem Homeserver

1. Den einen Prozess mit echtem `DASHBOARD_TOKEN` und `DATA_DIR` (Pfad zum
   `data/`-Ordner des Bots) starten, z.B. via systemd-Service oder
   `pm2`/`supervisor`. Er liefert API und Frontend gemeinsam aus - ein
   zweiter Webserver für die statischen Dateien ist nicht nötig.
2. Cloudflare Tunnel auf genau diesen einen Port zeigen lassen.
3. `CORS_ORIGINS` kann auf `*` bleiben, solange alles über dieselbe
   Adresse läuft (der Browser schickt dann gar keine CORS-Anfragen). Nur
   falls das Frontend doch von einer anderen Domain aus genutzt wird,
   dort die konkrete URL eintragen.
