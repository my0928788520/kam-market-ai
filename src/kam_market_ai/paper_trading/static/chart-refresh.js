"use strict";

(() => {
  const REFRESH_INTERVAL_MS = 3000;
  const TOOLTIP_HIDE_DELAY_MS = 6000;
  const REGION_IDS = ["chart-summary", "chart-panel", "chart-footer"];
  const status = document.getElementById("chart-live-status");
  let refreshInFlight = false;
  let tooltipHideTimer = null;
  let activeDrawingTool = null;
  let pendingDrawingPoint = null;
  const drawingStorageKey = `kam-chart-drawings:${window.location.pathname}:${window.location.search}`;
  let manualDrawings = [];
  try {
    manualDrawings = JSON.parse(window.localStorage.getItem(drawingStorageKey) || "[]");
    if (!Array.isArray(manualDrawings)) manualDrawings = [];
  } catch (_error) {
    manualDrawings = [];
  }
  const numberFormatter = new Intl.NumberFormat("zh-TW", { maximumFractionDigits: 0 });

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
    renderManualDrawings();
  };

  const saveManualDrawings = () => {
    try {
      window.localStorage.setItem(drawingStorageKey, JSON.stringify(manualDrawings));
    } catch (_error) {
      // Drawing still works for this page even when browser storage is unavailable.
    }
  };

  const renderManualDrawings = () => {
    const layer = document.querySelector(".chart-manual-drawings");
    if (!layer) return;
    const namespace = "http://www.w3.org/2000/svg";
    const nodes = manualDrawings.map((drawing) => {
      const line = document.createElementNS(namespace, "line");
      line.setAttribute("class", "chart-manual-line");
      for (const attribute of ["x1", "y1", "x2", "y2"]) {
        line.setAttribute(attribute, String(drawing[attribute]));
      }
      return line;
    });
    if (pendingDrawingPoint) {
      const marker = document.createElementNS(namespace, "circle");
      marker.setAttribute("class", "chart-manual-anchor");
      marker.setAttribute("cx", String(pendingDrawingPoint.x));
      marker.setAttribute("cy", String(pendingDrawingPoint.y));
      marker.setAttribute("r", "4");
      nodes.push(marker);
    }
    layer.replaceChildren(...nodes);
    for (const button of document.querySelectorAll("[data-manual-tool]")) {
      button.setAttribute("aria-pressed", String(button.dataset.manualTool === activeDrawingTool));
    }
  };

  const setDrawingHelp = (message) => {
    const help = document.getElementById("chart-drawing-help");
    if (help) help.textContent = message;
  };

  const chartPoint = (event, svg) => {
    const matrix = svg.getScreenCTM();
    if (!matrix) return null;
    const point = svg.createSVGPoint();
    point.x = event.clientX;
    point.y = event.clientY;
    const transformed = point.matrixTransform(matrix.inverse());
    return {
      x: Math.min(980, Math.max(66, transformed.x)),
      y: Math.min(270, Math.max(28, transformed.y)),
    };
  };

  const hideChartTooltip = (panel) => {
    if (tooltipHideTimer !== null) {
      window.clearTimeout(tooltipHideTimer);
      tooltipHideTimer = null;
    }
    if (!panel) return;
    const tooltip = panel.querySelector(".chart-tooltip");
    const crosshair = panel.querySelector(".chart-crosshair");
    if (tooltip) tooltip.hidden = true;
    if (crosshair) crosshair.setAttribute("hidden", "");
  };

  const keepChartTooltipVisible = () => {
    if (tooltipHideTimer === null) return;
    window.clearTimeout(tooltipHideTimer);
    tooltipHideTimer = null;
  };

  const hideChartTooltipLater = (panel) => {
    keepChartTooltipVisible();
    tooltipHideTimer = window.setTimeout(() => {
      tooltipHideTimer = null;
      hideChartTooltip(panel);
    }, TOOLTIP_HIDE_DELAY_MS);
  };

  const isChartTooltipVisible = () => {
    const tooltip = document.querySelector(".chart-tooltip");
    return Boolean(tooltip && !tooltip.hidden);
  };

  const addTooltipLine = (parent, label, value, className = "") => {
    const line = document.createElement("span");
    if (className) line.className = className;
    line.textContent = `${label} ${value}`;
    parent.appendChild(line);
  };

  const showChartTooltip = (zone, clientX, clientY) => {
    keepChartTooltipVisible();
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
    if (panel && !event.relatedTarget?.closest?.(".chart-panel")) hideChartTooltipLater(panel);
  });

  document.addEventListener("focusin", (event) => {
    const zone = event.target.closest?.(".chart-hover-zone");
    if (!zone) return;
    const box = zone.getBoundingClientRect();
    showChartTooltip(zone, box.left + box.width / 2, box.top + box.height / 2);
  });

  document.addEventListener("focusout", (event) => {
    hideChartTooltipLater(event.target.closest?.(".chart-panel"));
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") hideChartTooltip(document.getElementById("chart-panel"));
  });

  document.addEventListener("click", (event) => {
    const toolButton = event.target.closest?.("[data-manual-tool]");
    if (toolButton) {
      const selected = toolButton.dataset.manualTool;
      activeDrawingTool = activeDrawingTool === selected ? null : selected;
      pendingDrawingPoint = null;
      setDrawingHelp(
        activeDrawingTool === "trend"
          ? "請在 K 線圖依序點選斜線的起點與終點"
          : activeDrawingTool === "horizontal"
            ? "請在 K 線圖點選水平線價位"
            : "所有線均由手動畫線；已停止畫線",
      );
      renderManualDrawings();
      return;
    }
    const actionButton = event.target.closest?.("[data-manual-action]");
    if (!actionButton) return;
    if (actionButton.dataset.manualAction === "undo") manualDrawings.pop();
    if (actionButton.dataset.manualAction === "clear") manualDrawings = [];
    pendingDrawingPoint = null;
    saveManualDrawings();
    renderManualDrawings();
  });

  document.addEventListener("pointerdown", (event) => {
    if (!activeDrawingTool) return;
    const svg = event.target.closest?.(".candlestick-chart");
    if (!svg) return;
    const point = chartPoint(event, svg);
    if (!point) return;
    event.preventDefault();
    if (activeDrawingTool === "horizontal") {
      manualDrawings.push({ x1: 66, y1: point.y, x2: 980, y2: point.y });
      saveManualDrawings();
      setDrawingHelp("水平線已完成；可繼續點選其他價位");
    } else if (!pendingDrawingPoint) {
      pendingDrawingPoint = point;
      setDrawingHelp("起點已選，請再點選終點");
    } else {
      manualDrawings.push({
        x1: pendingDrawingPoint.x,
        y1: pendingDrawingPoint.y,
        x2: point.x,
        y2: point.y,
      });
      pendingDrawingPoint = null;
      saveManualDrawings();
      setDrawingHelp("斜線已完成；可繼續畫下一條");
    }
    renderManualDrawings();
  });

  async function refreshChart() {
    if (refreshInFlight || document.hidden || isChartTooltipVisible()) {
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

  renderManualDrawings();
  scheduleNext();
})();
