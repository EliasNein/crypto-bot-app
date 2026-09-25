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
# dann DASHBOARD_TOKEN in .env auf einen eigenen Wert setzen:
#   openssl rand -hex 32
# Mindestens 32 Zeichen, keine Platzhalter - sonst verweigert der Server
# den Dienst (siehe "Sicherheit").

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
- `GET /api/status` - Token per Header `X-Dashboard-Token: <token>`.
  Ohne/mit falschem Token: `401`. Ein `?token=`-Query-Parameter wird
  bewusst **nicht** akzeptiert (siehe "Sicherheit").
  Antwort: je ein Block für `dca`, `grid`, `trend` und `allocator`, dazu
  `overview` (Gesamtgewinn/-verlust, unrealisierter Bestand) sowie die
  beiden unten beschriebenen Felder `investment_activity` und
  `pnl_verlauf`.
- `GET /api/export/trades` - CSV-Export aller ECHTEN Trades (`dry_run: false`)
  aus allen drei Bots, chronologisch sortiert, als Download
  (`Content-Disposition: attachment`). Gleiche Header-Authentifizierung wie
  `/api/status`. Enthält am Ende einen `#`-Kommentarblock mit Hinweisen
  (Beträge in USDT, keine Euro-Umrechnung, kein Steuerberatungs-Ersatz) -
  gedacht als Rohdaten-Vorbereitung für einen Steuerberater, keine
  fertige Steuerauswertung.
  Optionaler Parameter `?period=week|month|year|all` (Default `all`)
  filtert nach Kauf- bzw. Verkaufs-Zeitpunkt der jeweiligen Zeile - eine
  Position, die vor dem Zeitraum eröffnet und erst darin verkauft wurde,
  zeigt dann nur die Verkaufs-Zeile. Ein ungültiger Wert liefert `400`.

### `investment_activity` - an wie vielen Tagen wurde überhaupt investiert?

Skaliert der Allocator den DCA-Betrag unter das Mindestvolumen und hat der
Trend-Bot am selben Tag kein bestätigtes Signal, kauft das System an diesem
Tag gar nichts. Diese Tage sind sonst nirgends sichtbar.

```json
"investment_activity": {
  "status": "ok",
  "total_days_tracked": 20,
  "days_with_activity": 10,
  "days_without_activity": 10,
  "days_without_activity_pct": 50.0,
  "days_with_dry_run_activity": 2,
  "today_has_activity": false
}
```

- Ein Tag gilt als aktiv, wenn **mindestens einer der drei Bots** an ihm
  einen echten (`dry_run: false`) Kauf/Einstieg getätigt hat. Maßgeblich
  sind `timestamp` (DCA), `bought_at` (Grid) und `entry_time` (Trend).
- Das Fenster ist `[erster echter Kauftag … gestern]`, Tagesgrenze **UTC**.
  Der **heutige Tag bleibt draußen**: er ist noch nicht vorbei, ein Kauf
  könnte folgen. Würde er mitgezählt, startete jeder Tag um 00:00 UTC
  zwangsläufig als "ohne Aktivität" und die Quote schwankte im Tagesverlauf.
  `today_has_activity` weist den heutigen Stand rein informativ aus.
- `days_with_dry_run_activity` zählt Tage mit simuliertem Kauf über die
  **gesamte** Historie (bis gestern), unabhängig vom Fenster der echten
  Metrik - sonst wäre die Paper-Trade-Phase unsichtbar, solange es noch
  keinen einzigen echten Kauf gibt.
- `status: "no_data"` (und `days_without_activity_pct: null`), solange es
  keinen abgeschlossenen Tag mit echtem Kauf gibt - keine Division durch 0.

> **Interpretationsgrenze:** Das Ledger enthält kein Signal dafür, ob der
> Bot lief. Ein Tag ohne Kauf kann "Allocator heruntergefahren und kein
> Trend-Signal" bedeuten - oder schlicht "Bot war aus / Server neu
> gestartet". Beides sieht in den Daten identisch aus. Das Frontend weist
> ausdrücklich darauf hin; ohne diese Einschränkung ist die Zahl **kein
> Fehlerbericht**.

### `pnl_verlauf` - realisierte PnL über die Zeit

```json
"pnl_verlauf": [
  {"datum": "2026-09-07", "realisierte_pnl_an_diesem_tag": 2.4, "kumulierte_pnl_bis_zu_diesem_tag": 2.4},
  {"datum": "2026-09-10", "realisierte_pnl_an_diesem_tag": 1.1, "kumulierte_pnl_bis_zu_diesem_tag": 3.5}
]
```

- Gruppiert nach **Verkaufs-/Ausstiegstag** (`sold_at` bzw. `exit_time`,
  UTC) - erst dort entsteht ein realisierter Gewinn oder Verlust.
- Nur echte (`dry_run: false`), geschlossene Grid- und Trend-Positionen.
  DCA fehlt zwangsläufig: der Bot verkauft nie und führt kein
  `realized_pnl`.
- Tage ohne Abschluss bekommen **keinen** Eintrag; die Liste hat bewusst
  Lücken. Das Frontend zeichnet deshalb eine Stufenkurve - die kumulierte
  Summe ändert sich nur an Abschlusstagen und bleibt dazwischen konstant.
- Leere Liste, solange nichts Echtes abgeschlossen wurde.

### `heartbeat` - läuft der jeweilige Bot-Prozess noch?

Der Bot schreibt je Prozess eine Datei `heartbeat_{dca,grid,trend,allocator}.json`
in dasselbe `DATA_DIR` wie die Ledger.

```json
"heartbeat": {
  "grid": {
    "status": "ok" | "warn" | "no_data",
    "reason": null | "consecutive_failures" | "stale_success" | "no_confirmed_success",
    "last_successful_cycle": "2026-09-25T11:55:00+00:00",
    "last_cycle_attempt": "2026-09-25T11:59:00+00:00",
    "consecutive_failures": 0,
    "seconds_since_success": 300.4,
    "seconds_since_attempt": 60.4
  }
}
```

- Der Rohinhalt der Datei wird unverändert durchgereicht - auch ein
  unsinniger Wert bleibt sichtbar, statt still zu einem Default zu werden.
- **Die Altersangaben rechnet der Server**, nicht der Browser: Die Dateien
  entstehen auf derselben Maschine, die die API bedient, damit ist die
  Differenz frei von Uhren-Versatz. Eine falsch gehende Handy-Uhr würde
  ausgerechnet bei einer Lebendigkeits-Anzeige Stillstand behaupten, wo
  keiner ist.
- Fehlende oder kaputte Datei → `no_data` für **diesen** Bot, ohne die
  anderen drei zu beeinträchtigen, und **ohne Warnung**: ein älteres
  crypto-bot-Deployment kennt das Feature schlicht noch nicht.

**Warum es keine bot-spezifischen Intervall-Schwellen gibt.** Die
erwarteten Zyklus-Takte (DCA/Trend typischerweise 24h, Grid 5min,
Allocator 60min) stehen auf Bot-Seite und sind dort konfigurierbar -
diese App erführe eine Änderung nie. Eine geratene „müsste längst wieder
gelaufen sein"-Schwelle würde deshalb entweder Fehlalarme erzeugen oder
einen echten Ausfall verschweigen. Gewarnt wird nur anhand von zwei
robusten, bot-unabhängigen Signalen:

| Lage | Status | `reason` |
|---|---|---|
| `consecutive_failures > 0` (der Bot meldet es selbst) | `warn` | `consecutive_failures` |
| Bestätigte Erfolgsmeldung älter als **48 h** | `warn` | `stale_success` |
| Noch keine bestätigte Erfolgsmeldung, aber auch kein Fehlschlag | `ok` | `no_confirmed_success` |
| Sonst | `ok` | `null` |

Der dritte Fall ist bewusst **keine** Warnung: Die Werte gelten nur für
den aktuell laufenden Prozess, nach einem Neustart beginnt die Zählung
bei 0. Bei einem 24h-Takt ist „noch kein erfolgreicher Zyklus" damit
einen ganzen Tag lang der Normalzustand. Das Frontend benennt ihn
sachlich („Noch kein erfolgreicher Zyklus seit Prozessstart"), statt eine
Dauer zu behaupten, die es nicht gibt.

### Tests

```bash
cd backend
pytest
```

Zusätzlich gibt es Browser-Tests für den Login-/Reload-Ablauf des
Frontends (`tests/test_frontend_login_flow.py`). Die brauchen Playwright
und überspringen sich sonst automatisch:

```bash
pip install -r requirements-dev.txt
python -m playwright install chromium
pytest                      # führt die Browser-Tests jetzt mit aus
```

Sie starten einen echten uvicorn-Prozess und steuern einen echten
Browser - die Sichtbarkeit des Login-Overlays hängt an einer CSS-Klasse
und ist in einem DOM-Stub nicht zuverlässig prüfbar.

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

## Sicherheit

Was die App selbst durchsetzt:

- **Token nur im Header.** `?token=` wird nicht akzeptiert. Query-Strings
  landen im uvicorn-Access-Log, in der Browser-History und in den
  Request-Logs von Cloudflare - ein Header tut das nicht. Der
  CSV-Download im Frontend läuft deshalb über `fetch` + Blob statt über
  eine Navigation zur Export-URL.
- **Mindest-Entropie erzwungen.** Tokens unter 32 Zeichen oder typische
  Platzhalter werden abgewiesen (HTTP 500, Hinweis im Server-Log). Es
  gibt bewusst keine Rate-Limitierung: bei einem Token aus
  `openssl rand -hex 32` (256 Bit) ist Brute-Force aussichtslos, bei
  einem schwachen Token würde auch ein Limit nicht helfen. Die Entropie
  ist die Schutzschicht, deshalb wird sie erzwungen statt empfohlen.
- **Konstanter Zeitvergleich** über `secrets.compare_digest`.
- **Fehlgeschlagene Zugriffe werden geloggt** (Pfad + Client-IP, hinter
  Cloudflare aus `CF-Connecting-IP`). Das übermittelte Token wird dabei
  nie mitgeloggt.
- **Access-Logs werden gefiltert.** uvicorn loggt die angefragte URL
  auch bei abgelehnten Requests - ein alter Bookmark mit `?token=...`
  würde das Token sonst trotz `401` ins Log schreiben. Sensible
  Parameterwerte werden deshalb durch `REDACTED` ersetzt
  (`app/access_log.py`), harmlose wie `period=year` bleiben lesbar.
- **Keine öffentliche API-Doku.** `/docs`, `/redoc` und `/openapi.json`
  sind abgeschaltet.
- **CORS standardmäßig geschlossen** (siehe `CORS_ORIGINS`).
- **Kein Trading möglich.** Das Backend importiert keinen Binance-Client
  und überhaupt keine HTTP-Client-Bibliothek, kennt die API-Keys des Bots
  nicht und schreibt nirgendwo hin - es gibt nur `json.load`. Das
  schlimmstmögliche Ergebnis eines geleakten Tokens ist das *Lesen* der
  Ledger-Daten.

## Später auf dem Homeserver

1. Den einen Prozess mit echtem `DASHBOARD_TOKEN` und `DATA_DIR` (Pfad zum
   `data/`-Ordner des Bots) starten, z.B. via systemd-Service oder
   `pm2`/`supervisor`. Er liefert API und Frontend gemeinsam aus - ein
   zweiter Webserver für die statischen Dateien ist nicht nötig.
   **Ohne `--reload`** (das ist nur fürs lokale Entwickeln) und **ohne
   `--host 0.0.0.0`**: auf `127.0.0.1` gebunden ist der Tunnel der
   einzige Weg hinein, sonst hängt das Dashboard zusätzlich offen im
   Heimnetz.
2. Cloudflare Tunnel auf genau diesen einen Port zeigen lassen.
3. **Cloudflare Access (Zero Trust) davorschalten.** Das ist die
   wirksamste Einzelmaßnahme: die App ist dann für das offene Internet
   gar nicht erreichbar, sondern erst nach Anmeldung. Ein geleaktes
   Token allein genügt dann nicht mehr.
4. In Cloudflare **"Always Use HTTPS"** aktivieren. Der lokale
   HTTP-Listener ist unkritisch, weil der Klartext-Hop auf `localhost`
   bleibt - `cloudflared` verbindet sich ausgehend per TLS.
5. `CORS_ORIGINS` leer lassen, solange alles über dieselbe Adresse läuft.
   Nur falls das Frontend bewusst von einer anderen Domain kommt, dort
   die konkrete URL eintragen.

Bekannte, bewusst offene Punkte: keine Security-Header (CSP etc.) - die
lassen sich bei Bedarf in Cloudflare setzen; und Werte aus den
Ledger-Dateien werden im CSV-Export nicht gegen Excel-Formeln
entschärft (nicht über das Netz erreichbar, setzt Schreibzugriff auf den
Homeserver voraus).
