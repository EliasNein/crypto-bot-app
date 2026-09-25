"""Strukturmessung + Kein-Informationsverlust-Prüfung für Design-Runde 2 (P4-P8).

NOCH NICHT TEIL DER PYTEST-SUITE - siehe README.md in diesem Ordner.

Aufruf: python measure_round2.py <praefix> <port>
Erwartet einen laufenden Server mit dem Datensatz "demo" aus fixtures.py.

Misst im gerenderten DOM, nicht im CSS - gezählt wird, was der Nutzer sieht.
Die Messwerte (Kästen, Stile, Abstände ...) sind Information. Harte Prüfung
ist der Block "Kein Informationsverlust": Jede Position, die die API
liefert, muss nach dem Aufklappen auf der Seite stehen - genau daran ist
vor Runde 2 das stille Abschneiden der DCA-Liste aufgefallen (10 von 13).

Exit-Code 1, wenn eine Kein-Informationsverlust-Prüfung fehlschlägt oder
die Seite Konsolenfehler wirft.
"""
import json
import sys
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

TOKEN = "demo-token-zum-lokalen-anschauen-2026"
OUT = Path(__file__).resolve().parent / "out"

MESS_JS = r"""
() => {
  // checkVisibility() statt display/visibility/Groesse: Chromium versteckt
  // den Inhalt eines geschlossenen <details> ueber content-visibility, das
  // erkennt nur checkVisibility. Fuer normale Elemente liefern beide
  // Pruefungen dasselbe - die Vorher-Werte bleiben damit vergleichbar.
  const sichtbar = (e) => {
    const r = e.getBoundingClientRect();
    return e.checkVisibility({ contentVisibilityAuto: true, visibilityProperty: true })
      && r.width > 0 && r.height > 0;
  };
  const alle = [...document.querySelectorAll('body *')].filter(e => !e.closest('svg') && !e.closest('#login-overlay'));

  // Kasten = sichtbares Element mit eigenem Rahmen ODER eigener Füllung
  const istKasten = (e) => {
    const s = getComputedStyle(e);
    const rahmen = parseFloat(s.borderTopWidth) > 0 && parseFloat(s.borderLeftWidth) > 0;
    const fuellung = s.backgroundColor !== 'rgba(0, 0, 0, 0)';
    return (rahmen || fuellung) && !['BUTTON','SELECT','INPUT','OPTION'].includes(e.tagName);
  };
  const kaesten = alle.filter(e => sichtbar(e) && istKasten(e));
  // Verschachtelungstiefe: wie viele Kasten-Vorfahren hat ein Kasten?
  let maxTiefe = 0;
  for (const k of kaesten) {
    let t = 1, p = k.parentElement;
    while (p) { if (kaesten.includes(p)) t++; p = p.parentElement; }
    maxTiefe = Math.max(maxTiefe, t);
  }

  // Titel-/Label-Stile: feste Liste der Klassen, die in einem der beiden
  // Staende Titel oder Label sind. Vorher UND nachher mit derselben Liste
  // gemessen. Inhalt (etwa "An 10 von 20 Tagen investiert") zaehlt nicht.
  const TITEL_LABEL = ['zone-title','block-title','card-title','unrealized-title',
                       'tile-label','field-label','label','bot-name'];
  const titelLabel = alle.filter(e => sichtbar(e) &&
    TITEL_LABEL.some(k => (e.classList || []).contains(k)));
  const stile = new Set(titelLabel.map(e => {
    const s = getComputedStyle(e);
    return `${s.fontSize}|${s.fontWeight}|${s.color}|${s.textTransform}`;
  }));

  // Abstands- und Radiuswerte, wie sie gerendert werden
  const abstaende = new Set(), radien = new Set();
  for (const e of alle) {
    if (!sichtbar(e)) continue;
    const s = getComputedStyle(e);
    for (const p of ['paddingTop','paddingRight','paddingBottom','paddingLeft',
                     'marginTop','marginBottom','rowGap','columnGap']) {
      const v = s[p];
      if (v && v !== '0px' && v !== 'normal' && v !== 'auto') abstaende.add(v);
    }
    const r = s.borderTopLeftRadius;
    if (r && r !== '0px') radien.add(r);
  }

  // Positionszeilen: sichtbar vs. im DOM vorhanden (aufklappbar)
  const posImDom = document.querySelectorAll('.position').length;
  const posSichtbar = [...document.querySelectorAll('.position')].filter(sichtbar).length;

  // Fußzeilen pro Bot-Karte
  const fussProKarte = [...document.querySelectorAll('.card')].map(c =>
    [...c.querySelectorAll('.last-activity, .card-footer')].filter(sichtbar).length);

  // P4: oberste Kaesten (ohne Kasten-Vorfahren, ohne den Statuspunkt) in
  // DOM-Reihenfolge. Laengste Folge gleich aussehender Kaesten, die nicht
  // durch eine Zonenueberschrift unterbrochen wird.
  const oberste = kaesten.filter(k => {
    if (k.classList.contains('dot')) return false;
    let p = k.parentElement;
    while (p) { if (kaesten.includes(p)) return false; p = p.parentElement; }
    return true;
  });
  const folge = [...document.querySelectorAll('body *')]
    .filter(e => oberste.includes(e) || (e.classList && e.classList.contains('zone-title') && sichtbar(e)));
  let laengste = 0, lauf = 0, letzte = null;
  const signaturen = new Set();
  for (const e of folge) {
    if (e.classList.contains('zone-title')) { lauf = 0; letzte = null; continue; }
    const s = getComputedStyle(e);
    const sig = `${s.backgroundColor}|${s.borderTopColor}|${s.borderTopWidth}`;
    signaturen.add(sig);
    lauf = (sig === letzte) ? lauf + 1 : 1;
    letzte = sig;
    laengste = Math.max(laengste, lauf);
  }
  const zonen = [...document.querySelectorAll('.zone-title')].filter(sichtbar).length;

  // Gleich große Top-Kennzahlen im Übersichtsbereich
  const topZahlen = [...document.querySelectorAll('.tile-value, .hero-value')].filter(sichtbar)
    .map(e => getComputedStyle(e).fontSize);

  return {
    kaesten_sichtbar: kaesten.length,
    kaesten_max_verschachtelung: maxTiefe,
    oberste_kaesten: oberste.length,
    gewichtungsklassen_oberste_kaesten: signaturen.size,
    laengste_folge_gleicher_kaesten_ohne_trenner: laengste,
    zonenueberschriften: zonen,
    titel_label_stile: stile.size,
    titel_label_stile_liste: [...stile],
    abstandswerte: [...abstaende].sort((a,b)=>parseFloat(a)-parseFloat(b)),
    radiuswerte: [...radien].sort((a,b)=>parseFloat(a)-parseFloat(b)),
    positionen_im_dom: posImDom,
    positionen_sichtbar: posSichtbar,
    fusszeilen_pro_karte: fussProKarte,
    top_kennzahlen_groessen: topZahlen,
    seitentext: document.body.innerText,
  };
}
"""


def zahl(v):
    return f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def main(prefix, port):
    base = f"http://127.0.0.1:{port}"
    OUT.mkdir(exist_ok=True)

    # Soll-Werte direkt aus der API: Das Frontend muss jeden davon zeigen können.
    req = urllib.request.Request(f"{base}/api/status", headers={"X-Dashboard-Token": TOKEN})
    api = json.load(urllib.request.urlopen(req))

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 420, "height": 1400})
        fehler = []
        page.on("console", lambda m: fehler.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: fehler.append(str(e)))

        page.goto(base + "/")
        page.wait_for_selector("#login-overlay:not(.hidden)")
        page.fill("#input-token", TOKEN)
        page.click("#login-save")
        page.wait_for_selector(".card", timeout=15000)
        page.wait_for_timeout(400)

        page.screenshot(path=str(OUT / f"r2-{prefix}-voll.png"), full_page=True)
        page.screenshot(path=str(OUT / f"r2-{prefix}-oben.png"),
                        clip={"x": 0, "y": 0, "width": 420, "height": 700})

        m = page.evaluate(MESS_JS)

        # Aufgeklappt: Alle <details> öffnen, dann muss jede Position sichtbar sein
        page.evaluate("() => document.querySelectorAll('details').forEach(d => d.open = true)")
        page.wait_for_timeout(150)
        offen = page.evaluate(MESS_JS)
        browser.close()

    # --- Kein-Informationsverlust-Prüfung gegen die API -----------------------
    text = offen["seitentext"]
    pruefungen = {}
    ov = api["overview"]
    pruefungen["Gesamtgewinn-Betrag sichtbar"] = zahl(ov["gesamtgewinn"]) in text
    pruefungen["Gesamtverlust-Betrag sichtbar"] = zahl(ov["gesamtverlust"]) in text
    netto = ov["gesamtgewinn"] + ov["gesamtverlust"]
    pruefungen["Netto-Betrag sichtbar"] = zahl(netto) in text

    erwartete_positionen = sum(len(api[b].get("open_positions", [])) for b in ("dca", "grid", "trend"))
    pruefungen[f"alle {erwartete_positionen} Positionen nach Aufklappen im DOM"] = (
        offen["positionen_im_dom"] == erwartete_positionen)
    pruefungen["alle Positionen nach Aufklappen sichtbar"] = (
        offen["positionen_sichtbar"] == erwartete_positionen)

    for bot, hb in api["heartbeat"].items():
        if hb["status"] == "warn" and hb["reason"] == "consecutive_failures":
            pruefungen[f"Heartbeat-Warnung {bot} sichtbar"] = f'{hb["consecutive_failures"]} Fehlschl' in text

    m.pop("seitentext")
    print(json.dumps(m, indent=2, ensure_ascii=False))
    print()
    print(f"API liefert {erwartete_positionen} offene Positionen (DCA+Grid+Trend)")
    print("--- Kein Informationsverlust ---")
    for name, bestanden in pruefungen.items():
        print(("  OK   " if bestanden else "  FEHLT ") + name)
    print("Console-Fehler:", fehler)

    return 0 if all(pruefungen.values()) and not fehler else 1


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    sys.exit(main(*sys.argv[1:]))
