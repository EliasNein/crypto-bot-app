"""Browser-Prüfungen zu Design-Runde 2 (P4-P8): Ergebnis-Block und Aufklappen.

NOCH NICHT TEIL DER PYTEST-SUITE - siehe README.md in diesem Ordner.

Aufruf: python verify_round2.py <port_demo> <port_nur_dry_run> <port_ein_abschluss>
Erwartet drei laufende Server mit den Datensätzen aus fixtures.py.
Bequemer: run_checks.py startet Server und Prüfungen gemeinsam.

Exit-Code 1, sobald eine Prüfung fehlschlägt.
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

TOKEN = "demo-token-zum-lokalen-anschauen-2026"
OUT = Path(__file__).resolve().parent / "out"

fehlgeschlagen = []


def login(page, port):
    page.goto(f"http://127.0.0.1:{port}/")
    page.wait_for_selector("#login-overlay:not(.hidden)")
    page.fill("#input-token", TOKEN)
    page.click("#login-save")
    page.wait_for_selector(".card", timeout=15000)
    page.wait_for_timeout(300)


def ok(bedingung, text):
    print(("  OK    " if bedingung else "  FEHLER ") + text)
    if not bedingung:
        fehlgeschlagen.append(text)


def main(port_demo, port_nur_dry_run, port_ein_abschluss):
    OUT.mkdir(exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()

        # 1) Aufgeklappte Liste überlebt ein Neuzeichnen
        print("1) Aufklapp-Zustand beim Refresh")
        page = browser.new_page(viewport={"width": 420, "height": 1400})
        requests = []
        page.on("request", lambda r: requests.append(r.url) if "/api/status" in r.url else None)
        login(page, port_demo)
        page.click(".card >> nth=0 >> summary")
        page.wait_for_timeout(200)
        ok(page.eval_on_selector(".card >> nth=0 >> details", "d => d.open"), "DCA-Liste nach Klick offen")
        ok(page.text_content(".card >> nth=0 >> summary") == "weniger anzeigen",
           "Beschriftung wechselt auf 'weniger anzeigen'")

        vorher = len(requests)
        # Derselbe Pfad wie der 45-s-Refresh: fetchStatus() -> render() baut alle Karten neu.
        page.evaluate("() => document.dispatchEvent(new Event('visibilitychange'))")
        page.wait_for_timeout(800)
        ok(len(requests) > vorher, "Refresh hat /api/status erneut abgefragt (Karten neu gebaut)")
        ok(page.eval_on_selector(".card >> nth=0 >> details", "d => d.open"),
           "DCA-Liste nach Refresh weiterhin offen")
        ok(page.eval_on_selector(".card >> nth=1", "c => !c.querySelector('details')"),
           "Grid mit 4 Positionen: nichts eingeklappt (+1-Regel)")
        page.locator(".card").nth(0).screenshot(path=str(OUT / "r2-dca-offen.png"))
        page.close()

        # 2) Nur Dry-Run-Daten: kein echtes Ergebnis
        print("2) Ergebnis-Block ohne echte Trades")
        page = browser.new_page(viewport={"width": 420, "height": 900})
        login(page, port_nur_dry_run)
        hero = page.text_content("#hero-block")
        ok("Noch kein realisiertes Ergebnis" in hero, "zeigt 'Noch kein realisiertes Ergebnis'")
        ok("0,00" not in hero, "keine große 0,00, die wie 'ausgeglichen' aussähe")
        ok(page.query_selector("#hero-block svg") is None, "kein Diagramm")
        page.locator("#hero-block").screenshot(path=str(OUT / "r2-hero-leer.png"))
        page.close()

        # 3) Genau ein Abschlusstag: Zahl ohne Diagramm
        print("3) Ergebnis-Block mit einem einzigen Abschlusstag")
        page = browser.new_page(viewport={"width": 420, "height": 900})
        login(page, port_ein_abschluss)
        hero = page.text_content("#hero-block")
        ok("+0,62 USDT" in hero, "Netto-Zahl +0,62 USDT")
        ok("einziger Abschlusstag" in hero, "Hinweis auf einzigen Abschlusstag")
        ok(page.query_selector("#hero-block svg") is None, "kein Diagramm aus einem einzigen Punkt")
        ok("Verlust 0,00" in hero, "Verlust ohne sinnloses Vorzeichen ('0,00' statt '+0,00')")
        page.locator("#hero-block").screenshot(path=str(OUT / "r2-hero-einzeln.png"))
        page.close()

        browser.close()

    print()
    print(f"{12 - len(fehlgeschlagen)} von 12 Prüfungen bestanden.")
    return 1 if fehlgeschlagen else 0


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    sys.exit(main(*sys.argv[1:]))
