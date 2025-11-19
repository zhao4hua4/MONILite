"""HTTP server for MONILite."""

from __future__ import annotations

from flask import Flask, Response, jsonify, request

from .metrics import MetricsCollector
from .storage import HistoryStore


def create_app(collector: MetricsCollector, history_store: HistoryStore | None = None) -> Flask:
    """Create a Flask application bound to the provided collector."""

    app = Flask(__name__)
    refresh_ms = max(int(collector.get_interval() * 1000), 1000)
    app.config["UI_REFRESH_INTERVAL_MS"] = refresh_ms
    app.config["HISTORY_ENABLED"] = history_store is not None

    @app.get("/api/v1/live")
    def live_metrics():
        return jsonify(collector.get_snapshot())

    @app.get("/")
    def dashboard():
        return _render_index(
            refresh_ms,
            history_enabled=history_store is not None,
        )

    @app.get("/api/v1/settings")
    def get_settings():
        return jsonify({"interval": collector.get_interval()})

    @app.post("/api/v1/settings")
    def update_settings():
        payload = request.get_json(silent=True) or {}
        interval = payload.get("interval")
        try:
            interval_value = float(interval)
        except (TypeError, ValueError):
            return jsonify({"error": "interval must be a positive number"}), 400
        if interval_value <= 0:
            return jsonify({"error": "interval must be greater than zero"}), 400
        collector.set_interval(interval_value)
        return jsonify({"interval": collector.get_interval()})

    @app.get("/api/v1/history")
    def history():
        if history_store is None:
            return jsonify({"error": "history storage disabled"}), 503
        window = request.args.get("window", "24h")
        try:
            points = history_store.fetch_window(window)
        except ValueError:
            return jsonify({"error": "invalid window"}), 400
        return jsonify({"window": window, "points": points})

    return app


def _render_index(refresh_interval_ms: int, history_enabled: bool) -> Response:
    html = (
        _INDEX_HTML.replace("__REFRESH_INTERVAL_MS__", str(refresh_interval_ms))
        .replace("__HISTORY_ENABLED__", "true" if history_enabled else "false")
    )
    return Response(html, mimetype="text/html; charset=utf-8")


_INDEX_HTML = """<!doctype html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\" />
    <title>MONILite Dashboard</title>
    <style>
      :root {
        font-family: system-ui, -apple-system, BlinkMacSystemFont, \"Segoe UI\", sans-serif;
        background-color: #0b0c10;
        color: #f7f7f7;
      }
      body {
        margin: 0;
        padding: 2rem;
        line-height: 1.6;
      }
      h1 {
        margin-top: 0;
        font-size: 2.2rem;
        letter-spacing: 0.02em;
      }
      .metrics-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
        gap: 1.25rem;
        margin: 1.5rem 0;
      }
      .metric {
        background: #161920;
        border-radius: 12px;
        padding: 1.25rem;
        box-shadow: 0 15px 35px rgba(0, 0, 0, 0.2);
        border: 1px solid rgba(255, 255, 255, 0.05);
      }
      .metric-header {
        display: flex;
        flex-direction: column;
        gap: 0.1rem;
        margin-bottom: 0.75rem;
      }
      .metric-header h2 {
        margin: 0;
        font-size: 1.25rem;
      }
      .metric-header .hint {
        margin: 0;
        font-size: 0.85rem;
        color: #b3b9c6;
        line-height: 1.3;
      }
      .controls {
        display: flex;
        align-items: center;
        gap: 0.75rem;
        flex-wrap: wrap;
        margin: 0.5rem 0 1.5rem;
      }
      .controls label {
        font-size: 0.9rem;
        color: #b3b9c6;
      }
      .controls select {
        background: #11131a;
        color: #f7f7f7;
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 8px;
        padding: 0.35rem 0.75rem;
      }
      .history-controls label {
        font-size: 0.85rem;
        color: #b3b9c6;
      }
      .history-controls select,
      .history-controls input[type="range"] {
        background: #11131a;
        color: #f7f7f7;
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 8px;
        padding: 0.2rem 0.5rem;
      }
      .history-controls input[type="range"] {
        -webkit-appearance: none;
        width: 120px;
        padding: 0;
        height: 6px;
      }
      .history-controls input[type="range"]::-webkit-slider-thumb {
        -webkit-appearance: none;
        width: 12px;
        height: 12px;
        border-radius: 50%;
        background: #4fc3f7;
        cursor: pointer;
      }
      .history-controls input[type="range"]::-moz-range-thumb {
        width: 12px;
        height: 12px;
        border-radius: 50%;
        background: #4fc3f7;
        cursor: pointer;
      }
      .status {
        font-size: 0.9rem;
        opacity: 0.8;
      }
      .value {
        font-size: 1.1rem;
      }
      .subtext {
        display: block;
        font-size: 0.9rem;
        color: #b3b9c6;
        margin-top: 0.25rem;
      }
      ul.devices {
        padding-left: 1.1rem;
        margin: 0;
      }
      ul.devices li {
        margin-bottom: 0.35rem;
      }
      .history-block {
        margin-top: 2rem;
      }
      .history-header {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        justify-content: space-between;
        gap: 1rem;
      }
      .history-controls {
        display: flex;
        align-items: center;
        gap: 0.5rem;
      }
      .history-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
        gap: 1rem;
        margin-top: 1rem;
      }
      canvas.history-chart {
        width: 100%;
        height: 220px;
        background: #11131a;
        border-radius: 12px;
        border: 1px solid rgba(255, 255, 255, 0.05);
      }
      .history-tooltip {
        position: fixed;
        pointer-events: none;
        background: rgba(15, 17, 26, 0.9);
        color: #f7f7f7;
        padding: 0.35rem 0.5rem;
        border-radius: 6px;
        font-size: 0.85rem;
        border: 1px solid rgba(255, 255, 255, 0.1);
        transform: translate(-50%, -120%);
        opacity: 0;
        transition: opacity 0.1s ease;
        z-index: 10;
      }
      pre {
        background: #11131a;
        padding: 1rem;
        border-radius: 10px;
        overflow-x: auto;
      }
    </style>
  </head>
  <body>
    <h1>MONILite</h1>
    <p class=\"status\">Refreshing every <span id=\"refresh\"></span> seconds. Last update: <span id=\"timestamp\">loading…</span></p>
    <div class=\"controls\">
      <label for=\"interval-control\">Sampling interval</label>
      <select id=\"interval-control\">
        <option value=\"1\">1s</option>
        <option value=\"2\">2s</option>
        <option value=\"5\">5s</option>
        <option value=\"10\">10s</option>
        <option value=\"15\">15s</option>
        <option value=\"30\">30s</option>
        <option value=\"60\">60s</option>
      </select>
      <span id=\"interval-status\" class=\"subtext\"></span>
    </div>
    <div class=\"metrics-grid\">
      <section class=\"metric\">
        <div class=\"metric-header\">
          <h2>CPU</h2>
          <p class=\"hint\">Utilization and load average (1m · 5m · 15m run queue).</p>
        </div>
        <div id=\"cpu\" class=\"value\">loading…</div>
      </section>
      <section class=\"metric\">
        <div class=\"metric-header\">
          <h2>Memory</h2>
          <p class=\"hint\">Total vs used physical memory, scaled automatically.</p>
        </div>
        <div id=\"memory\" class=\"value\">loading…</div>
      </section>
      <section class=\"metric\">
        <div class=\"metric-header\">
          <h2>Disk</h2>
          <p class=\"hint\">Root filesystem usage with free space summary.</p>
        </div>
        <div id=\"disk\" class=\"value\">loading…</div>
      </section>
      <section class=\"metric\">
        <div class=\"metric-header\">
          <h2>GPU</h2>
          <p class=\"hint\">Per-device utilization, VRAM, temperature, and power.</p>
        </div>
        <div id=\"gpu\" class=\"value\">loading…</div>
      </section>
    </div>
    <section class=\"history-block\" id=\"history-block\">
      <div class=\"history-header\">
        <h2>History trends</h2>
        <div class=\"history-controls\">
          <label for=\"history-window\">Window</label>
          <select id=\"history-window\">
            <option value=\"1h\">Last hour</option>
            <option value=\"24h\">Last 24 hours</option>
            <option value=\"7d\">Last 7 days</option>
          </select>
          <label for=\"history-smoothing\">Smoothing</label>
          <input type=\"range\" id=\"history-smoothing\" min=\"0\" max=\"0.99\" step=\"0.01\" value=\"0\" />
          <span id=\"history-smoothing-label\" class=\"subtext\">0.00</span>
        </div>
        <span id=\"history-status\" class=\"subtext\"></span>
      </div>
      <div class=\"history-grid\">
        <canvas id=\"history-cpu\" class=\"history-chart\"></canvas>
        <canvas id=\"history-memory\" class=\"history-chart\"></canvas>
        <canvas id=\"history-disk\" class=\"history-chart\"></canvas>
        <canvas id=\"history-gpu\" class=\"history-chart\"></canvas>
      </div>
    </section>
    <section>
      <details>
        <summary>Raw payload</summary>
        <pre id=\"raw\"></pre>
      </details>
    </section>

    <script>
      const REFRESH_MS = __REFRESH_INTERVAL_MS__;
      const HISTORY_ENABLED = __HISTORY_ENABLED__;
      const refreshEl = document.getElementById("refresh");
      const timestampEl = document.getElementById("timestamp");
      const cpuEl = document.getElementById("cpu");
      const memEl = document.getElementById("memory");
      const diskEl = document.getElementById("disk");
      const gpuEl = document.getElementById("gpu");
      const rawEl = document.getElementById("raw");
      const intervalSelect = document.getElementById("interval-control");
      const intervalStatus = document.getElementById("interval-status");
      const historyBlock = document.getElementById("history-block");
      const historyWindowSelect = document.getElementById("history-window");
      const historyStatus = document.getElementById("history-status");
      const cpuHistoryCanvas = document.getElementById("history-cpu");
      const memoryHistoryCanvas = document.getElementById("history-memory");
      const diskHistoryCanvas = document.getElementById("history-disk");
      const gpuHistoryCanvas = document.getElementById("history-gpu");
      const chartState = new Map();
      const historyTooltip = document.createElement('div');
      historyTooltip.className = 'history-tooltip';
      document.body.appendChild(historyTooltip);
      const historySmoothingInput = document.getElementById("history-smoothing");
      const historySmoothingLabel = document.getElementById("history-smoothing-label");
      let historySmoothing = historySmoothingInput ? Number(historySmoothingInput.value) || 0 : 0;
      if (historySmoothingLabel) {
        historySmoothingLabel.textContent = Number(historySmoothing).toFixed(2);
      }
      let lastHistoryPoints = [];

      let refreshMs = Math.max(REFRESH_MS, 1000);
      let refreshTimerId = null;
      const HISTORY_REFRESH_MS = 20000;
      let historyTimerId = null;
      let historyWindow = historyWindowSelect ? historyWindowSelect.value : '24h';
      let lastHistoryRefresh = 0;
      let historyRequestInFlight = false;

      function formatNumber(value, digits) {
        if (typeof value !== "number" || Number.isNaN(value)) {
          return "n/a";
        }
        if (typeof digits === "number") {
          return value.toFixed(digits);
        }
        return String(value);
      }

      function formatSizeMB(value) {
        if (typeof value !== "number" || Number.isNaN(value)) {
          return "n/a";
        }
        if (value >= 1024 * 1024) {
          return (value / (1024 * 1024)).toFixed(2) + ' TB';
        }
        if (value >= 1024) {
          return (value / 1024).toFixed(2) + ' GB';
        }
        return value.toFixed(0) + ' MB';
      }

      function ensureIntervalOption(seconds) {
        const value = seconds.toString();
        const exists = Array.from(intervalSelect.options).some(function (option) {
          return option.value === value;
        });
        if (!exists) {
          const option = document.createElement('option');
          option.value = value;
          option.textContent = value + 's';
          intervalSelect.appendChild(option);
        }
      }

      function updateRefreshDisplay(seconds) {
        refreshEl.textContent = seconds.toFixed(1);
        intervalStatus.textContent = 'Sampling every ' + seconds.toFixed(1) + 's';
      }

      function scheduleRefresh() {
        if (refreshTimerId) {
          clearInterval(refreshTimerId);
        }
        refreshTimerId = setInterval(fetchMetrics, refreshMs);
      }

      function setCurrentInterval(seconds) {
        const normalized = Math.max(Number(seconds) || 1, 0.5);
        const rounded = Math.round(normalized * 10) / 10;
        refreshMs = rounded * 1000;
        ensureIntervalOption(rounded);
        intervalSelect.value = rounded.toString();
        updateRefreshDisplay(rounded);
        scheduleRefresh();
      }

      function applySmoothing(series, smoothingFactor) {
        const factor = Math.max(0, Math.min(0.99, Number(smoothingFactor) || 0));
        if (factor <= 0) {
          return series.slice();
        }
        const alpha = Math.max(0.01, 1 - factor);
        let prev = null;
        return series.map(point => {
          const value = Number(point.value);
          if (!Number.isFinite(value)) {
            prev = null;
            return { ts: point.ts, value: NaN };
          }
          prev = prev === null ? value : alpha * value + (1 - alpha) * prev;
          return { ts: point.ts, value: prev };
        });
      }

      function showTooltip(text, clientX, clientY) {
        if (!historyTooltip) {
          return;
        }
        historyTooltip.textContent = text;
        historyTooltip.style.left = `${clientX}px`;
        historyTooltip.style.top = `${clientY - 10}px`;
        historyTooltip.style.opacity = '1';
      }

      function hideTooltip() {
        if (historyTooltip) {
          historyTooltip.style.opacity = '0';
        }
      }

      function drawLineChart(canvas, rawSeries, smoothedSeries, color, label, smoothingFactor, highlightTs) {
        if (!canvas) {
          return;
        }
        const ctx = canvas.getContext('2d');
        if (!ctx) {
          return;
        }
        const dpr = window.devicePixelRatio || 1;
        const width = canvas.clientWidth * dpr;
        const height = canvas.clientHeight * dpr;
        if (!width || !height) {
          return;
        }
        canvas.width = width;
        canvas.height = height;
        ctx.clearRect(0, 0, width, height);

        const pairs = [];
        for (let i = 0; i < rawSeries.length; i++) {
          const ts = rawSeries[i]?.ts;
          const rawValue = Number(rawSeries[i]?.value);
          const smoothValue = Number(smoothedSeries[i]?.value);
          if (!Number.isFinite(rawValue) && !Number.isFinite(smoothValue)) {
            continue;
          }
          pairs.push({ ts, raw: rawValue, smooth: smoothValue });
        }

        if (!pairs.length) {
          ctx.fillStyle = '#b3b9c6';
          ctx.font = `${14 * dpr}px sans-serif`;
          ctx.fillText('No data', 10 * dpr, 20 * dpr);
          chartState.set(canvas, {
            label,
            color,
            smoothingFactor,
            rawSeries,
            smoothedSeries,
            chartPoints: [],
            rawChartPoints: [],
          });
          return;
        }

        const times = pairs.map(point => point.ts);
        const values = pairs.map(point => Number.isFinite(point.smooth) ? point.smooth : point.raw);
        const minT = Math.min(...times);
        const maxT = Math.max(...times);
        const minV = Math.min(...values);
        const maxV = Math.max(...values);
        const rangeV = maxV - minV || 1;
        const rangeT = maxT - minT || 1;

        const marginLeft = 45 * dpr;
        const marginRight = 15 * dpr;
        const marginTop = 20 * dpr;
        const marginBottom = 30 * dpr;
        const plotWidth = Math.max(width - marginLeft - marginRight, 1);
        const plotHeight = Math.max(height - marginTop - marginBottom, 1);

        ctx.strokeStyle = 'rgba(255, 255, 255, 0.15)';
        ctx.lineWidth = 1 * dpr;
        ctx.beginPath();
        ctx.moveTo(marginLeft, marginTop);
        ctx.lineTo(marginLeft, height - marginBottom);
        ctx.lineTo(width - marginRight, height - marginBottom);
        ctx.stroke();

        const yTicks = 4;
        ctx.fillStyle = '#b3b9c6';
        ctx.font = `${10 * dpr}px sans-serif`;
        for (let i = 0; i <= yTicks; i++) {
          const fraction = i / yTicks;
          const value = minV + rangeV * (1 - fraction);
          const y = marginTop + plotHeight * fraction;
          ctx.beginPath();
          ctx.moveTo(marginLeft - 4 * dpr, y);
          ctx.lineTo(marginLeft, y);
          ctx.stroke();
          ctx.fillText(value.toFixed(1), Math.max(2 * dpr, marginLeft - 40 * dpr), y + 3 * dpr);
        }

        const xTicks = 4;
        for (let i = 0; i <= xTicks; i++) {
          const fraction = i / xTicks;
          const ts = minT + rangeT * fraction;
          const x = marginLeft + plotWidth * fraction;
          ctx.beginPath();
          ctx.moveTo(x, height - marginBottom);
          ctx.lineTo(x, height - marginBottom + 4 * dpr);
          ctx.stroke();
          const text = new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
          ctx.fillText(text, x - 24 * dpr, height - 10 * dpr);
        }

        const smoothedPoints = [];
        const rawPoints = [];
        const getCoords = (ts, value) => {
          const x = marginLeft + ((ts - minT) / rangeT) * plotWidth;
          const y = height - marginBottom - ((value - minV) / rangeV) * plotHeight;
          return { x, y };
        };

        pairs.forEach(pair => {
          if (Number.isFinite(pair.smooth)) {
            const coords = getCoords(pair.ts, pair.smooth);
            smoothedPoints.push({ ts: pair.ts, value: pair.smooth, ...coords });
          }
          if (Number.isFinite(pair.raw)) {
            const coordsRaw = getCoords(pair.ts, pair.raw);
            rawPoints.push({ ts: pair.ts, value: pair.raw, ...coordsRaw });
          }
        });

        const drawPath = (pointsArray, strokeStyle, lineWidth, alpha = 1) => {
          if (!pointsArray.length) {
            return;
          }
          ctx.save();
          ctx.globalAlpha = alpha;
          ctx.strokeStyle = strokeStyle;
          ctx.lineWidth = lineWidth;
          ctx.beginPath();
          pointsArray.forEach((point, index) => {
            if (index === 0) {
              ctx.moveTo(point.x, point.y);
            } else {
              ctx.lineTo(point.x, point.y);
            }
          });
          ctx.stroke();
          ctx.restore();
        };

        if (Number(smoothingFactor) > 0 && rawPoints.length) {
          drawPath(rawPoints, color, 1.5 * dpr, 0.35);
        }

        drawPath(smoothedPoints, color, 2 * dpr, 1);

        if (typeof highlightTs === 'number') {
          const smoothedHighlight = smoothedPoints.find(point => point.ts === highlightTs);
          if (smoothedHighlight) {
            ctx.fillStyle = color;
            ctx.beginPath();
            ctx.arc(smoothedHighlight.x, smoothedHighlight.y, 4 * dpr, 0, Math.PI * 2);
            ctx.fill();
            ctx.strokeStyle = '#ffffff';
            ctx.lineWidth = 1 * dpr;
            ctx.stroke();
          }
          if (Number(smoothingFactor) > 0) {
            const rawHighlight = rawPoints.find(point => point.ts === highlightTs);
            if (rawHighlight) {
              ctx.save();
              ctx.globalAlpha = 0.6;
              ctx.fillStyle = color;
              ctx.beginPath();
              ctx.arc(rawHighlight.x, rawHighlight.y, 3 * dpr, 0, Math.PI * 2);
              ctx.fill();
              ctx.restore();
            }
          }
        }

        ctx.fillStyle = '#b3b9c6';
        ctx.font = `${13 * dpr}px sans-serif`;
        ctx.fillText(label, marginLeft, marginTop - 6 * dpr);

        chartState.set(canvas, {
          label,
          color,
          smoothingFactor,
          rawSeries,
          smoothedSeries,
          chartPoints: smoothedPoints,
          rawChartPoints: rawPoints,
        });
      }

      function renderHistory(points) {
        if (!cpuHistoryCanvas || !memoryHistoryCanvas) {
          return;
        }
        lastHistoryPoints = Array.isArray(points) ? points.slice() : [];
        const cpuSeries = [];
        const memSeries = [];
        const diskSeries = [];
        const gpuSeries = [];
        points.forEach(point => {
          const ts = Date.parse(point.timestamp);
          if (!Number.isFinite(ts)) {
            return;
          }
          const cpuVal = point.cpu && point.cpu.utilization_pct;
          const memVal = point.memory && point.memory.utilization_pct;
          const diskVal = point.disk && point.disk.utilization_pct;
          const gpuVal = point.gpu && point.gpu.utilization_pct;
          cpuSeries.push({ ts, value: Number(cpuVal) });
          memSeries.push({ ts, value: Number(memVal) });
          diskSeries.push({ ts, value: Number(diskVal) });
          gpuSeries.push({ ts, value: Number(gpuVal) });
        });
        const smoothing = Math.max(0, Math.min(0.99, Number(historySmoothing) || 0));
        drawLineChart(
          cpuHistoryCanvas,
          cpuSeries,
          applySmoothing(cpuSeries, smoothing),
          '#4fc3f7',
          'CPU util %',
          smoothing,
          null,
        );
        drawLineChart(
          memoryHistoryCanvas,
          memSeries,
          applySmoothing(memSeries, smoothing),
          '#ffb347',
          'Memory util %',
          smoothing,
          null,
        );
        drawLineChart(
          diskHistoryCanvas,
          diskSeries,
          applySmoothing(diskSeries, smoothing),
          '#90caf9',
          'Disk util %',
          smoothing,
          null,
        );
        drawLineChart(
          gpuHistoryCanvas,
          gpuSeries,
          applySmoothing(gpuSeries, smoothing),
          '#ce93d8',
          'GPU util %',
          smoothing,
          null,
        );
      }

      async function loadHistory(windowValue) {
        if (!HISTORY_ENABLED) {
          if (historyBlock) {
            historyBlock.style.display = 'none';
          }
          return;
        }
        if (historyRequestInFlight) {
          return;
        }
        historyRequestInFlight = true;
        if (historyStatus) {
          historyStatus.textContent = 'Loading…';
        }
        try {
          const response = await fetch(`/api/v1/history?window=${encodeURIComponent(windowValue)}`, { cache: 'no-store' });
          const payload = await response.json();
          if (!response.ok) {
            throw new Error(payload.error || 'Failed to load history');
          }
          renderHistory(payload.points || []);
          lastHistoryRefresh = Date.now();
          if (historyStatus) {
            historyStatus.textContent = `${payload.points?.length ?? 0} points`;
          }
        } catch (error) {
          if (historyStatus) {
            historyStatus.textContent = error.message;
          }
        } finally {
          historyRequestInFlight = false;
        }
      }

      function scheduleHistoryRefresh() {
        if (historyTimerId) {
          clearInterval(historyTimerId);
        }
        historyTimerId = setInterval(() => {
          loadHistory(historyWindow);
        }, HISTORY_REFRESH_MS);
      }

      async function loadSettings() {
        try {
          const response = await fetch('/api/v1/settings', { cache: 'no-store' });
          const payload = await response.json();
          if (response.ok && typeof payload.interval !== 'undefined') {
            setCurrentInterval(payload.interval);
          }
        } catch (error) {
          intervalStatus.textContent = 'Using default interval';
        }
      }

      async function applyInterval(seconds) {
        intervalStatus.textContent = 'Updating…';
        try {
          const response = await fetch('/api/v1/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ interval: seconds }),
          });
          const payload = await response.json().catch(() => ({}));
          if (!response.ok) {
            throw new Error(payload.error || 'Failed to update interval');
          }
          setCurrentInterval(payload.interval);
          intervalStatus.textContent = 'Sampling every ' + Number(payload.interval).toFixed(1) + 's';
          fetchMetrics();
          loadHistory(historyWindow);
        } catch (error) {
          intervalStatus.textContent = error.message;
        }
      }

      intervalSelect.addEventListener('change', function (event) {
        const seconds = Number(event.target.value);
        if (!Number.isFinite(seconds) || seconds <= 0) {
          intervalStatus.textContent = 'Choose a valid interval';
          return;
        }
        applyInterval(seconds);
      });

      if (historyWindowSelect) {
        historyWindowSelect.addEventListener('change', function (event) {
          const value = event.target.value;
          historyWindow = value;
          loadHistory(historyWindow);
          scheduleHistoryRefresh();
        });
      }

      if (historySmoothingInput) {
        historySmoothingInput.addEventListener('input', function (event) {
          historySmoothing = Math.max(0, Number(event.target.value) || 0);
          if (historySmoothingLabel) {
            historySmoothingLabel.textContent = Number(historySmoothing).toFixed(2);
          }
          renderHistory(lastHistoryPoints);
        });
      }

      [cpuHistoryCanvas, memoryHistoryCanvas, diskHistoryCanvas, gpuHistoryCanvas].forEach(canvas => {
        if (!canvas) {
          return;
        }
        canvas.addEventListener('mousemove', handleHistoryHover);
        canvas.addEventListener('mouseleave', handleHistoryLeave);
      });

      async function fetchMetrics() {
        try {
          const response = await fetch('/api/v1/live', { cache: 'no-store' });
          if (!response.ok) {
            throw new Error('Request failed: ' + response.status);
          }
          const payload = await response.json();
          renderMetrics(payload);
          maybeRefreshHistory();
        } catch (error) {
          rawEl.textContent = String(error);
        }
      }

      function maybeRefreshHistory() {
        if (!HISTORY_ENABLED) {
          return;
        }
        if (Date.now() - lastHistoryRefresh >= HISTORY_REFRESH_MS) {
          loadHistory(historyWindow);
        }
      }

      function handleHistoryHover(event) {
        const canvas = event.currentTarget;
        const state = chartState.get(canvas);
        const smoothedPoints = state && state.chartPoints ? state.chartPoints : [];
        if (!state || !smoothedPoints.length) {
          hideTooltip();
          return;
        }
        const rect = canvas.getBoundingClientRect();
        const dpr = window.devicePixelRatio || 1;
        const pointerX = (event.clientX - rect.left) * dpr;
        let nearest = smoothedPoints[0];
        let minDistance = Math.abs(nearest.x - pointerX);
        for (const point of smoothedPoints) {
          const distance = Math.abs(point.x - pointerX);
          if (distance < minDistance) {
            minDistance = distance;
            nearest = point;
          }
        }
        if (!Number.isFinite(nearest.value)) {
          hideTooltip();
          return;
        }
        const rawMatch = (state.rawChartPoints || []).find(point => point.ts === nearest.ts);
        const rawValue = rawMatch && Number.isFinite(rawMatch.value) ? rawMatch.value : nearest.value;
        const smoothedValue = nearest.value;
        const timestamp = new Date(nearest.ts);
        const label = state.label || 'Value';
        const rawText = Number.isFinite(rawValue) ? rawValue.toFixed(1) : 'n/a';
        const smoothText = Number.isFinite(smoothedValue) ? smoothedValue.toFixed(1) : 'n/a';
        const timeText = timestamp.toLocaleString();
        const tooltipText = state.smoothingFactor > 0
          ? `${label}: raw ${rawText} → smooth ${smoothText} @ ${timeText}`
          : `${label}: ${smoothText} @ ${timeText}`;
        showTooltip(tooltipText, event.clientX, event.clientY);
        drawLineChart(
          canvas,
          state.rawSeries,
          state.smoothedSeries,
          state.color,
          state.label,
          state.smoothingFactor,
          nearest.ts,
        );
      }

      function handleHistoryLeave(event) {
        hideTooltip();
        const canvas = event.currentTarget;
        const state = chartState.get(canvas);
        if (state) {
          drawLineChart(
            canvas,
            state.rawSeries,
            state.smoothedSeries,
            state.color,
            state.label,
            state.smoothingFactor,
            null,
          );
        }
      }

      function renderMetrics(data) {
        if (data.timestamp) {
          const parsed = new Date(data.timestamp);
          timestampEl.textContent = isNaN(parsed.getTime()) ? data.timestamp : parsed.toLocaleTimeString();
        }

        if (data.cpu) {
          const cpu = data.cpu;
          const util = formatNumber(cpu.utilization_pct, 1);
          const load = Array.isArray(cpu.load_avg)
            ? cpu.load_avg
                .map(function (value, index) {
                  const label = ['1m', '5m', '15m'][index] || '?';
                  return label + ': ' + formatNumber(Number(value), 2);
                })
                .join(' · ')
            : 'n/a';
          cpuEl.innerHTML = `<strong>${util}%</strong> utilization<span class="subtext">Load average — ${load}</span>`;
        }

        if (data.memory) {
          const mem = data.memory;
          const used = formatSizeMB(mem.used_mb);
          const total = formatSizeMB(mem.total_mb);
          const avail = formatSizeMB(mem.available_mb);
          const pct = formatNumber(mem.utilization_pct, 1);
          memEl.innerHTML = `<strong>${used}</strong> of ${total} (${pct}%)` +
            `<span class="subtext">Available: ${avail}</span>`;
        }

        if (data.disk) {
          const disk = data.disk;
          if (disk.total_mb == null) {
            diskEl.textContent = disk.message || 'Disk metrics unavailable';
          } else {
            const used = formatSizeMB(disk.used_mb);
            const total = formatSizeMB(disk.total_mb);
            const free = formatSizeMB(disk.free_mb);
            const pct = formatNumber(disk.utilization_pct, 1);
            diskEl.innerHTML = `${disk.path}: <strong>${used}</strong> of ${total} (${pct}%)` +
              `<span class="subtext">Free: ${free}</span>`;
          }
        }

        if (data.gpu && data.gpu.available && Array.isArray(data.gpu.devices) && data.gpu.devices.length) {
          const lines = data.gpu.devices.map(function (device) {
            const util = formatNumber(device.utilization_pct, 1);
            const memSegment = device.memory
              ? formatSizeMB(device.memory.used_mb) + ' / ' + formatSizeMB(device.memory.total_mb)
              : 'n/a';
            const temp = typeof device.temperature_c === 'number' ? device.temperature_c + '°C' : 'n/a';
            const power = typeof device.power_w === 'number' ? device.power_w + ' W' : 'n/a';
            return `<li><strong>${device.name}</strong> (idx ${device.index}) — ${util}% util, ${memSegment} VRAM, ${temp}, power ${power}</li>`;
          });
          gpuEl.innerHTML = `<ul class="devices">${lines.join('')}</ul>`;
        } else if (data.gpu && data.gpu.message) {
          gpuEl.textContent = data.gpu.message;
        } else {
          gpuEl.textContent = 'GPU metrics unavailable';
        }

        rawEl.textContent = JSON.stringify(data, null, 2);
      }

      setCurrentInterval(refreshMs / 1000);
      fetchMetrics();
      loadSettings();
      if (HISTORY_ENABLED) {
        loadHistory(historyWindow);
        scheduleHistoryRefresh();
      } else if (historyBlock) {
        historyBlock.style.display = 'none';
      }
    </script>
  </body>
</html>
"""
