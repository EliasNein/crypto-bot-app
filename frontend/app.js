(() => {
  "use strict";

  const STORAGE_TOKEN = "dashboard_token";
  const STORAGE_BASE = "dashboard_api_base";
  const REFRESH_INTERVAL_MS = 45000;

  const els = {
    connDot: document.getElementById("conn-dot"),
    connText: document.getElementById("conn-text"),
    errorBanner: document.getElementById("error-banner"),
    cards: document.getElementById("cards"),
    heroBlock: document.getElementById("hero-block"),
    unrealizedBlock: document.getElementById("unrealized-block"),
    activityBlock: document.getElementById("activity-block"),
    overlay: document.getElementById("login-overlay"),
    inputToken: document.getElementById("input-token"),
    inputBase: document.getElementById("input-base"),
    loginError: document.getElementById("login-error"),
    loginSave: document.getElementById("login-save"),
    settingsBtn: document.getElementById("settings-btn"),
    exportBtn: document.getElementById("export-btn"),
    exportPeriod: document.getElementById("export-period"),
  };

  let refreshTimer = null;

  function getToken() {
    try {
      return localStorage.getItem(STORAGE_TOKEN) || "";
    } catch {
      return "";
    }
  }

  function getApiBase() {
    try {
      return localStorage.getItem(STORAGE_BASE) || "";
    } catch {
      return "";
    }
  }

  function saveCredentials(token, base) {
    try {
      localStorage.setItem(STORAGE_TOKEN, token);
      localStorage.setItem(STORAGE_BASE, base);
    } catch {
      // LocalStorage nicht verfügbar (z.B. privates Fenster) - Sitzung
      // läuft trotzdem, nur ohne "Angemeldet bleiben".
    }
  }

  function clearToken() {
    try {
      localStorage.removeItem(STORAGE_TOKEN);
    } catch {
      /* siehe saveCredentials */
    }
  }

  function statusUrl() {
    const base = getApiBase().replace(/\/+$/, "");
    return `${base}/api/status`;
  }

  function exportUrl(period) {
    const base = getApiBase().replace(/\/+$/, "");
    return `${base}/api/export/trades?period=${encodeURIComponent(period)}`;
  }

  function showOverlay(prefill) {
    els.inputToken.value = "";
    els.inputBase.value = prefill ? getApiBase() : "";
    els.loginError.classList.remove("visible");
    els.overlay.classList.remove("hidden");
  }

  function hideOverlay() {
    els.overlay.classList.add("hidden");
  }

  function showLoginError(message) {
    els.loginError.textContent = message;
    els.loginError.classList.add("visible");
  }

  function setConnection(state, text) {
    els.connDot.className = `dot ${state}`;
    els.connText.textContent = text;
  }

  function showErrorBanner(message) {
    els.errorBanner.textContent = message;
    els.errorBanner.classList.add("visible");
  }

  function hideErrorBanner() {
    els.errorBanner.classList.remove("visible");
  }

  // --- Formatierung ---------------------------------------------------

  function fmtNum(value, decimals) {
    if (value === null || value === undefined || Number.isNaN(value)) return "–";
    return Number(value).toLocaleString("de-DE", {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    });
  }

  function fmtQty(value) {
    return fmtNum(value, 8);
  }

  function fmtPrice(value) {
    return fmtNum(value, 2);
  }

  function fmtPct(value) {
    if (value === null || value === undefined) return "–";
    return `${(value * 100).toFixed(1)}%`;
  }

  // Eine Kaskade für beide Zeitangaben auf der Karte, damit "Letzte
  // Aktivität" und der Heartbeat identisch formulieren.
  function fmtRelativeSeconds(seconds) {
    if (seconds === null || seconds === undefined || Number.isNaN(seconds)) return null;
    const diffMin = Math.round(seconds / 60);
    if (diffMin < 1) return "gerade eben";
    if (diffMin < 60) return `vor ${diffMin} Min.`;
    const diffH = Math.round(diffMin / 60);
    if (diffH < 24) return `vor ${diffH} Std.`;
    return `vor ${Math.round(diffH / 24)} Tag(en)`;
  }

  function fmtRelativeTime(iso) {
    if (!iso) return "keine Aktivität";
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return iso;
    return fmtRelativeSeconds((Date.now() - date.getTime()) / 1000);
  }

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function metric(label, value, cls) {
    const wrap = el("div", "metric");
    wrap.appendChild(el("div", "field-label", label));
    wrap.appendChild(el("div", `value${cls ? " " + cls : ""}`, value));
    return wrap;
  }

  function pnlClass(value) {
    if (value === null || value === undefined) return "";
    return value >= 0 ? "pos" : "neg";
  }

  // --- Karten ------------------------------------------------------------

  function badge(status) {
    const b = el("span", `badge ${status}`, status === "ok" ? "OK" : "Keine Daten");
    return b;
  }

  // Die Altersangabe kommt als Sekunden vom Server, nicht aus dem
  // ISO-Zeitstempel: Die Heartbeat-Dateien entstehen auf derselben
  // Maschine wie die API, damit ist die Differenz frei von Uhren-Versatz.
  // Eine falsch gehende Handy-Uhr würde sonst ausgerechnet bei der
  // Lebendigkeits-Anzeige Stillstand behaupten, wo keiner ist.
  // Texte beginnen klein, weil sie in der Fußzeile nach einem " · " stehen.
  function heartbeatLine(hb) {
    if (!hb) return null;

    if (hb.status === "no_data") {
      return { text: "kein Heartbeat verfügbar", warn: false };
    }

    if (hb.reason === "consecutive_failures") {
      const n = hb.consecutive_failures;
      const wort = n === 1 ? "Fehlschlag" : "Fehlschläge";
      return { text: `⚠ ${n} ${wort} in Folge`, warn: true };
    }

    if (hb.reason === "stale_success") {
      return { text: "⚠ keine Erfolgsmeldung seit über 48h", warn: true };
    }

    if (hb.reason === "no_confirmed_success") {
      // Bewusst neutral: direkt nach einem Neustart ist das der
      // Normalzustand, bei 24h-Takt womöglich einen ganzen Tag lang.
      return { text: "noch kein erfolgreicher Zyklus seit Prozessstart", warn: false };
    }

    const relativ = fmtRelativeSeconds(hb.seconds_since_success);
    return { text: `letzter erfolgreicher Zyklus ${relativ || "unbekannt"}`, warn: false };
  }

  // Eine Fußzeile statt zwei fast gleicher: Ledger-Aktivität und
  // Prozess-Heartbeat nebeneinander. Nur ein Warnungsteil wird amber, damit
  // er genauso auffällt wie vorher als eigene Zeile. Die exakten
  // Zeitstempel bleiben als Tooltip erhalten.
  function cardFooter(data, heartbeat) {
    const teile = [];

    if (data.status === "ok" && data.last_activity !== undefined) {
      const aktivitaet = el(
        "span",
        "",
        data.last_activity ? `Aktivität ${fmtRelativeTime(data.last_activity)}` : "keine Aktivität"
      );
      aktivitaet.title = data.last_activity || "";
      teile.push(aktivitaet);
    }

    // Der Heartbeat gehört auch dann auf die Karte, wenn das Ledger
    // fehlt: "Datei weg, Prozess läuft" ist eine andere Lage als
    // "Prozess tot" - und genau dann braucht man die Unterscheidung.
    const puls = heartbeatLine(heartbeat);
    if (puls) {
      const pulsTeil = el("span", puls.warn ? "warn" : "", puls.text);
      if (heartbeat && heartbeat.last_successful_cycle) {
        pulsTeil.title = `Letzter Erfolg laut Bot: ${heartbeat.last_successful_cycle}`;
      }
      teile.push(pulsTeil);
    }

    if (!teile.length) return null;
    const footer = el("div", "card-footer");
    teile.forEach((teil, i) => {
      if (i) footer.appendChild(document.createTextNode(" · "));
      footer.appendChild(teil);
    });
    return footer;
  }

  function buildCard(title, data, renderBody, heartbeat) {
    const card = el("div", "card");
    const header = el("div", "card-header");
    header.appendChild(el("div", "block-title", title));
    header.appendChild(badge(data.status));
    card.appendChild(header);

    if (data.status !== "ok") {
      card.appendChild(el("div", "no-data-text", data.error || "Keine Daten verfügbar."));
    } else {
      renderBody(card);
    }

    const footer = cardFooter(data, heartbeat);
    if (footer) card.appendChild(footer);
    return card;
  }

  function buildPositionRow(parts) {
    const row = el("div", "position");
    const left = el("span");
    left.textContent = parts.join(" · ");
    row.appendChild(left);
    return row;
  }

  const SICHTBARE_POSITIONEN = 3;

  // Welche Listen aufgeklappt sind. Das Dashboard baut die Karten alle 45 s
  // neu auf - ohne diese Erinnerung klappte eine geöffnete Liste beim
  // nächsten Refresh von selbst wieder zu.
  const offeneListen = new Set();

  // Die ersten Zeilen direkt, den Rest aufklappbar. Jede Position steht
  // weiterhin im Dokument; nichts wird abgeschnitten, nur eingeklappt.
  function positionList(schluessel, zeilen) {
    const list = el("div", "positions");

    // Eine einzelne Zeile wird nicht eingeklappt: "+1 weitere anzeigen"
    // bräuchte genau so viel Platz wie die Zeile selbst.
    if (zeilen.length <= SICHTBARE_POSITIONEN + 1) {
      zeilen.forEach((zeile) => list.appendChild(zeile));
      return list;
    }

    zeilen.slice(0, SICHTBARE_POSITIONEN).forEach((zeile) => list.appendChild(zeile));
    const rest = zeilen.slice(SICHTBARE_POSITIONEN);

    const details = document.createElement("details");
    details.className = "positions-more";
    const summary = document.createElement("summary");
    const beschrifte = () => {
      summary.textContent = details.open ? "weniger anzeigen" : `+${rest.length} weitere anzeigen`;
    };
    details.appendChild(summary);
    rest.forEach((zeile) => details.appendChild(zeile));

    details.open = offeneListen.has(schluessel);
    beschrifte();
    details.addEventListener("toggle", () => {
      if (details.open) offeneListen.add(schluessel);
      else offeneListen.delete(schluessel);
      beschrifte();
    });

    list.appendChild(details);
    return list;
  }

  function cardDca(data, heartbeat) {
    return buildCard("DCA-Bot", data, (card) => {
      const metrics = el("div", "metrics-row");
      metrics.appendChild(metric("Käufe (echt)", String(data.metrics.real_trades)));
      metrics.appendChild(metric("Dry-Run", String(data.metrics.dry_run_trades)));
      metrics.appendChild(metric("Menge gesamt", fmtQty(data.metrics.total_quantity)));
      metrics.appendChild(metric("Eingesetzt", `${fmtPrice(data.metrics.total_spent)} USDT`));
      if (data.metrics.avg_entry_price !== null) {
        metrics.appendChild(metric("Ø Einstieg", fmtPrice(data.metrics.avg_entry_price)));
      }
      card.appendChild(metrics);

      if (data.open_positions.length) {
        // Neueste zuerst. Früher wurde hier auf die fünf neuesten Käufe
        // gekürzt - ältere verschwanden ohne jeden Hinweis.
        const zeilen = [...data.open_positions]
          .reverse()
          .map((p) => buildPositionRow([p.symbol, `${fmtPrice(p.price)} USDT`, fmtQty(p.quantity)]));
        card.appendChild(positionList("dca", zeilen));
      }
    }, heartbeat);
  }

  function cardGrid(data, heartbeat) {
    return buildCard("Grid-Bot", data, (card) => {
      const metrics = el("div", "metrics-row");
      metrics.appendChild(metric("Offen", String(data.metrics.open_positions)));
      metrics.appendChild(metric("Geschlossen", String(data.metrics.closed_positions)));
      metrics.appendChild(
        metric("Realisiert", `${fmtPrice(data.metrics.realized_pnl)} USDT`, pnlClass(data.metrics.realized_pnl))
      );
      card.appendChild(metrics);

      if (data.open_positions.length) {
        const zeilen = data.open_positions.map((p) => {
          const row = buildPositionRow([
            `Stufe ${p.level_index}`,
            `Kauf ${fmtPrice(p.buy_price)}`,
            `Ziel ${fmtPrice(p.target_sell_price)}`,
          ]);
          if (p.dry_run) {
            row.appendChild(el("span", "dry-run-tag", "DRY-RUN"));
          }
          return row;
        });
        card.appendChild(positionList("grid", zeilen));
      }
    }, heartbeat);
  }

  function cardTrend(data, heartbeat) {
    return buildCard("Trend-Bot", data, (card) => {
      const metrics = el("div", "metrics-row");
      metrics.appendChild(metric("Offen", String(data.metrics.open_trades)));
      metrics.appendChild(metric("Geschlossen", String(data.metrics.closed_trades)));
      metrics.appendChild(
        metric("Realisiert", `${fmtPrice(data.metrics.realized_pnl)} USDT`, pnlClass(data.metrics.realized_pnl))
      );
      card.appendChild(metrics);

      if (data.open_positions.length) {
        const zeilen = data.open_positions.map((p) => {
          const row = buildPositionRow([
            `Einstieg ${fmtPrice(p.entry_price)}`,
            `Menge ${fmtQty(p.quantity)}`,
            p.stop_loss_order_id ? "SL gesetzt" : "kein SL",
          ]);
          if (p.dry_run) {
            row.appendChild(el("span", "dry-run-tag", "DRY-RUN"));
          }
          return row;
        });
        card.appendChild(positionList("trend", zeilen));
      }
    }, heartbeat);
  }

  function cardAllocator(data, heartbeat) {
    return buildCard("Allocator", data, (card) => {
      const metrics = el("div", "metrics-row");
      metrics.appendChild(metric("Trend-Anteil", fmtPct(data.trend_fraction)));
      metrics.appendChild(metric("DCA-Anteil", fmtPct(data.dca_fraction)));
      if (data.gap_pct !== null && data.gap_pct !== undefined) {
        metrics.appendChild(metric("Gap", `${fmtNum(data.gap_pct, 2)}%`));
      }
      if (data.direction) {
        metrics.appendChild(metric("Richtung", data.direction));
      }
      card.appendChild(metrics);
    }, heartbeat);
  }

  const BOT_LABELS = { dca: "DCA", grid: "Grid", trend: "Trend" };

  function unrealizedRowText(entry) {
    if (entry === null || entry === undefined) return "keine Daten";
    if (!entry.quantity) return "keine offene Position";
    const qty = fmtQty(entry.quantity);
    if (entry.avg_price === null || entry.avg_price === undefined) {
      return `${qty} BTC · Einstandspreis unbekannt`;
    }
    return `${qty} BTC zu Ø ${fmtPrice(entry.avg_price)} USDT Einstandspreis`;
  }

  // Die Kernaussage der Seite: eine Zahl, die niemand mehr im Kopf
  // ausrechnen muss. Bewusst "realisiert" und nicht "gesamt" - der
  // DCA-Bestand fließt nicht ein, ein "Gesamtergebnis" würde also mehr
  // behaupten, als die Zahl enthält.
  function renderHero(overview, verlauf) {
    const block = els.heroBlock;
    block.innerHTML = "";
    block.appendChild(el("div", "field-label", "Realisiertes Ergebnis"));

    const gewinn = overview.gesamtgewinn;
    const verlust = overview.gesamtverlust;
    const hatVerlauf = Array.isArray(verlauf) && verlauf.length > 0;

    // "Noch nie gehandelt" ist etwas anderes als "genau ausgeglichen" -
    // eine große 0,00 würde das Erste als das Zweite ausgeben.
    if (!hatVerlauf && gewinn === 0 && verlust === 0) {
      block.appendChild(el("div", "hero-empty", "Noch kein realisiertes Ergebnis"));
      block.appendChild(
        el(
          "div",
          "hero-breakdown",
          "Sobald der erste echte Trade geschlossen ist, erscheinen hier das Netto-Ergebnis und sein Verlauf."
        )
      );
      return;
    }

    // Farbe und "±0,00" folgen derselben Rundung wie die Ziffern (siehe displayedSign).
    const netto = gewinn + verlust;
    const vorzeichen = displayedSign(netto);
    const richtung = vorzeichen > 0 ? " pos" : vorzeichen < 0 ? " neg" : "";
    block.appendChild(
      el("div", `value hero-value${richtung}`, vorzeichen === 0 ? "±0,00 USDT" : fmtSigned(netto))
    );

    // Nur die Netto-Zahl trägt Farbe; die Aufschlüsselung bleibt grau.
    block.appendChild(
      el(
        "div",
        "hero-breakdown",
        `Gewinn ${fmtSignedPlain(gewinn)} · Verlust ${fmtSignedPlain(verlust)} USDT`
      )
    );

    if (!hatVerlauf) return;

    if (verlauf.length === 1) {
      // Ein einzelner Punkt ist kein Verlauf - die Zahl steht schon oben.
      block.appendChild(
        el("div", "hero-meta", `Bisher ein einziger Abschlusstag: ${fmtShortDate(verlauf[0].datum)}`)
      );
      return;
    }

    block.appendChild(buildPnlChart(verlauf));
  }

  function renderUnrealized(overview) {
    const unrealized = overview["unrealisiert_geschätzt"] || {};

    els.unrealizedBlock.innerHTML = "";
    els.unrealizedBlock.appendChild(el("div", "block-title", "Unrealisiert (geschätzt)"));
    const rows = el("div", "unrealized-rows");
    for (const key of ["dca", "grid", "trend"]) {
      const row = el("div", "unrealized-row");
      row.appendChild(el("span", "field-label", BOT_LABELS[key]));
      row.appendChild(el("span", "", unrealizedRowText(unrealized[key])));
      rows.appendChild(row);
    }
    els.unrealizedBlock.appendChild(rows);
    els.unrealizedBlock.appendChild(
      el(
        "div",
        "unrealized-hint",
        unrealized["hinweis"] || "kein Live-Kurs, daher keine Berechnung des unrealisierten Gewinns/Verlusts"
      )
    );
  }

  // --- PnL-Verlauf -------------------------------------------------------

  const SVG_NS = "http://www.w3.org/2000/svg";

  function svgEl(tag, attrs) {
    const node = document.createElementNS(SVG_NS, tag);
    for (const [key, value] of Object.entries(attrs)) {
      node.setAttribute(key, String(value));
    }
    return node;
  }

  function fmtShortDate(iso) {
    const date = new Date(`${iso}T00:00:00Z`);
    if (Number.isNaN(date.getTime())) return iso;
    return `${String(date.getUTCDate()).padStart(2, "0")}.${String(date.getUTCMonth() + 1).padStart(2, "0")}.`;
  }

  // Richtung eines Betrags so, wie er ANGEZEIGT wird: 1, -1 oder 0.
  // Bewusst aus den formatierten Ziffern abgeleitet statt über eine
  // eigene Rundung: Math.round rundet ,5 stets nach oben (Math.round(-0.5)
  // ist -0), toLocaleString dagegen vom Nullpunkt weg. Mit zwei
  // Rundungswegen erschien +0,005 als "+0,01" in Grün, −0,005 aber als
  // "±0,00" ohne Farbe. Aus den Ziffern selbst abgeleitet, können Anzeige,
  // Vorzeichen und Farbe nicht mehr auseinanderlaufen.
  function displayedSign(value) {
    if (!/[1-9]/.test(fmtPrice(Math.abs(value)))) return 0;
    return value < 0 ? -1 : 1;
  }

  // Null ohne Vorzeichen - "Verlust +0,00" wäre sinnlos.
  function fmtSignedPlain(value) {
    const formatted = fmtPrice(Math.abs(value));
    const sign = displayedSign(value);
    if (sign === 0) return formatted;
    return `${sign < 0 ? "−" : "+"}${formatted}`;
  }

  function fmtSigned(value) {
    return `${fmtSignedPlain(value)} USDT`;
  }

  function daysSinceEpoch(iso) {
    return Date.parse(`${iso}T00:00:00Z`) / 86400000;
  }

  function buildPnlChart(verlauf) {
    // Geometrie: der Platz für die Achsenbeschriftung ist eingeplant, damit
    // die Karte nicht scrollen muss.
    const W = 340;
    const H = 150;
    const padLeft = 46;
    const padRight = 12;
    const padTop = 14;
    const padBottom = 20;
    const plotW = W - padLeft - padRight;
    const plotH = H - padTop - padBottom;

    const points = verlauf.map((entry) => ({
      x: daysSinceEpoch(entry.datum),
      y: entry.kumulierte_pnl_bis_zu_diesem_tag,
      datum: entry.datum,
    }));

    // Die kumulierte Summe gilt bis heute weiter - die Linie läuft flach
    // bis zum aktuellen Tag, statt am letzten Abschluss abzubrechen.
    const heute = Math.floor(Date.now() / 86400000);
    const xMin = points[0].x;
    const xMax = Math.max(points[points.length - 1].x, heute);
    const xSpan = xMax - xMin || 1;

    const werte = points.map((p) => p.y);
    // Die Null gehört immer in die Skala: sie ist der neutrale Mittelpunkt,
    // an dem sich Gewinn und Verlust scheiden.
    const yHigh = Math.max(0, ...werte);
    const yLow = Math.min(0, ...werte);
    const ySpan = yHigh - yLow || 1;
    const headroom = ySpan * 0.12;
    const yTop = yHigh + headroom;
    const yBottom = yLow - headroom;

    const sx = (x) => padLeft + ((x - xMin) / xSpan) * plotW;
    const sy = (y) => padTop + ((yTop - y) / (yTop - yBottom)) * plotH;

    const svg = svgEl("svg", {
      class: "pnl-chart",
      viewBox: `0 0 ${W} ${H}`,
      role: "img",
      "aria-label": `Kumulierter realisierter Gewinn/Verlust, zuletzt ${fmtSigned(
        points[points.length - 1].y
      )}`,
    });

    const endFarbe = points[points.length - 1].y >= 0 ? "var(--accent)" : "var(--danger)";

    // Stufenlinie: die kumulierte PnL springt am Abschlusstag und bleibt
    // dazwischen konstant. Eine diagonale Verbindung würde einen stetigen
    // Verlauf behaupten, den es nicht gab.
    const segments = [`M ${sx(points[0].x)} ${sy(points[0].y)}`];
    for (let i = 1; i < points.length; i += 1) {
      segments.push(`L ${sx(points[i].x)} ${sy(points[i - 1].y)}`);
      segments.push(`L ${sx(points[i].x)} ${sy(points[i].y)}`);
    }
    const letzterX = sx(xMax);
    segments.push(`L ${letzterX} ${sy(points[points.length - 1].y)}`);
    const linePath = segments.join(" ");

    const yNull = sy(0);
    const areaPath = `${linePath} L ${letzterX} ${yNull} L ${sx(points[0].x)} ${yNull} Z`;

    // Die Null ist der neutrale Mittelpunkt: oberhalb Gewinn, unterhalb
    // Verlust. Beide Hälften bekommen ihre eigene Farbe, statt die ganze
    // Kurve nach dem Endstand einzufärben - sonst läge eine grüne Fläche
    // unter der Nulllinie und behauptete Gewinn, wo Verlust stand.
    const defs = svgEl("defs", {});
    const clipGewinn = svgEl("clipPath", { id: "pnl-clip-gewinn" });
    clipGewinn.appendChild(svgEl("rect", { x: 0, y: 0, width: W, height: Math.max(yNull, 0) }));
    const clipVerlust = svgEl("clipPath", { id: "pnl-clip-verlust" });
    clipVerlust.appendChild(
      svgEl("rect", { x: 0, y: yNull, width: W, height: Math.max(H - yNull, 0) })
    );
    defs.appendChild(clipGewinn);
    defs.appendChild(clipVerlust);
    svg.appendChild(defs);

    for (const [farbe, clipId] of [
      ["var(--accent)", "pnl-clip-gewinn"],
      ["var(--danger)", "pnl-clip-verlust"],
    ]) {
      svg.appendChild(
        svgEl("path", {
          class: "series-area",
          fill: farbe,
          d: areaPath,
          "clip-path": `url(#${clipId})`,
        })
      );
    }

    svg.appendChild(
      svgEl("line", { class: "zero-line", x1: padLeft, y1: yNull, x2: W - padRight, y2: yNull })
    );

    for (const [farbe, clipId] of [
      ["var(--accent)", "pnl-clip-gewinn"],
      ["var(--danger)", "pnl-clip-verlust"],
    ]) {
      svg.appendChild(
        svgEl("path", {
          class: "series-line",
          stroke: farbe,
          d: linePath,
          "clip-path": `url(#${clipId})`,
        })
      );
    }

    // Endpunkt-Markierung am letzten tatsächlichen Abschluss. Ohne
    // Beschriftung: Der Wert steht als Netto-Ergebnis groß direkt über dem
    // Diagramm - hier noch einmal wäre dieselbe Zahl zweimal übereinander.
    const letzterPunkt = points[points.length - 1];
    svg.appendChild(
      svgEl("circle", {
        class: "end-dot",
        cx: sx(letzterPunkt.x),
        cy: sy(letzterPunkt.y),
        r: 4.5,
        fill: endFarbe,
      })
    );

    // Y-Achse: Extremwerte plus Null, mehr braucht es auf dem Handy nicht.
    const yTicks = [yHigh, 0, yLow].filter(
      (value, index, alle) => alle.indexOf(value) === index
    );
    for (const value of yTicks) {
      const tick = svgEl("text", {
        class: "tick-label",
        x: padLeft - 6,
        y: sy(value) + 3,
        "text-anchor": "end",
      });
      tick.textContent = fmtPrice(value);
      svg.appendChild(tick);
    }

    // X-Achse: erster und letzter Tag.
    svg.appendChild(
      svgEl("line", {
        class: "axis-line",
        x1: padLeft,
        y1: H - padBottom,
        x2: W - padRight,
        y2: H - padBottom,
      })
    );
    const von = svgEl("text", { class: "tick-label", x: padLeft, y: H - padBottom + 13 });
    von.textContent = fmtShortDate(points[0].datum);
    svg.appendChild(von);

    const bis = svgEl("text", {
      class: "tick-label",
      x: W - padRight,
      y: H - padBottom + 13,
      "text-anchor": "end",
    });
    bis.textContent = "heute";
    svg.appendChild(bis);

    return svg;
  }

  // --- Investitionsaktivität ---------------------------------------------

  function activityCaveat() {
    const box = el("div", "activity-caveat");
    box.appendChild(el("strong", "", "Wichtig zur Einordnung: "));
    box.appendChild(
      document.createTextNode(
        "Ein Tag ohne Kauf bedeutet NICHT automatisch, dass die Strategie sich " +
          "bewusst gegen einen Kauf entschieden hat. Das Ledger enthält kein " +
          "Signal dafür, ob der Bot überhaupt lief - ein abgeschalteter Bot, ein " +
          "Server-Neustart oder eine Downtime sehen in den Daten exakt gleich aus " +
          "wie „Allocator heruntergefahren und kein Trend-Signal“. Diese " +
          "Zahl ist ohne diese Einschränkung kein Fehlerbericht."
      )
    );
    return box;
  }

  function renderActivity(activity) {
    els.activityBlock.innerHTML = "";
    els.activityBlock.appendChild(el("div", "block-title", "Investitionsaktivität"));

    if (!activity) {
      els.activityBlock.appendChild(el("div", "no-data-text", "Keine Daten verfügbar."));
      return;
    }

    if (activity.status === "ok") {
      els.activityBlock.appendChild(
        el(
          "div",
          "activity-headline",
          `An ${activity.days_with_activity} von ${activity.total_days_tracked} Tagen investiert`
        )
      );
      els.activityBlock.appendChild(
        el(
          "div",
          "activity-sub",
          `${fmtNum(activity.days_without_activity_pct, 1)}% der abgeschlossenen Tage ohne Kauf` +
            ` · heute ${activity.today_has_activity ? "bereits gekauft" : "bisher kein Kauf"}` +
            " (heute zählt erst ab morgen mit)"
        )
      );
    } else if (activity.days_with_dry_run_activity > 0) {
      els.activityBlock.appendChild(el("div", "activity-headline", "Noch kein echter Kauf"));
      els.activityBlock.appendChild(
        el(
          "div",
          "activity-sub",
          `Paper-Trade-Phase: an ${activity.days_with_dry_run_activity} Tagen simulierte Käufe. ` +
            "Die Quote startet mit dem ersten echten Kauf."
        )
      );
    } else {
      els.activityBlock.appendChild(el("div", "no-data-text", "Noch keine Daten."));
      return;
    }

    els.activityBlock.appendChild(activityCaveat());
  }

  function render(data) {
    renderHero(data.overview, data.pnl_verlauf);
    renderUnrealized(data.overview);
    renderActivity(data.investment_activity);

    const puls = data.heartbeat || {};
    els.cards.innerHTML = "";
    els.cards.appendChild(cardDca(data.dca, puls.dca));
    els.cards.appendChild(cardGrid(data.grid, puls.grid));
    els.cards.appendChild(cardTrend(data.trend, puls.trend));
    els.cards.appendChild(cardAllocator(data.allocator, puls.allocator));
  }

  // --- Datenabruf ----------------------------------------------------------

  async function fetchStatus() {
    const token = getToken();
    if (!token) {
      showOverlay(true);
      return;
    }

    try {
      const response = await fetch(statusUrl(), {
        headers: { "X-Dashboard-Token": token },
      });

      if (response.status === 401) {
        clearToken();
        setConnection("error", "Nicht angemeldet");
        showOverlay(true);
        showLoginError("Token ungültig oder abgelaufen. Bitte erneut eingeben.");
        return;
      }

      if (!response.ok) {
        setConnection("error", "Backend-Fehler");
        showErrorBanner(`Backend antwortete mit Status ${response.status}.`);
        return;
      }

      const data = await response.json();
      hideErrorBanner();
      setConnection("ok", `Verbunden · aktualisiert ${new Date().toLocaleTimeString("de-DE")}`);
      render(data);
    } catch (err) {
      setConnection("error", "Nicht erreichbar");
      showErrorBanner("Backend nicht erreichbar. Prüfe Verbindung/Backend-URL und versuche es erneut.");
    }
  }

  function startPolling() {
    // Das Overlay ist im HTML sichtbar angelegt (damit ohne JavaScript
    // nicht einfach ein leeres Dashboard dasteht). Wer pollt, hat ein
    // Token - dann muss es weg. Das gehört hierher und nicht in den
    // Login-Handler: sonst bleibt es bei jedem anderen Einstieg stehen,
    // etwa beim Neuladen mit bereits gespeichertem Token.
    hideOverlay();

    if (refreshTimer) clearInterval(refreshTimer);
    fetchStatus();
    refreshTimer = setInterval(fetchStatus, REFRESH_INTERVAL_MS);
  }

  // --- Events ------------------------------------------------------------

  els.loginSave.addEventListener("click", () => {
    const token = els.inputToken.value.trim();
    const base = els.inputBase.value.trim();
    if (!token) {
      showLoginError("Bitte ein Token eingeben.");
      return;
    }
    saveCredentials(token, base);
    startPolling();
  });

  els.settingsBtn.addEventListener("click", () => {
    showOverlay(true);
  });

  // Der Download läuft bewusst über fetch + Blob statt über eine
  // Navigation zur Export-URL: Das Token geht so im Header raus und
  // landet nicht in der Browser-History, im Server-Access-Log oder in
  // den Logs des Cloudflare Tunnels.
  async function downloadExport() {
    const token = getToken();
    if (!token) {
      showOverlay(true);
      return;
    }

    els.exportBtn.disabled = true;
    try {
      const response = await fetch(exportUrl(els.exportPeriod.value), {
        headers: { "X-Dashboard-Token": token },
      });

      if (response.status === 401) {
        clearToken();
        showOverlay(true);
        showLoginError("Token ungültig oder abgelaufen. Bitte erneut eingeben.");
        return;
      }

      if (!response.ok) {
        showErrorBanner(`Export fehlgeschlagen (Status ${response.status}).`);
        return;
      }

      const blob = await response.blob();
      const objectUrl = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = "trades_export.csv";
      document.body.appendChild(link);
      link.click();
      link.remove();
      // Erst freigeben, wenn der Browser den Download übernommen hat.
      setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
      hideErrorBanner();
    } catch {
      showErrorBanner("Export nicht möglich - Backend nicht erreichbar.");
    } finally {
      els.exportBtn.disabled = false;
    }
  }

  els.exportBtn.addEventListener("click", downloadExport);

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible" && getToken()) {
      fetchStatus();
    }
  });

  // --- Start ---------------------------------------------------------------

  if (!getToken()) {
    showOverlay(false);
  } else {
    startPolling();
  }
})();
