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
      current.replaceWith(document.importNode(replacement, true));
    }
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

  scheduleNext();
})();
