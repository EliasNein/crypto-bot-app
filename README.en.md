# Trading Bot Dashboard

> English translation of `README.md`, kept in sync with it (every change
> lands in both files in the same commit). If they ever differ, the German
> original is authoritative. API field names, CSV columns and UI texts
> (e.g. `gesamtgewinn`, `waehrung`, „Noch kein realisiertes Ergebnis“) are
> quoted exactly as the code emits them, i.e. in German. Dates use the
> original DD.MM.YYYY format.

Read-only, mobile-optimised web dashboard for displaying the stats of the
trading bot (DCA, Grid, Trend, Allocator): current positions, total
profit/loss, PnL history, liveness of the bot processes and a trade export
for the tax return.

**Isolation principle:** This app is a completely independent project.
It only reads the bot's four ledger files (`trade_ledger.json`,
`grid_positions.json`, `trend_ledger.json`, `allocator_state.json`) via
`json.load()`, never changes anything there, imports no code from the bot
project, has no access to its `.env`/API keys and contains no Binance
connection whatsoever. Triggering a trade is structurally impossible with
this code.

Deutsche Version: [README.md](README.md)

## Bot project

The trading bots themselves, which write the ledger files displayed here,
live in their own repository:
[crypto-dca-bot](https://github.com/EliasNein/crypto-dca-bot).

The app only depends on the ledger file format, not on the bot's code -
where a change there has to be followed up here is stated in the
respective section (e.g. 6.2 "Dependency on the bot repo").

## 1. Prerequisites

- Python 3.10+
- For the browser tests additionally Playwright with Chromium (see 10)
- For access from outside: a Cloudflare Tunnel (see 9)

## 2. Installation

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/Mac
pip install -r requirements.txt
```

The versions in `requirements.txt` are pinned exactly so that the home
server gets the same versions as were tested locally.

## 3. Configuration

```bash
copy .env.example .env        # Windows
# cp .env.example .env        # Linux/Mac
```

| Variable | Required | Meaning |
|---|---|---|
| `DASHBOARD_TOKEN` | yes | Secret token that the frontend sends as the `X-Dashboard-Token` header. At least 32 characters, no placeholders - otherwise the server refuses service (see 8). Generate with `openssl rand -hex 32`. |
| `DATA_DIR` | no | Folder containing the ledger files. If unset, the backend reads from `../data` (the bundled sample files). For the real server: the bot's `data/` folder. |
| `CORS_ORIGINS` | no | Allowed foreign origins, comma-separated. **Leaving it empty** is the normal case, because frontend and API are served from the same address. |

Instead of in `.env`, all three can also be set as environment variables.

## 4. Starting (backend + frontend in one process)

The FastAPI instance serves both: the API endpoints **and** the frontend
(`frontend/` is mounted under `/`). So only one process on one port is
needed, no separate web server for the static files.

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

Then open `http://localhost:8000/` in the browser - that is the dashboard.
On first load, let it ask for the token (the one from `.env`); leave the
"Backend-URL" field **empty**, because API and frontend come from the
same address.

`--reload` is only meant for local development; leave it out on the
server (see 9).

## 5. Project structure

```
Trading-Bot-App/
├── backend/
│   ├── app/
│   │   ├── main.py           # FastAPI app: endpoints, frontend mount, CORS
│   │   ├── auth.py           # Token check (header, minimum entropy, constant-time compare)
│   │   ├── ledger_readers.py # Reads the ledgers, computes cards, overview, histories
│   │   ├── currency.py       # Currency per entry + sums per currency (single home of the rule)
│   │   ├── export.py         # CSV export of the real trades
│   │   └── access_log.py     # Filters secrets out of the uvicorn access log
│   ├── tests/                # pytest suite incl. browser tests (see 10)
│   ├── requirements.txt      # Runtime dependencies (pinned)
│   ├── requirements-dev.txt  # Additionally: Playwright for the browser tests
│   ├── pytest.ini
│   └── .env.example
├── frontend/                 # Static HTML/CSS/JS without a build step
│   ├── index.html
│   ├── app.js
│   ├── style.css
│   ├── manifest.json         # PWA-light for "Add to Home screen"
│   └── icons/
├── data/                     # Sample JSON files for local development
├── README.md
└── README.en.md
```

## 6. API

### 6.1 Endpoints

- `GET /health` - no token needed, returns `{"status": "ok"}`.
- `GET /api/status` - token via header `X-Dashboard-Token: <token>`.
  Without/with a wrong token: `401`. A `?token=` query parameter is
  deliberately **not** accepted (see 8).
  Response: one block each for `dca`, `grid`, `trend` and `allocator`,
  plus `overview` (total profit/loss, unrealised holdings) and the fields
  `investment_activity`, `pnl_verlauf` and `heartbeat` described below.
  All monetary amounts come **per currency** - see 6.2.
- `GET /api/export/trades` - CSV export of all REAL trades (`dry_run: false`)
  from all three bots, sorted chronologically, as a download
  (`Content-Disposition: attachment`). Same header authentication as
  `/api/status`. Columns: `datum_zeit_utc, bot, symbol, waehrung, seite,
  menge_btc, preis, betrag, realisierter_pnl, position_id` - `symbol` and
  `waehrung` are taken per row from the ledger entry. At the end there is
  a `#` comment block that states **for each currency that occurs**
  whether a conversion to euros is needed for tax purposes (EUR: no;
  USDT/USDC: yes, the CSV does not convert), plus export time, period and
  "no tax advice" - intended as raw-data preparation for a tax advisor,
  not a finished tax evaluation.
  **Note, renamed columns (29.09.2026):** Until then the amount columns
  were called `preis_usdt`, `betrag_usdt` and `realisierter_pnl_usdt`,
  and there was no `waehrung` column. Excel templates or formulas that
  refer to the old names or column positions must be adjusted.
  Optional parameter `?period=week|month|year|all` (default `all`)
  filters by the buy or sell time of each row - a position opened before
  the period and only sold within it then shows only the sell row. An
  invalid value returns `400`.

### 6.2 Currencies - never added across currency boundaries

Binance has removed the USDT spot pairs for customers in the EEA; for real
money the bot switches from BTCUSDT to BTCEUR. Afterwards the same ledgers
contain amounts in two currencies. A sum over both would be a number in no
currency - and would still look plausible, because EUR and USD are close
to each other. That is why **every** monetary amount is kept per currency
(`app/currency.py` is the only place containing the rule).

**Which currency does an entry have?**

| Field `symbol` in the ledger | Result |
|---|---|
| missing or `null` | `BTCUSDT` → USDT (legacy entries, see below) |
| `BTCUSDT` / `BTCUSDC` / `BTCEUR` (surrounding whitespace ignored) | USDT / USDC / EUR |
| anything else (empty, number, `ETHEUR`, `BTCXYZ`, ...) | **undeterminable** |

- **Legacy entries = BTCUSDT.** Grid and trend entries only carry their
  own `symbol` since the "symbol binding" in crypto-bot (commits
  `e2a37bd`-`9ef7d60`, deployed with state `980f3c3` on 29.09.2026); older
  entries are not stamped retroactively. The bot reads a missing and a
  `null` field as BTCUSDT (decision E1, `symbol_guard.effective_symbol`)
  - this app adopts **exactly the same rule**, so that both repos classify
  legacy entries identically. DCA entries have always had `symbol`.
- **Only BTC as base, only USDT/USDC/EUR as quote.** Quantities are shown
  in BTC; another pair would otherwise silently add its quantity to the
  BTC sums. Adding another quote is one line in `QUOTES`.
- **Safety net.** A real entry with an undeterminable currency flows into
  **no** sum - neither as USDT nor as EUR -, but stays visible in the
  position lists and is counted (`unknown_currency` per card,
  `ohne_waehrung` in `overview`). The frontend then shows an amber line in
  the result block and in the card footer; the export keeps the row (empty
  `waehrung`) and warns in the comment block. On the bot side, a startup
  check prevents a foreign pair from getting into the ledger at all - so
  this case is an anomaly, but if it happens it should stand out.

**Dependency on the bot repo:** The rule above assumes that the bot writes
`symbol` into every new grid/trend entry and leaves old entries untouched
(both the case since the symbol binding). If the reading rule for legacy
entries changes there, `currency.py` has to follow.

**API structure (example after a switch):**

```jsonc
"overview": {
  "gesamtgewinn":  {"EUR": 1.2, "USDT": 5.0},   // always the same keys
  "gesamtverlust": {"EUR": -3.0, "USDT": 0.0},  // as gesamtgewinn
  "unrealisiert_geschätzt": {
    "dca":  {"EUR": {"quantity": 0.0002, "avg_price": 65000.0},
             "USDT": {"quantity": 0.0002, "avg_price": 75000.0}},
    "grid": {},       // valid file, no open holdings
    "trend": null,    // file missing/broken
    "hinweis": "..."
  },
  "waehrungen": ["EUR", "USDT"],    // most recent real activity first
  "ohne_waehrung": {"dca": 0, "grid": 0, "trend": 0}
}
```

- Card metrics: `dca.metrics.total_spent` and `avg_entry_price` as well as
  `grid`/`trend.metrics.realized_pnl` are dicts `{currency: value}`; empty
  (`{}`) when there is nothing to sum. `total_quantity` (BTC) remains a
  number. Every position in `open_positions` carries `symbol` and
  `waehrung` (`null` = undeterminable).
- "Nothing realised yet" is an empty `gesamtgewinn`, not `0` - a currency
  with a closed trade at a PnL of exactly 0 appears in it with `0.0`.

**Display.** With only one currency - the normal case - the dashboard
looks as before; the unit comes from the data instead of being a fixed
"USDT". With several currencies, the **main currency** (`waehrungen[0]`)
gets the large net figure, the breakdown and the chart; older results are
shown small underneath ("zusätzlich +4,00 USDT aus der Zeit vor dem
Wechsel" - "additionally +4.00 USDT from the time before the switch"). If
the main currency has no result yet, it says in large type "Noch kein
realisiertes Ergebnis in EUR" ("No realised result in EUR yet"). The
chart only shows the main currency: green/red already carries the meaning
plus/minus there, a second line would need another colour, and two units
on one axis would look comparable without being so. Cards show one line
per currency; with several currencies, position rows get the unit
appended.

### 6.3 `investment_activity` - on how many days was anything invested at all?

If the allocator scales the DCA amount below the minimum volume and the
trend bot has no confirmed signal on the same day, the system buys nothing
at all that day. These days are not visible anywhere else.

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

- A day counts as active if **at least one of the three bots** made a
  real (`dry_run: false`) purchase/entry on it. The relevant fields are
  `timestamp` (DCA), `bought_at` (Grid) and `entry_time` (Trend).
- The window is `[first real purchase day … yesterday]`, day boundary
  **UTC**. **Today is left out**: it is not over yet, a purchase could
  still follow. If it were counted, every day would inevitably start at
  00:00 UTC as "without activity" and the ratio would fluctuate over the
  course of the day. `today_has_activity` reports today's state purely for
  information.
- `days_with_dry_run_activity` counts days with a simulated purchase over
  the **entire** history (up to yesterday), independent of the window of
  the real metric - otherwise the paper-trading phase would be invisible
  as long as there is not a single real purchase yet.
- `status: "no_data"` (and `days_without_activity_pct: null`) as long as
  there is no completed day with a real purchase - no division by 0.

> **Limit of interpretation:** The ledger contains no signal as to whether
> the bot was running. A day without a purchase can mean "allocator scaled
> down and no trend signal" - or simply "bot was off / server restarted".
> Both look identical in the data. The frontend points this out
> explicitly; without this caveat the number is **not an error report**.

### 6.4 `pnl_verlauf` - realised PnL over time

```json
"pnl_verlauf": {
  "USDT": [
    {"datum": "2026-09-07", "realisierte_pnl_an_diesem_tag": 2.4, "kumulierte_pnl_bis_zu_diesem_tag": 2.4},
    {"datum": "2026-09-10", "realisierte_pnl_an_diesem_tag": 1.1, "kumulierte_pnl_bis_zu_diesem_tag": 3.5}
  ]
}
```

- **A separate history per currency** with its own accumulation (see 6.2)
  - two closed trades on the same day in USDT and EUR end up in two lists,
  not in one daily sum.
- Grouped by **sell/exit day** (`sold_at` or `exit_time`, UTC) - only
  there does a realised profit or loss arise.
- Only real (`dry_run: false`), closed grid and trend positions. DCA is
  necessarily missing: the bot never sells and keeps no `realized_pnl`.
- Days without a closed trade get **no** entry; the list deliberately has
  gaps. The frontend therefore draws a step curve - the cumulative sum
  only changes on closing days and stays constant in between.
- Empty object `{}` as long as nothing real has been closed.

### 6.5 `heartbeat` - is each bot process still running?

The bot writes one file `heartbeat_{dca,grid,trend,allocator}.json` per
process into the same `DATA_DIR` as the ledgers.

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

- The raw content of the file is passed through unchanged - even a
  nonsensical value stays visible instead of silently becoming a default.
- **The ages are computed by the server**, not the browser: the files are
  created on the same machine that serves the API, so the difference is
  free of clock skew. A phone clock running wrong would, of all things in
  a liveness display, claim a standstill where there is none.
- Missing or broken file → `no_data` for **this** bot, without affecting
  the other three, and **without a warning**: an older crypto-bot
  deployment simply does not know the feature yet.

**Why there are no bot-specific interval thresholds.** The expected cycle
intervals (DCA/Trend typically 24h, Grid 5min, Allocator 60min) live on
the bot side and are configurable there - this app would never learn
about a change. A guessed "should have run again long ago" threshold
would therefore either produce false alarms or hide a real outage.
Warnings are based only on two robust, bot-independent signals:

| Situation | Status | `reason` |
|---|---|---|
| `consecutive_failures > 0` (reported by the bot itself) | `warn` | `consecutive_failures` |
| Confirmed success report older than **48 h** | `warn` | `stale_success` |
| No confirmed success report yet, but no failure either | `ok` | `no_confirmed_success` |
| Otherwise | `ok` | `null` |

The third case is deliberately **not** a warning: the values only apply
to the currently running process, and after a restart the count starts at
0. With a 24h interval, "no successful cycle yet" is thus the normal state
for a whole day. The frontend names it matter-of-factly ("Noch kein
erfolgreicher Zyklus seit Prozessstart" - "No successful cycle since
process start yet") instead of claiming a duration that does not exist.

## 7. Frontend

No build step, no server of its own - `frontend/` is served directly by
the FastAPI instance (see 4).

Token and (optional) backend URL are stored in the browser's
LocalStorage; they can be changed later via the gear icon in the top
right. The backend URL is only needed if the frontend does run from a
different address than the API after all - that is what the CORS setup
(`CORS_ORIGINS`) is kept for.

The dashboard refreshes automatically every 45 seconds and shows a clear
error message if the token is wrong or the backend is unreachable.

The "Export für Steuerberater (CSV)" button ("export for tax advisor")
downloads `/api/export/trades` (normal browser download, no preview in
the frontend).

### 7.1 "Add to Home screen" (Android)

The page ships a `manifest.json` (PWA-light, without a service worker).
In mobile Chrome, choose "Add to Home screen" from the menu once the
dashboard is reachable via a real URL (e.g. via the Cloudflare Tunnel).

### 7.2 Known minor improvements

From the app check of 26.09.2026, deliberately still open:

- **Colour literals instead of tokens** in `style.css`: `#error-banner`,
  `.activity-caveat` and `#login-overlay` use fixed colour values - partly
  variants of existing tokens (`--danger`, `--warn`), partly without a
  variable of their own in `:root`.
- **Dead `--fs-xl`** (`style.css`, `:root`): defined but used nowhere.
- **Box titles as `div`** (`.block-title` in cards and overview boxes)
  instead of real headings - screen readers cannot jump to them.
- **No `aria-live`** for the error banner, login errors and connection
  status - changes are not announced to screen readers.

## 8. Security

What the app enforces itself:

- **Token only in the header.** `?token=` is not accepted. Query strings
  end up in the uvicorn access log, in the browser history and in
  Cloudflare's request logs - a header does not. The CSV download in the
  frontend therefore uses `fetch` + Blob instead of navigating to the
  export URL.
- **Minimum entropy enforced.** Tokens under 32 characters or typical
  placeholders are rejected (HTTP 500, note in the server log). There is
  deliberately no rate limiting: with a token from `openssl rand -hex 32`
  (256 bits) brute force is hopeless, and with a weak token a limit would
  not help either. Entropy is the protective layer, which is why it is
  enforced rather than recommended.
- **Constant-time comparison** via `secrets.compare_digest`.
- **Failed access attempts are logged** (path + client IP, behind
  Cloudflare taken from `CF-Connecting-IP`). The submitted token is never
  logged.
- **Access logs are filtered.** uvicorn logs the requested URL even for
  rejected requests - an old bookmark with `?token=...` would otherwise
  write the token to the log despite the `401`. Sensitive parameter values
  are therefore replaced with `REDACTED` (`app/access_log.py`), harmless
  ones like `period=year` remain readable.
- **No public API docs.** `/docs`, `/redoc` and `/openapi.json` are
  disabled.
- **CORS closed by default** (see `CORS_ORIGINS`).
- **No trading possible.** The backend imports no Binance client and no
  HTTP client library at all, does not know the bot's API keys and writes
  nowhere - there is only `json.load`. The worst possible outcome of a
  leaked token is *reading* the ledger data.

Known, deliberately open points: no security headers (CSP etc.) - they
can be set in Cloudflare if needed; and values from the ledger files are
not neutralised against Excel formulas in the CSV export (not reachable
over the network, requires write access to the home server).

## 9. Running on the home server

1. Start the one process with a real `DASHBOARD_TOKEN` and `DATA_DIR`
   (path to the bot's `data/` folder), e.g. via a systemd service or
   `pm2`/`supervisor`. It serves API and frontend together - a second web
   server for the static files is not needed.
   **Without `--reload`** (that is only for local development) and
   **without `--host 0.0.0.0`**: bound to `127.0.0.1`, the tunnel is the
   only way in; otherwise the dashboard is additionally exposed on the
   home network.
2. Point the Cloudflare Tunnel at exactly this one port.
3. **Put Cloudflare Access (Zero Trust) in front.** This is the most
   effective single measure: the app is then not reachable from the open
   internet at all, only after logging in. A leaked token alone is then
   no longer enough.
4. Enable **"Always Use HTTPS"** in Cloudflare. The local HTTP listener is
   uncritical because the plain-text hop stays on `localhost` -
   `cloudflared` connects outbound via TLS.
5. Leave `CORS_ORIGINS` empty as long as everything runs via the same
   address. Only if the frontend deliberately comes from a different
   domain, enter the specific URL there.

## 10. Tests

```bash
cd backend
pytest
```

There are also browser tests for the frontend. They need Playwright and
skip themselves automatically otherwise:

```bash
pip install -r requirements-dev.txt
python -m playwright install chromium
pytest                      # now also runs the browser tests
```

| Test file | Topic |
|---|---|
| `test_api_auth` | Token check: header, minimum entropy, no `?token=` |
| `test_api_status`, `test_ledger_readers` | `/api/status` and the evaluation of the four ledgers |
| `test_corrupt_values` | Robustness against wrong field types in valid JSON files |
| `test_currency` | Currency rule, sums per currency, legacy entries, safety net |
| `test_export`, `test_api_export` | CSV export per currency, period filter |
| `test_investment_activity` | "Days without a purchase" metric |
| `test_pnl_history` | PnL history per day and cumulative |
| `test_heartbeats` | Heartbeat status of the four bot processes |
| `test_access_log` | Secrets in the access log are replaced |
| `test_frontend_login_flow` | Browser: login/reload flow and login overlay |
| `test_frontend_dashboard` | Browser: result block and position lists |

The browser tests in detail:

- `tests/test_frontend_login_flow.py` - login/reload flow and login
  overlay.
- `tests/test_frontend_dashboard.py` - net result (sum, rounding, colour,
  "Noch kein realisiertes Ergebnis"), position lists (three visible,
  "+1" rule, every position on the page after expanding) and an expanded
  list staying open on refresh. The net result is only computed in the
  frontend; these tests are its only safeguard. The result tests each run
  once with legacy entries (USDT) and once with BTCEUR, so that a
  hard-coded "USDT" stands out; on top come the multi-currency cases: a
  pure EUR ledger without any "USDT" on the page, mixed currencies (never
  added, main currency large), a new currency without a result and the
  amber notice for entries without a determinable currency.

The currency rule itself and the sums per currency (mixed ledger from the
audit, pure EUR ledger, safety net, legacy entries with missing, `null`
and explicit symbol) are checked by `tests/test_currency.py`, the export
per currency by `tests/test_export.py`.

Both browser test files drive a real browser against a real uvicorn
process (fixtures in `tests/conftest.py`) - visibility depends on CSS and
cannot be checked reliably in a DOM stub. The dashboard tests intercept
`/api/status` in the browser and deliver the response that the real
backend produces for the ledger data of the respective test. This way not
every case needs its own server, and the test data cannot silently drift
away from the backend.
