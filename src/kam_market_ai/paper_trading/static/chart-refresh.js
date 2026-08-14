"use strict";

(() => {
  const REFRESH_INTERVAL_MS = 3000;
  const REGION_IDS = ["chart-summary", "chart-panel", "chart-footer"];
  const status = document.getElementById("chart-live-status");
  let refreshInFlight = false;

  const scheduleNext = () => {
    window.setTimeout(refreshChart, REFRESH_INTERVAL_MS);
  };

  const showStatus = (message, state) => {
    if (!status) return;
    status.textContent = message;
    status.dataset.state = state;
  };

  const replaceRegions = (documentFromServer) => {
    for (const id of REGION_IDS) {
      const current = document.getElementById(id);
      const replacement = documentFromServer.getElementById(id);
      if (!current || !replacement) {
        throw new Error(`missing chart refresh region: ${id}`);
      }
      current.replaceChildren(...Array.from(replacement.childNodes).map((node) => document.importNode(node, true)));
    }
  };

  async function refreshChart() {
    if (refreshInFlight || document.hidden) {
      scheduleNext();
      return;
    }
    refreshInFlight = true;
    showStatus("更新中…", "refreshing");
    try {
      const response = await fetch(window.location.href, {
        cache: "no-store",
        headers: { "X-KAM-Chart-Refresh": "1" },
      });
      if (!response.ok) throw new Error(`chart refresh failed: ${response.status}`);
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
