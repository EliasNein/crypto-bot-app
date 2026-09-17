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
    overviewTiles: document.getElementById("overview-tiles"),
    unrealizedBlock: document.getElementById("unrealized-block"),
    overlay: document.getElementById("login-overlay"),
    inputToken: document.getElementById("input-token"),
    inputBase: document.getElementById("input-base"),
    loginError: document.getElementById("login-error"),
    loginSave: document.getElementById("login-save"),
    settingsBtn: document.getElementById("settings-btn"),
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

  function fmtRelativeTime(iso) {
    if (!iso) return "keine Aktivität";
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return iso;
    const diffMs = Date.now() - date.getTime();
    const diffMin = Math.round(diffMs / 60000);
    if (diffMin < 1) return "gerade eben";
    if (diffMin < 60) return `vor ${diffMin} Min.`;
    const diffH = Math.round(diffMin / 60);
    if (diffH < 24) return `vor ${diffH} Std.`;
    const diffD = Math.round(diffH / 24);
    return `vor ${diffD} Tag(en)`;
  }

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function metric(label, value, cls) {
    const wrap = el("div", "metric");
    wrap.appendChild(el("div", "label", label));
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

  function buildCard(title, data, renderBody) {
    const card = el("div", "card");
    const header = el("div", "card-header");
    header.appendChild(el("div", "card-title", title));
    header.appendChild(badge(data.status));
    card.appendChild(header);

    if (data.status !== "ok") {
      card.appendChild(el("div", "no-data-text", data.error || "Keine Daten verfügbar."));
      return card;
    }

    renderBody(card);

    if (data.last_activity !== undefined) {
      const activity = el("div", "last-activity", `Letzte Aktivität: ${fmtRelativeTime(data.last_activity)}`);
      activity.title = data.last_activity || "";
      card.appendChild(activity);
    }

    return card;
  }

  function buildPositionRow(parts) {
    const row = el("div", "position");
    const left = el("span");
    left.textContent = parts.join(" · ");
    row.appendChild(left);
    return row;
  }

  function cardDca(data) {
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
        const list = el("div", "positions");
        for (const p of data.open_positions.slice(-5).reverse()) {
          list.appendChild(
            buildPositionRow([p.symbol, `${fmtPrice(p.price)} USDT`, fmtQty(p.quantity)])
          );
        }
        card.appendChild(list);
      }
    });
  }

  function cardGrid(data) {
    return buildCard("Grid-Bot", data, (card) => {
      const metrics = el("div", "metrics-row");
      metrics.appendChild(metric("Offen", String(data.metrics.open_positions)));
      metrics.appendChild(metric("Geschlossen", String(data.metrics.closed_positions)));
      metrics.appendChild(
        metric("Realisiert", `${fmtPrice(data.metrics.realized_pnl)} USDT`, pnlClass(data.metrics.realized_pnl))
      );
      card.appendChild(metrics);

      if (data.open_positions.length) {
        const list = el("div", "positions");
        for (const p of data.open_positions) {
          const row = buildPositionRow([
            `Stufe ${p.level_index}`,
            `Kauf ${fmtPrice(p.buy_price)}`,
            `Ziel ${fmtPrice(p.target_sell_price)}`,
          ]);
          if (p.dry_run) {
            row.appendChild(el("span", "dry-run-tag", "DRY-RUN"));
          }
          list.appendChild(row);
        }
        card.appendChild(list);
      }
    });
  }

  function cardTrend(data) {
    return buildCard("Trend-Bot", data, (card) => {
      const metrics = el("div", "metrics-row");
      metrics.appendChild(metric("Offen", String(data.metrics.open_trades)));
      metrics.appendChild(metric("Geschlossen", String(data.metrics.closed_trades)));
      metrics.appendChild(
        metric("Realisiert", `${fmtPrice(data.metrics.realized_pnl)} USDT`, pnlClass(data.metrics.realized_pnl))
      );
      card.appendChild(metrics);

      if (data.open_positions.length) {
        const list = el("div", "positions");
        for (const p of data.open_positions) {
          const row = buildPositionRow([
            `Einstieg ${fmtPrice(p.entry_price)}`,
            `Menge ${fmtQty(p.quantity)}`,
            p.stop_loss_order_id ? "SL gesetzt" : "kein SL",
          ]);
          if (p.dry_run) {
            row.appendChild(el("span", "dry-run-tag", "DRY-RUN"));
          }
          list.appendChild(row);
        }
        card.appendChild(list);
      }
    });
  }

  function cardAllocator(data) {
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
    });
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

  function renderOverview(overview) {
    els.overviewTiles.innerHTML = "";

    const gainTile = el("div", "tile gain");
    gainTile.appendChild(el("div", "tile-label", "Gesamtgewinn"));
    gainTile.appendChild(el("div", "tile-value", `${fmtPrice(overview.gesamtgewinn)} USDT`));
    els.overviewTiles.appendChild(gainTile);

    const lossTile = el("div", "tile loss");
    lossTile.appendChild(el("div", "tile-label", "Gesamtverlust"));
    lossTile.appendChild(el("div", "tile-value", `${fmtPrice(overview.gesamtverlust)} USDT`));
    els.overviewTiles.appendChild(lossTile);

    const unrealized = overview["unrealisiert_geschätzt"] || {};

    els.unrealizedBlock.innerHTML = "";
    els.unrealizedBlock.appendChild(el("div", "unrealized-title", "Unrealisiert (geschätzt)"));
    const rows = el("div", "unrealized-rows");
    for (const key of ["dca", "grid", "trend"]) {
      const row = el("div", "unrealized-row");
      row.appendChild(el("span", "bot-name", BOT_LABELS[key]));
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

  function render(data) {
    renderOverview(data.overview);

    els.cards.innerHTML = "";
    els.cards.appendChild(cardDca(data.dca));
    els.cards.appendChild(cardGrid(data.grid));
    els.cards.appendChild(cardTrend(data.trend));
    els.cards.appendChild(cardAllocator(data.allocator));
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
    hideOverlay();
    startPolling();
  });

  els.settingsBtn.addEventListener("click", () => {
    showOverlay(true);
  });

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
