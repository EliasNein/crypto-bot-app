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

## Backend lokal starten

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

uvicorn app.main:app --reload --port 8123
```

Ohne `DATA_DIR`-Angabe liest das Backend automatisch aus `../data`
(die mitgelieferten Beispieldateien). Für den echten Server: `DATA_DIR`
auf den `data/`-Ordner des Bots setzen.

Endpunkte:
- `GET /health` - kein Token nötig, liefert `{"status": "ok"}`.
- `GET /api/status` - Token per Header `X-Dashboard-Token: <token>` oder
  Query-Parameter `?token=<token>`. Ohne/mit falschem Token: `401`.

### Tests

```bash
cd backend
pytest
```

## Frontend lokal starten

Kein Build-Schritt nötig. Beliebigen statischen Server im `frontend/`-Ordner
starten, z.B.:

```bash
cd frontend
python -m http.server 5500
```

Dann `http://localhost:5500` im Browser öffnen. Beim ersten Laden nach
Token fragen lassen - das Token aus der Backend-`.env` eingeben. Läuft das
Backend nicht auf derselben Adresse wie das Frontend, zusätzlich die
Backend-URL angeben (z.B. `http://localhost:8123`). Beides wird im
LocalStorage des Browsers gespeichert; über das Zahnrad-Icon oben rechts
lässt es sich später ändern.

Das Dashboard aktualisiert sich automatisch alle 45 Sekunden und zeigt bei
falschem Token oder nicht erreichbarem Backend eine klare Fehlermeldung.

### "Zum Startbildschirm hinzufügen" (Android)

Die Seite bringt ein `manifest.json` mit (PWA-light, ohne Service Worker).
Im mobilen Chrome über das Menü "Zum Startbildschirm hinzufügen" wählen,
sobald das Dashboard über eine echte URL erreichbar ist (z.B. über den
Cloudflare Tunnel).

## Später auf dem Homeserver

1. Backend mit echtem `DASHBOARD_TOKEN` und `DATA_DIR` (Pfad zum
   `data/`-Ordner des Bots) starten, z.B. via systemd-Service oder
   `pm2`/`supervisor`.
2. Frontend-Ordner von einem beliebigen Webserver ausliefern (nginx,
   Caddy, oder einfach `python -m http.server`).
3. Cloudflare Tunnel auf den Port des Frontends (und ggf. separat auf das
   Backend, falls Frontend und Backend nicht denselben Host/Port teilen)
   zeigen lassen.
4. `CORS_ORIGINS` in der Backend-`.env` auf die tatsächliche Frontend-URL
   einschränken, sobald die feststeht (statt `*`).
