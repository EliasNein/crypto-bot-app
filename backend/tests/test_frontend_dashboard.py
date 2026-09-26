"""Browser-Tests für Ergebnis-Block und Positionslisten (App-Check 26.09.2026, Befund 2).

Warum diese Tests nötig sind:
- Das Netto-Ergebnis, die wichtigste Zahl der Seite, wird NUR im Frontend
  berechnet (renderHero in app.js). Kein Backend-Test deckt es ab.
- Die DCA-Karte zeigte früher nur die fünf neuesten Käufe, ältere
  verschwanden ohne Hinweis. Die Aufklapp-Liste hat das behoben, war aber
  nie automatisch geprüft - ebenso die "+1"-Regel und das Offenhalten
  beim 45-Sekunden-Refresh.

Test-Setup: Ein uvicorn-Prozess (conftest.py) liefert das echte Frontend
aus. Die Antwort auf /api/status fängt Playwright im Browser ab und
ersetzt sie durch das, was das ECHTE Backend für die Ledger-Daten des
jeweiligen Tests liefert (TestClient auf einem temporären DATA_DIR).
So braucht nicht jeder Fall einen eigenen Serverstart, und handgeschriebene
API-Antworten können nicht unbemerkt vom Backend abweichen.

Sichtbarkeit wird mit element.checkVisibility() geprüft: Chromium
versteckt den Inhalt eines geschlossenen <details> über
content-visibility, die einfache Prüfung über display/visibility/Größe
zählt eingeklappte Zeilen fälschlich als sichtbar.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import TOKEN

REFRESH_INTERVAL_MS = 45_000  # wie in app.js


# --- Ledger-Daten ------------------------------------------------------------


def _dca_buy(i: int, dry_run: bool = False) -> dict:
    # Eindeutiger Preis je Kauf (70.001, 70.002, ...), damit jede Zeile auf
    # der Seite einem Ledger-Eintrag zugeordnet werden kann.
    return {"timestamp": f"2026-09-{i:02d}T09:00:00+00:00", "symbol": "BTCUSDT",
            "quote_spent": 15.0, "quantity": 0.0002, "price": 70000.0 + i, "dry_run": dry_run}


def _grid_open(i: int) -> dict:
    return {"id": f"offen-{i}", "level_index": i, "buy_price": 77000.0 + i,
            "target_sell_price": 77300.0 + i, "quantity": 0.0002, "quote_spent": 15.0,
            "bought_at": "2026-09-20T10:00:00+00:00", "dry_run": False, "status": "open",
            "sell_price": None, "sold_at": None, "realized_pnl": None}


def _grid_closed(i: int, pnl: float, dry_run: bool = False) -> dict:
    # Ein Abschluss je Tag, damit der Verlauf mehrere Punkte hat.
    return {"id": f"zu-{i}", "level_index": i, "buy_price": 100.0, "target_sell_price": 105.0,
            "quantity": 0.0002, "quote_spent": 15.0, "bought_at": f"2026-09-{i:02d}T10:00:00+00:00",
            "dry_run": dry_run, "status": "closed", "sell_price": 100.0 + pnl,
            "sold_at": f"2026-09-{i:02d}T15:00:00+00:00", "realized_pnl": pnl}


def _closes(*pnls: float) -> list[dict]:
    return [_grid_closed(i + 1, pnl) for i, pnl in enumerate(pnls)]


def _status_payload(tmp_path, monkeypatch, **files) -> dict:
    """Was das echte Backend für diese Ledger-Daten ausliefern würde."""
    ledgers = {
        "trade_ledger.json": [],
        "grid_positions.json": [],
        "trend_ledger.json": [],
        "allocator_state.json": {"trend_fraction": 0.3, "updated_at": "2026-09-25T00:00:00+00:00"},
    }
    ledgers.update(files)
    for name, data in ledgers.items():
        (tmp_path / name).write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DASHBOARD_TOKEN", TOKEN)

    response = TestClient(app).get("/api/status", headers={"X-Dashboard-Token": TOKEN})
    assert response.status_code == 200
    return response.json()


# --- Browser -----------------------------------------------------------------


def _open_dashboard(page, server: str, payload: dict) -> list[str]:
    """Öffnet das Dashboard mit gespeichertem Token; /api/status liefert
    `payload`. Gibt die Liste der abgefangenen Anfragen zurück - sie
    wächst mit jedem Refresh."""
    requests: list[str] = []

    def fulfill(route):
        requests.append(route.request.url)
        route.fulfill(json=payload)

    page.route("**/api/status", fulfill)
    page.add_init_script(f"localStorage.setItem('dashboard_token', '{TOKEN}')")
    page.goto(server + "/")
    page.wait_for_selector("#cards .card")
    return requests


def _hero(page) -> dict:
    return page.evaluate(
        """() => {
            const block = document.getElementById('hero-block');
            const value = block.querySelector('.hero-value');
            // Farben so auflösen, wie der Browser sie für die Tokens rechnet.
            const resolve = (token) => {
                const probe = document.createElement('span');
                probe.style.color = `var(${token})`;
                block.appendChild(probe);
                const color = getComputedStyle(probe).color;
                probe.remove();
                return color;
            };
            const breakdown = block.querySelector('.hero-breakdown');
            return {
                text: block.innerText,
                value: value ? value.textContent : null,
                classes: value ? [...value.classList] : [],
                color: value ? getComputedStyle(value).color : null,
                breakdown: breakdown ? breakdown.textContent : null,
                empty: block.querySelector('.hero-empty')?.textContent ?? null,
                meta: block.querySelector('.hero-meta')?.textContent ?? null,
                hasChart: !!block.querySelector('.pnl-chart'),
                green: resolve('--accent'),
                red: resolve('--danger'),
                plain: resolve('--text'),
            };
        }"""
    )


def _card(page, title: str) -> dict:
    return page.evaluate(
        """(title) => {
            const card = [...document.querySelectorAll('#cards .card')]
                .find((c) => c.querySelector('.card-header .block-title').textContent === title);
            const rows = [...card.querySelectorAll('.position')];
            const details = card.querySelector('details.positions-more');
            return {
                all: rows.map((r) => r.textContent),
                visible: rows.filter((r) => r.checkVisibility()).map((r) => r.textContent),
                summary: details ? details.querySelector('summary').textContent : null,
                open: details ? details.open : null,
            };
        }""",
        title,
    )


def _toggle(page, title: str) -> None:
    card = page.locator("#cards .card").filter(
        has=page.locator(".card-header .block-title", has_text=title)
    )
    details = card.locator("details.positions-more")
    will_open = not details.evaluate("(d) => d.open")
    details.locator("> summary").click()
    # Das toggle-Event feuert asynchron nach dem Klick. Erst danach stehen
    # Beschriftung und die Erinnerung für den Refresh (offeneListen) fest.
    details.evaluate(
        """(d, willOpen) => new Promise((resolve) => {
            const done = () => d.open === willOpen
                && (d.querySelector('summary').textContent === 'weniger anzeigen') === willOpen;
            if (done()) return resolve();
            d.addEventListener('toggle', () => resolve(), { once: true });
        })""",
        will_open,
    )


# --- Netto-Ergebnis ------------------------------------------------------------


@pytest.mark.parametrize(
    "closes, value, direction, breakdown",
    [
        pytest.param(
            (2.40, 1.10, -5.80, -1.20, 3.75, 2.90),
            "+3,15 USDT", "pos", "Gewinn +10,15 · Verlust −7,00 USDT",
            id="netto-positiv",
        ),
        pytest.param(
            (1.00, -4.25),
            "−3,25 USDT", "neg", "Gewinn +1,00 · Verlust −4,25 USDT",
            id="netto-negativ",
        ),
        pytest.param(
            (5.00, -5.00),
            "±0,00 USDT", None, "Gewinn +5,00 · Verlust −5,00 USDT",
            id="netto-exakt-null",
        ),
    ],
)
def test_net_result_is_sum_of_gain_and_loss(page, server, tmp_path, monkeypatch,
                                            closes, value, direction, breakdown):
    # Ein Dry-Run-Abschluss mit großem Gewinn darf nirgends einfließen.
    payload = _status_payload(
        tmp_path, monkeypatch,
        **{"grid_positions.json": _closes(*closes) + [_grid_closed(28, 999.0, dry_run=True)]},
    )
    _open_dashboard(page, server, payload)
    hero = _hero(page)

    assert hero["value"] == value
    assert hero["breakdown"] == breakdown
    assert "999" not in hero["text"]
    assert hero["hasChart"], "mehrere Abschlusstage, aber kein Verlauf"
    _assert_direction(hero, direction)


def _assert_direction(hero: dict, direction: str | None) -> None:
    """Klasse UND tatsächlich gerenderte Farbe - die Klasse allein bewiese
    nicht, dass die Zahl auch grün/rot erscheint."""
    if direction == "pos":
        assert "pos" in hero["classes"] and "neg" not in hero["classes"]
        assert hero["color"] == hero["green"]
    elif direction == "neg":
        assert "neg" in hero["classes"] and "pos" not in hero["classes"]
        assert hero["color"] == hero["red"]
    else:
        assert "pos" not in hero["classes"] and "neg" not in hero["classes"]
        assert hero["color"] == hero["plain"], "±0,00 darf keine Gewinn-/Verlustfarbe tragen"


@pytest.mark.parametrize(
    "pnl, value, direction, breakdown",
    [
        pytest.param(0.004, "±0,00 USDT", None, "Gewinn 0,00 · Verlust 0,00 USDT", id="plus-0,004"),
        pytest.param(-0.004, "±0,00 USDT", None, "Gewinn 0,00 · Verlust 0,00 USDT", id="minus-0,004"),
        # Der frühere Fehler: +0,005 erschien als "+0,01" in Grün, −0,005 als
        # "±0,00" ohne Farbe (und "Verlust 0,01" ohne Minuszeichen).
        pytest.param(0.005, "+0,01 USDT", "pos", "Gewinn +0,01 · Verlust 0,00 USDT", id="plus-0,005"),
        pytest.param(-0.005, "−0,01 USDT", "neg", "Gewinn 0,00 · Verlust −0,01 USDT", id="minus-0,005"),
        pytest.param(1.345, "+1,35 USDT", "pos", "Gewinn +1,35 · Verlust 0,00 USDT", id="plus-1,345"),
        pytest.param(-1.345, "−1,35 USDT", "neg", "Gewinn 0,00 · Verlust −1,35 USDT", id="minus-1,345"),
    ],
)
def test_net_result_rounding_is_symmetric(page, server, tmp_path, monkeypatch,
                                          pnl, value, direction, breakdown):
    """Ziffern, Vorzeichen und Farbe folgen derselben Rundung - für Gewinn
    und Verlust gleich."""
    payload = _status_payload(tmp_path, monkeypatch, **{"grid_positions.json": _closes(pnl)})
    _open_dashboard(page, server, payload)
    hero = _hero(page)

    assert hero["value"] == value
    assert hero["breakdown"] == breakdown
    _assert_direction(hero, direction)


def test_without_real_trades_no_result_is_claimed(page, server, tmp_path, monkeypatch):
    """"Noch nie gehandelt" ist nicht "genau ausgeglichen" - keine 0,00.
    Der geschlossene Dry-Run-Gewinn darf daran nichts ändern."""
    payload = _status_payload(
        tmp_path, monkeypatch,
        **{
            "trade_ledger.json": [_dca_buy(i, dry_run=True) for i in (1, 2, 3)],
            "grid_positions.json": [_grid_closed(5, 5.0, dry_run=True)],
        },
    )
    _open_dashboard(page, server, payload)
    hero = _hero(page)

    assert hero["empty"] == "Noch kein realisiertes Ergebnis"
    assert hero["value"] is None
    assert "0,00" not in hero["text"]
    assert "5,00" not in hero["text"]
    assert not hero["hasChart"]


def test_single_close_shows_number_without_chart(page, server, tmp_path, monkeypatch):
    payload = _status_payload(tmp_path, monkeypatch, **{"grid_positions.json": _closes(0.62)})
    _open_dashboard(page, server, payload)
    hero = _hero(page)

    assert hero["value"] == "+0,62 USDT"
    # Verlust als "0,00", nicht als "+0,00" oder "−0,00".
    assert hero["breakdown"] == "Gewinn +0,62 · Verlust 0,00 USDT"
    assert hero["meta"] == "Bisher ein einziger Abschlusstag: 01.09."
    assert not hero["hasChart"]
    _assert_direction(hero, "pos")


# --- Positionslisten -------------------------------------------------------------


def _dca_row(i: int) -> str:
    return f"BTCUSDT · {70000 + i:,}".replace(",", ".") + ",00 USDT · 0,00020000"


@pytest.mark.parametrize("count", [5, 8])
def test_long_list_shows_three_and_collapses_the_rest(page, server, tmp_path, monkeypatch, count):
    payload = _status_payload(
        tmp_path, monkeypatch, **{"trade_ledger.json": [_dca_buy(i) for i in range(1, count + 1)]}
    )
    _open_dashboard(page, server, payload)
    card = _card(page, "DCA-Bot")

    # Neueste zuerst, genau drei sichtbar.
    assert card["visible"] == [_dca_row(i) for i in (count, count - 1, count - 2)]
    assert card["summary"] == f"+{count - 3} weitere anzeigen"
    assert card["open"] is False
    # Eingeklappt heißt nicht abgeschnitten: alle Zeilen stehen im Dokument.
    assert len(card["all"]) == count


def test_exactly_four_positions_are_not_collapsed(page, server, tmp_path, monkeypatch):
    """"+1 weitere anzeigen" bräuchte so viel Platz wie die Zeile selbst."""
    payload = _status_payload(
        tmp_path, monkeypatch, **{"trade_ledger.json": [_dca_buy(i) for i in range(1, 5)]}
    )
    _open_dashboard(page, server, payload)
    card = _card(page, "DCA-Bot")

    assert card["summary"] is None
    assert card["visible"] == [_dca_row(i) for i in (4, 3, 2, 1)]


def test_expanding_shows_every_position_nothing_is_truncated(page, server, tmp_path, monkeypatch):
    """Regressionstest für das stille Abschneiden: früher standen nur die
    fünf neuesten DCA-Käufe auf der Seite."""
    payload = _status_payload(
        tmp_path, monkeypatch, **{"trade_ledger.json": [_dca_buy(i) for i in range(1, 9)]}
    )
    assert len(payload["dca"]["open_positions"]) == 8
    _open_dashboard(page, server, payload)

    _toggle(page, "DCA-Bot")
    card = _card(page, "DCA-Bot")

    assert card["open"] is True
    assert card["summary"] == "weniger anzeigen"
    # Jeder Kauf aus der API steht genau einmal sichtbar auf der Seite.
    assert card["visible"] == [_dca_row(i) for i in range(8, 0, -1)]


def test_expanded_list_stays_open_across_refresh(page, server, tmp_path, monkeypatch):
    """Das Dashboard baut alle Karten beim 45-s-Refresh neu auf. Eine
    aufgeklappte Liste darf dabei nicht von selbst zuklappen - und eine
    andere Liste darf nicht mit aufgehen."""
    payload = _status_payload(
        tmp_path, monkeypatch,
        **{
            "trade_ledger.json": [_dca_buy(i) for i in range(1, 9)],
            "grid_positions.json": [_grid_open(i) for i in range(6)],
        },
    )
    page.clock.install()  # vor dem Laden, damit setInterval unter Testkontrolle steht
    requests = _open_dashboard(page, server, payload)

    def refresh() -> None:
        # Alte Karten markieren; neu gerendert ist erst, wenn keine Markierung mehr existiert.
        before = len(requests)
        page.evaluate("() => document.querySelectorAll('#cards .card').forEach((c) => c.dataset.alt = '1')")
        page.clock.fast_forward(REFRESH_INTERVAL_MS)
        page.wait_for_function(
            "() => document.querySelector('#cards .card') && !document.querySelector('#cards .card[data-alt]')"
        )
        assert len(requests) == before + 1, "Refresh hat /api/status nicht erneut abgefragt"

    _toggle(page, "DCA-Bot")
    refresh()

    dca = _card(page, "DCA-Bot")
    assert dca["open"] is True, "aufgeklappte Liste ist beim Refresh zugeklappt"
    assert dca["summary"] == "weniger anzeigen"
    assert len(dca["visible"]) == 8
    grid = _card(page, "Grid-Bot")
    assert grid["open"] is False, "Grid-Liste wurde ungefragt mit aufgeklappt"
    assert len(grid["visible"]) == 3

    # Gegenrichtung: wieder zugeklappt bleibt ebenfalls zu.
    _toggle(page, "DCA-Bot")
    refresh()

    dca = _card(page, "DCA-Bot")
    assert dca["open"] is False
    assert dca["summary"] == "+5 weitere anzeigen"
    assert len(dca["visible"]) == 3
