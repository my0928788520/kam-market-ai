"use strict";

(() => {
  const REFRESH_INTERVAL_MS = 3000;
  const REGION_SELECTORS = [
    ".header-market-status",
    ".market-selector",
    ".market-snapshot-fields",
    ".market-status-line",
    ".dashboard",
    "main > footer",
  ];
  const status = document.getElementById("dashboard-live-status");
  let refreshInFlight = false;

  const placeAccountMetrics = () => {
    const metrics = document.querySelector("main > footer .footer-metrics");
    const matching = document.querySelector(".dashboard .matching");
    if (metrics && matching) matching.append(metrics);
  };

  const scheduleNext = () => window.setTimeout(refreshDashboard, REFRESH_INTERVAL_MS);

  const showStatus = (message, state) => {
    if (!status) return;
    status.textContent = message;
    status.dataset.state = state;
  };

  const replaceRegions = (nextDocument) => {
    for (const selector of REGION_SELECTORS) {
      const current = document.querySelector(selector);
      const replacement = nextDocument.querySelector(selector);
      if (!current && !replacement) continue;
      if (!current || !replacement) {
        throw new Error(`missing dashboard refresh region: ${selector}`);
      }
      const imported = document.importNode(replacement, true);
      if (selector === ".dashboard") {
        const currentCard = current.querySelector(".current-analysis-card");
        const nextCard = imported.querySelector(".current-analysis-card");
        const unchanged =
          currentCard &&
          nextCard &&
          currentCard.dataset.analysisHash === nextCard.dataset.analysisHash;
        if (unchanged) {
          nextCard.replaceWith(currentCard);
        }
      }
      current.replaceWith(imported);
    }
    placeAccountMetrics();
  };

  async function refreshDashboard() {
    if (refreshInFlight || document.hidden) {
      scheduleNext();
      return;
    }
    refreshInFlight = true;
    showStatus("更新中…", "refreshing");
    try {
      const response = await fetch(window.location.href, {
        cache: "no-store",
        headers: { "X-KAM-Dashboard-Refresh": "1" },
      });
      if (!response.ok) throw new Error(`dashboard refresh failed: ${response.status}`);
      const nextDocument = new DOMParser().parseFromString(await response.text(), "text/html");
      replaceRegions(nextDocument);
      showStatus(`已更新 ${new Date().toLocaleTimeString("zh-TW", { hour12: false })}・每 3 秒`, "ready");
    } catch (_error) {
      showStatus("更新暫時中斷・將自動重試", "error");
    } finally {
      refreshInFlight = false;
      scheduleNext();
    }
  }

  placeAccountMetrics();
  scheduleNext();
})();
