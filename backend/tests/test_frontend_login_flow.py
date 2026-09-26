"""Browser-Tests für die Token-Persistierung im Frontend.

Hintergrund: Nach dem Login und einem Reload (F5) erschien erneut das
Login-Overlay, obwohl das Token im LocalStorage lag. Ursache war nicht
die Persistierung - die funktionierte - sondern dass das Overlay auf dem
Pfad "Token schon vorhanden" nie ausgeblendet wurde. Das Dashboard lud
vollständig, blieb aber dahinter verborgen.

Genau diese Klasse von Fehlern ist nur in einem echten Browser sichtbar:
Die Sichtbarkeit hängt an einer CSS-Klasse, nicht am JavaScript-Zustand.
Deshalb hier Playwright statt eines DOM-Stubs.

Fixtures (Server, Browser, Seite) liegen in conftest.py. Fehlt
Playwright, überspringen sich diese Tests, statt die Suite rot zu färben.
"""

from __future__ import annotations

from tests.conftest import TOKEN


def _overlay_visible(page) -> bool:
    return page.evaluate(
        "() => getComputedStyle(document.getElementById('login-overlay')).display !== 'none'"
    )


def _stored_token(page) -> str:
    return page.evaluate("() => localStorage.getItem('dashboard_token') || ''")


def _login(page, base_url: str) -> None:
    page.goto(base_url + "/")
    page.wait_for_selector("#login-overlay:not(.hidden)")
    page.fill("#input-token", TOKEN)
    page.click("#login-save")
    page.wait_for_selector(".card", timeout=15000)


def test_token_survives_reload_and_login_overlay_stays_hidden(page, server):
    """Der eigentliche Regressionstest: nach F5 darf das Login-Formular
    nicht erneut erscheinen, und die API-Anfrage muss das gespeicherte
    Token tragen."""
    _login(page, server)
    assert not _overlay_visible(page), "Overlay direkt nach dem Login noch sichtbar"

    # Nur die Anfragen NACH dem Reload betrachten.
    requests_after_reload = []
    page.on(
        "request",
        lambda request: (
            requests_after_reload.append(request.headers.get("x-dashboard-token"))
            if "/api/status" in request.url
            else None
        ),
    )

    page.reload()  # simulierter F5
    page.wait_for_selector(".card", timeout=15000)

    assert _stored_token(page) == TOKEN, "Token nach Reload nicht mehr im LocalStorage"
    assert not _overlay_visible(page), "Login-Overlay nach Reload wieder sichtbar (Regression)"
    assert page.locator(".card").count() == 4, "Dashboard nach Reload unvollständig"
    assert requests_after_reload, "Nach dem Reload wurde /api/status gar nicht abgefragt"
    assert all(header == TOKEN for header in requests_after_reload), (
        "Gespeichertes Token wurde nicht als X-Dashboard-Token-Header gesendet"
    )


def test_without_stored_token_the_login_overlay_is_shown(page, server):
    """Gegenprobe zum Fix: das Overlay darf nicht pauschal verschwinden."""
    page.goto(server + "/")
    page.wait_for_selector("#login-overlay:not(.hidden)")

    assert _overlay_visible(page)
    assert _stored_token(page) == ""


def test_invalid_token_clears_storage_and_shows_overlay_again(page, server):
    """Ein abgelehntes Token darf nicht dauerhaft gespeichert bleiben -
    sonst käme der Nutzer in eine Schleife aus leerem Dashboard."""
    page.goto(server + "/")
    page.wait_for_selector("#login-overlay:not(.hidden)")
    page.fill("#input-token", "f" * 64)  # lang genug, aber falsch
    page.click("#login-save")

    page.wait_for_selector("#login-error.visible", timeout=15000)

    assert _overlay_visible(page)
    assert _stored_token(page) == "", "Ungültiges Token blieb im LocalStorage"
