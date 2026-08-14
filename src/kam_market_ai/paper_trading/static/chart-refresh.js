"use strict";

(() => {
  const REFRESH_INTERVAL_MS = 3000;
  const REGION_IDS = ["chart-summary", "chart-panel", "chart-footer"];
  const status = document.getElementById("chart-live-status");
  let refreshInFlight = false;
  const numberFormatter = new Intl.NumberFormat("zh-TW", { maximumFractionDigits: 2 });

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

  const hideChartTooltip = (panel) => {
    if (!panel) return;
    const tooltip = panel.querySelector(".chart-tooltip");
    const crosshair = panel.querySelector(".chart-crosshair");
    if (tooltip) tooltip.hidden = true;
    if (crosshair) crosshair.setAttribute("hidden", "");
  };

  const addTooltipLine = (parent, label, value, className = "") => {
    const line = document.createElement("span");
    if (className) line.className = className;
    line.textContent = `${label} ${value}`;
    parent.appendChild(line);
  };

  const showChartTooltip = (zone, clientX, clientY) => {
    const panel = zone.closest(".chart-panel");
    const svg = zone.ownerSVGElement;
    const tooltip = panel?.querySelector(".chart-tooltip");
    const crosshair = svg?.querySelector(".chart-crosshair");
    if (!panel || !svg || !tooltip || !crosshair) return;

    const format = (value) => numberFormatter.format(Number(value));
    const time = document.createElement("div");
    time.className = "chart-tooltip-time";
    time.textContent = zone.dataset.time || "—";
    const grid = document.createElement("div");
    grid.className = "chart-tooltip-grid";
    addTooltipLine(grid, "開", format(zone.dataset.open));
    addTooltipLine(grid, "高", format(zone.dataset.high));
    addTooltipLine(grid, "低", format(zone.dataset.low));
    addTooltipLine(grid, "收", format(zone.dataset.close));
    const ma = document.createElement("div");
    ma.className = "chart-tooltip-ma";
    ma.textContent = zone.dataset.ma20
      ? `${zone.dataset.maLabel} ${format(zone.dataset.ma20)}`
      : `${zone.dataset.maLabel} 尚未形成`;
    const volume = document.createElement("div");
    volume.textContent = `成交量 ${format(zone.dataset.volume)}`;
    tooltip.replaceChildren(time, grid, ma, volume);
    if (zone.dataset.forming === "true") {
      addTooltipLine(tooltip, "", "形成中・僅供顯示", "chart-tooltip-forming");
    }
    tooltip.hidden = false;

    const panelBox = panel.getBoundingClientRect();
    const tooltipBox = tooltip.getBoundingClientRect();
    const left = Math.min(
      Math.max(8, clientX - panelBox.left + 14),
      Math.max(8, panelBox.width - tooltipBox.width - 8),
    );
    const top = Math.min(
      Math.max(8, clientY - panelBox.top + 14),
      Math.max(8, panelBox.height - tooltipBox.height - 8),
    );
    tooltip.style.left = `${left}px`;
    tooltip.style.top = `${top}px`;

    const vertical = crosshair.querySelector(".chart-crosshair-x");
    const horizontal = crosshair.querySelector(".chart-crosshair-y");
    const matrix = svg.getScreenCTM();
    if (vertical) {
      vertical.setAttribute("x1", zone.dataset.x || "0");
      vertical.setAttribute("x2", zone.dataset.x || "0");
    }
    if (horizontal && matrix) {
      const point = svg.createSVGPoint();
      point.x = clientX;
      point.y = clientY;
      const chartPoint = point.matrixTransform(matrix.inverse());
      horizontal.setAttribute("y1", String(Math.min(356, Math.max(28, chartPoint.y))));
      horizontal.setAttribute("y2", String(Math.min(356, Math.max(28, chartPoint.y))));
    }
    crosshair.removeAttribute("hidden");
  };

  document.addEventListener("pointermove", (event) => {
    const zone = event.target.closest?.(".chart-hover-zone");
    if (zone) showChartTooltip(zone, event.clientX, event.clientY);
  });

  document.addEventListener("pointerout", (event) => {
    const panel = event.target.closest?.(".chart-panel");
    if (panel && !event.relatedTarget?.closest?.(".chart-panel")) hideChartTooltip(panel);
  });

  document.addEventListener("focusin", (event) => {
    const zone = event.target.closest?.(".chart-hover-zone");
    if (!zone) return;
    const box = zone.getBoundingClientRect();
    showChartTooltip(zone, box.left + box.width / 2, box.top + box.height / 2);
  });

  document.addEventListener("focusout", (event) => {
    hideChartTooltip(event.target.closest?.(".chart-panel"));
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") hideChartTooltip(document.getElementById("chart-panel"));
  });

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
