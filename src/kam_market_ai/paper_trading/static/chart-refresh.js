"use strict";

(() => {
  const REFRESH_INTERVAL_MS = 3000;
  const TOOLTIP_HIDE_DELAY_MS = 6000;
  const REGION_IDS = ["chart-summary", "chart-panel", "chart-footer"];
  const status = document.getElementById("chart-live-status");
  let refreshInFlight = false;
  let tooltipHideTimer = null;
  let activeDrawingTool = null;
  let draftDrawing = null;
  let editingAnchor = null;
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
    const nodes = manualDrawings.flatMap((drawing, drawingIndex) => {
      const line = document.createElementNS(namespace, "line");
      line.setAttribute("class", "chart-manual-line");
      for (const attribute of ["x1", "y1", "x2", "y2"]) {
        line.setAttribute(attribute, String(drawing[attribute]));
      }
      const anchors = ["start", "end"].map((endpoint) => {
        const anchor = document.createElementNS(namespace, "circle");
        const isStart = endpoint === "start";
        anchor.setAttribute("class", "chart-manual-anchor");
        anchor.setAttribute("cx", String(drawing[isStart ? "x1" : "x2"]));
        anchor.setAttribute("cy", String(drawing[isStart ? "y1" : "y2"]));
        anchor.setAttribute("r", "5");
        anchor.dataset.drawingIndex = String(drawingIndex);
        anchor.dataset.endpoint = endpoint;
        return anchor;
      });
      return [line, ...anchors];
    });
    if (draftDrawing) {
      const preview = document.createElementNS(namespace, "line");
      preview.setAttribute("class", "chart-manual-line chart-manual-preview");
      for (const attribute of ["x1", "y1", "x2", "y2"]) {
        preview.setAttribute(attribute, String(draftDrawing[attribute]));
      }
      nodes.push(preview);
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

  const horizontalDrawing = (drawing) => drawing.type === "horizontal" || drawing.y1 === drawing.y2;

  const updateDraftEndpoint = (point) => {
    if (!draftDrawing) return;
    if (activeDrawingTool === "horizontal") {
      draftDrawing.y1 = point.y;
      draftDrawing.y2 = point.y;
    } else {
      draftDrawing.x2 = point.x;
      draftDrawing.y2 = point.y;
    }
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

  document.addEventListener("submit", async (event) => {
    const form = event.target.closest?.(".chart-session-switcher form");
    if (!form) return;
    event.preventDefault();
    const buttons = Array.from(form.closest(".chart-session-switcher").querySelectorAll("button"));
    buttons.forEach((button) => { button.disabled = true; });
    showStatus("切換盤別中…", "refreshing");
    try {
      const response = await fetch(form.action, {
        method: "POST",
        body: new URLSearchParams(new FormData(form)),
        cache: "no-store",
        redirect: "follow",
      });
      if (!response.ok) throw new Error(`session switch failed: ${response.status}`);
      window.location.assign(response.url || "/charts");
    } catch (_error) {
      buttons.forEach((button) => { button.disabled = false; });
      showStatus("盤別切換失敗・請重試", "error");
    }
  });

  document.addEventListener("pointermove", (event) => {
    if (draftDrawing) {
      const svg = document.querySelector(".candlestick-chart");
      const point = svg && chartPoint(event, svg);
      if (point) {
        updateDraftEndpoint(point);
        renderManualDrawings();
      }
      return;
    }
    if (editingAnchor) {
      const point = chartPoint(event, editingAnchor.svg);
      const drawing = manualDrawings[editingAnchor.drawingIndex];
      if (point && drawing) {
        if (horizontalDrawing(drawing)) {
          drawing.y1 = point.y;
          drawing.y2 = point.y;
        } else if (editingAnchor.endpoint === "start") {
          drawing.x1 = point.x;
          drawing.y1 = point.y;
        } else {
          drawing.x2 = point.x;
          drawing.y2 = point.y;
        }
        renderManualDrawings();
      }
      return;
    }
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
    if (event.key === "Escape") {
      draftDrawing = null;
      editingAnchor = null;
      renderManualDrawings();
      hideChartTooltip(document.getElementById("chart-panel"));
      setDrawingHelp(activeDrawingTool ? "拖曳以畫線；放開後完成" : "所有線均由手動畫線");
    }
  });

  document.addEventListener("click", (event) => {
    const toolButton = event.target.closest?.("[data-manual-tool]");
    if (toolButton) {
      const selected = toolButton.dataset.manualTool;
      activeDrawingTool = activeDrawingTool === selected ? null : selected;
      draftDrawing = null;
      setDrawingHelp(
        activeDrawingTool === "trend"
          ? "在 K 線圖按住並拖曳；虛線對齊後放開完成斜線"
          : activeDrawingTool === "horizontal"
            ? "在 K 線圖按住並上下拖曳；虛線對齊價位後放開"
            : "所有線均由手動畫線；已停止畫線",
      );
      renderManualDrawings();
      return;
    }
    const actionButton = event.target.closest?.("[data-manual-action]");
    if (!actionButton) return;
    if (actionButton.dataset.manualAction === "undo") manualDrawings.pop();
    if (actionButton.dataset.manualAction === "clear") manualDrawings = [];
    draftDrawing = null;
    saveManualDrawings();
    renderManualDrawings();
  });

  document.addEventListener("pointerdown", (event) => {
    const anchor = event.target.closest?.(".chart-manual-anchor");
    if (anchor) {
      const svg = anchor.closest(".candlestick-chart");
      if (!svg) return;
      event.preventDefault();
      editingAnchor = {
        drawingIndex: Number(anchor.dataset.drawingIndex),
        endpoint: anchor.dataset.endpoint,
        pointerId: event.pointerId,
        svg,
      };
      anchor.setPointerCapture?.(event.pointerId);
      setDrawingHelp("拖曳端點調整位置；放開後儲存");
      return;
    }
    if (!activeDrawingTool) return;
    const svg = event.target.closest?.(".candlestick-chart");
    if (!svg) return;
    const point = chartPoint(event, svg);
    if (!point) return;
    event.preventDefault();
    draftDrawing = activeDrawingTool === "horizontal"
      ? { type: "horizontal", x1: 66, y1: point.y, x2: 980, y2: point.y, pointerId: event.pointerId }
      : { type: "trend", x1: point.x, y1: point.y, x2: point.x, y2: point.y, pointerId: event.pointerId };
    svg.setPointerCapture?.(event.pointerId);
    setDrawingHelp("拖曳中：虛線為預覽，對齊後放開完成");
    renderManualDrawings();
  });

  document.addEventListener("pointerup", (event) => {
    if (editingAnchor && editingAnchor.pointerId === event.pointerId) {
      editingAnchor = null;
      saveManualDrawings();
      setDrawingHelp("端點已更新；可繼續調整或畫線");
      renderManualDrawings();
      return;
    }
    if (!draftDrawing || draftDrawing.pointerId !== event.pointerId) return;
    const svg = document.querySelector(".candlestick-chart");
    const point = svg && chartPoint(event, svg);
    if (point) updateDraftEndpoint(point);
    const distance = Math.hypot(draftDrawing.x2 - draftDrawing.x1, draftDrawing.y2 - draftDrawing.y1);
    if (draftDrawing.type === "horizontal" || distance >= 4) {
      const { pointerId: _pointerId, ...completedDrawing } = draftDrawing;
      manualDrawings.push(completedDrawing);
      saveManualDrawings();
      setDrawingHelp("線條已完成；拖曳端點可再調整");
    } else {
      setDrawingHelp("拖曳距離太短，未建立線條");
    }
    draftDrawing = null;
    renderManualDrawings();
  });

  document.addEventListener("pointercancel", () => {
    draftDrawing = null;
    editingAnchor = null;
    renderManualDrawings();
    setDrawingHelp(activeDrawingTool ? "拖曳以畫線；放開後完成" : "所有線均由手動畫線");
  });

  async function refreshChart() {
    if (refreshInFlight || document.hidden || isChartTooltipVisible() || draftDrawing || editingAnchor) {
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
