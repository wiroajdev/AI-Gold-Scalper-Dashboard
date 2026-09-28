/**
 * TradingView Lightweight Charts Module for AI Gold Scalper Dashboard
 * Renders live candlestick & volume data loaded from staged MT5 CSVs.
 */

let tvChart = null;
let candleSeries = null;
let volumeSeries = null;
let aiPriceLines = [];
let sessionPriceLines = [];
let orderFlowPriceLines = [];
let showAiLevels = true;
let showSessionLevels = true;
let showOrderFlowLevels = true;
let currentChartTf = "M5";
let lastAiStatusData = null;
let lastSessionData = null;
let lastOrderFlowData = null;
let currentCandleData = [];
let brokerTimezoneStr = "UTC+1";

document.addEventListener("DOMContentLoaded", () => {
    initTradingViewChart();
    initChartControls();
});

function initTradingViewChart() {
    const container = document.getElementById("tvChartContainer");
    if (!container || typeof LightweightCharts === "undefined") {
        console.warn("LightweightCharts library or container not ready yet.");
        return;
    }

    // Initialize Lightweight Chart
    tvChart = LightweightCharts.createChart(container, {
        width: container.clientWidth,
        height: container.clientHeight || 480,
        layout: {
            background: { type: "solid", color: "#080c14" },
            textColor: "#94a3b8",
            fontFamily: "'JetBrains Mono', 'Inter', -apple-system, sans-serif",
            fontSize: 12,
        },
        grid: {
            vertLines: { color: "rgba(255, 255, 255, 0.03)" },
            horzLines: { color: "rgba(255, 255, 255, 0.03)" },
        },
        crosshair: {
            mode: LightweightCharts.CrosshairMode.Normal,
            vertLine: {
                color: "#64748b",
                width: 1,
                style: LightweightCharts.LineStyle.Dotted,
                labelBackgroundColor: "#1e293b",
            },
            horzLine: {
                color: "#64748b",
                width: 1,
                style: LightweightCharts.LineStyle.Dotted,
                labelBackgroundColor: "#1e293b",
            },
        },
        rightPriceScale: {
            borderColor: "rgba(255, 255, 255, 0.08)",
            scaleMargins: {
                top: 0.1,
                bottom: 0.22,
            },
        },
        timeScale: {
            borderColor: "rgba(255, 255, 255, 0.08)",
            timeVisible: true,
            secondsVisible: false,
        },
    });

    // Main Candlestick Series
    candleSeries = tvChart.addCandlestickSeries({
        upColor: "#10b981",
        downColor: "#ef4444",
        borderVisible: false,
        wickUpColor: "#10b981",
        wickDownColor: "#ef4444",
    });

    // Volume Histogram Series (Overlay at bottom)
    volumeSeries = tvChart.addHistogramSeries({
        priceFormat: {
            type: "volume",
        },
        priceScaleId: "", // Overlay over candlestick
    });

    volumeSeries.priceScale().applyOptions({
        scaleMargins: {
            top: 0.8,
            bottom: 0,
        },
    });

    // Crosshair hover legend update
    tvChart.subscribeCrosshairMove((param) => {
        if (!param || !param.time || !param.seriesData.get(candleSeries)) {
            updateDefaultLegend();
            return;
        }

        const cData = param.seriesData.get(candleSeries);
        const vData = volumeSeries ? param.seriesData.get(volumeSeries) : null;
        displayLegendValues(param.time, cData, vData);
    });

    // Responsive window resize
    window.addEventListener("resize", () => {
        if (tvChart && container) {
            tvChart.applyOptions({
                width: container.clientWidth,
                height: container.clientHeight,
            });
        }
    });

    // Load initial timeframe data
    loadChartTimeframe(currentChartTf, true);
}

function initChartControls() {
    // Timeframe selector buttons
    const tfButtons = document.querySelectorAll(".tf-pill");
    tfButtons.forEach((btn) => {
        btn.addEventListener("click", () => {
            const tf = btn.getAttribute("data-tf");
            if (!tf || tf === currentChartTf) return;

            tfButtons.forEach((b) => b.classList.remove("active"));
            btn.classList.add("active");

            currentChartTf = tf;
            document.getElementById("activeChartTfBadge").textContent = tf;

            loadChartTimeframe(tf, true);
        });
    });

    // AI Levels toggle button
    const toggleAiBtn = document.getElementById("toggleAiLevelsBtn");
    if (toggleAiBtn) {
        toggleAiBtn.addEventListener("click", () => {
            showAiLevels = !showAiLevels;
            toggleAiBtn.classList.toggle("active", showAiLevels);
            renderAiPriceLines();
        });
    }

    // Session Levels toggle button
    const toggleSessionBtn = document.getElementById("toggleSessionLevelsBtn");
    if (toggleSessionBtn) {
        toggleSessionBtn.addEventListener("click", () => {
            showSessionLevels = !showSessionLevels;
            toggleSessionBtn.classList.toggle("active", showSessionLevels);
            renderSessionLevels();
        });
    }

    // Order Flow / Market Structure toggle button
    const toggleOrderFlowBtn = document.getElementById("toggleOrderFlowBtn");
    if (toggleOrderFlowBtn) {
        toggleOrderFlowBtn.addEventListener("click", () => {
            showOrderFlowLevels = !showOrderFlowLevels;
            toggleOrderFlowBtn.classList.toggle("active", showOrderFlowLevels);
            // Show/hide the info strip too
            const strip = document.getElementById("orderFlowStrip");
            if (strip) strip.style.opacity = showOrderFlowLevels ? "1" : "0.35";
            renderOrderFlowLevels();
        });
    }

    // Auto-fit button
    const fitBtn = document.getElementById("fitContentBtn");
    if (fitBtn) {
        fitBtn.addEventListener("click", () => {
            if (tvChart) {
                tvChart.timeScale().fitContent();
            }
        });
    }

    // Fullscreen / Maximize toggle button
    const fullscreenBtn = document.getElementById("fullscreenChartBtn");
    const chartCard = document.getElementById("chartCardContainer");
    const container = document.getElementById("tvChartContainer");

    if (fullscreenBtn && chartCard) {
        fullscreenBtn.addEventListener("click", () => {
            const isFull = chartCard.classList.toggle("fullscreen-mode");
            fullscreenBtn.innerHTML = isFull ? "✕ Restore" : "⛶ Maximize";

            setTimeout(() => {
                if (tvChart && container) {
                    tvChart.applyOptions({
                        width: container.clientWidth,
                        height: container.clientHeight,
                    });
                    tvChart.timeScale().fitContent();
                }
            }, 100);
        });

        // Esc key to exit fullscreen
        document.addEventListener("keydown", (e) => {
            if (e.key === "Escape" && chartCard.classList.contains("fullscreen-mode")) {
                chartCard.classList.remove("fullscreen-mode");
                fullscreenBtn.innerHTML = "⛶ Maximize";
                setTimeout(() => {
                    if (tvChart && container) {
                        tvChart.applyOptions({
                            width: container.clientWidth,
                            height: container.clientHeight,
                        });
                        tvChart.timeScale().fitContent();
                    }
                }, 100);
            }
        });
    }
}

async function loadChartTimeframe(tf, fitContent = false) {
    const loadingOverlay = document.getElementById("chartLoadingOverlay");
    if (loadingOverlay) loadingOverlay.classList.remove("hidden");

    try {
        const response = await fetch(`/api/chart_data/${tf}`);
        const result = await response.json();

        if (result.status === "success") {
            currentCandleData = result.candles || [];
            brokerTimezoneStr = result.broker_tz || "UTC+1";

            if (candleSeries && result.candles) {
                candleSeries.setData(result.candles);
            }

            if (volumeSeries && result.volumes) {
                volumeSeries.setData(result.volumes);
            }

            if (fitContent && tvChart) {
                tvChart.timeScale().fitContent();
            }

            updateDefaultLegend();
            renderAiPriceLines();
            fetchAndRenderSessionLevels();
            fetchAndRenderOrderFlowLevels();
        } else {
            console.error("Failed to fetch chart data:", result.message);
        }
    } catch (err) {
        console.error("Chart data network error:", err);
    } finally {
        if (loadingOverlay) loadingOverlay.classList.add("hidden");
    }
}

function formatTime(timestamp) {
    if (!timestamp) return "--";
    const date = new Date(timestamp * 1000);
    // Format UTC+1 and Thai
    const y = date.getUTCFullYear();
    const m = String(date.getUTCMonth() + 1).padStart(2, "0");
    const d = String(date.getUTCDate()).padStart(2, "0");
    const hh = String(date.getUTCHours()).padStart(2, "0");
    const mm = String(date.getUTCMinutes()).padStart(2, "0");
    return `${y}.${m}.${d} ${hh}:${mm}`;
}

function displayLegendValues(timestamp, candle, volume) {
    if (!candle) return;

    const timeElem = document.getElementById("legendTime");
    const openElem = document.getElementById("legendOpen");
    const highElem = document.getElementById("legendHigh");
    const lowElem = document.getElementById("legendLow");
    const closeElem = document.getElementById("legendClose");
    const chgElem = document.getElementById("legendChange");
    const volElem = document.getElementById("legendVol");

    if (timeElem) timeElem.textContent = formatTime(timestamp);
    if (openElem) openElem.textContent = candle.open.toFixed(2);
    if (highElem) highElem.textContent = candle.high.toFixed(2);
    if (lowElem) lowElem.textContent = candle.low.toFixed(2);
    if (closeElem) closeElem.textContent = candle.close.toFixed(2);

    const diff = candle.close - candle.open;
    const pct = candle.open > 0 ? (diff / candle.open) * 100 : 0;
    const sign = diff >= 0 ? "+" : "";

    if (chgElem) {
        chgElem.textContent = `${sign}${diff.toFixed(2)} (${sign}${pct.toFixed(2)}%)`;
        chgElem.className = diff >= 0 ? "legend-up" : "legend-down";
    }

    if (volElem && volume) {
        volElem.textContent = Number(volume.value).toLocaleString();
    } else if (volElem) {
        volElem.textContent = "--";
    }
}

function updateDefaultLegend() {
    if (!currentCandleData || currentCandleData.length === 0) return;
    const latest = currentCandleData[currentCandleData.length - 1];
    displayLegendValues(latest.time, latest, null);
}

function renderAiPriceLines() {
    // Remove existing price lines
    if (candleSeries) {
        aiPriceLines.forEach((line) => {
            try {
                candleSeries.removePriceLine(line);
            } catch (e) {}
        });
    }
    aiPriceLines = [];

    if (!showAiLevels || !candleSeries) return;

    // Use the latest closed candle price of the currently active timeframe
    const currentPrice = (currentCandleData && currentCandleData.length > 0)
        ? currentCandleData[currentCandleData.length - 1].close
        : (lastAiStatusData ? lastAiStatusData.current_price : null);

    // 1. Current Timeframe Close Price Line (Cyan)
    if (currentPrice && currentPrice > 0) {
        const liveLine = candleSeries.createPriceLine({
            price: currentPrice,
            color: "#38bdf8",
            lineWidth: 2,
            lineStyle: LightweightCharts.LineStyle.Solid,
            axisLabelVisible: true,
            title: `Close: $${currentPrice.toFixed(2)}`,
        });
        aiPriceLines.push(liveLine);
    }

    const ensemble = lastAiStatusData ? lastAiStatusData.ensemble : null;
    if (!ensemble) return;

    const action = ensemble.action;
    const entry = ensemble.entry_price;
    const sl = ensemble.sl_price;
    const tp1 = ensemble.tp1_price;
    const tp2 = ensemble.tp2_price;

    // 2. Entry Price Line (Gold)
    if (entry && entry > 0 && action !== "HOLD") {
        const entryLine = candleSeries.createPriceLine({
            price: entry,
            color: "#fbbf24",
            lineWidth: 2,
            lineStyle: LightweightCharts.LineStyle.Dashed,
            axisLabelVisible: true,
            title: `AI Entry (${action}): $${entry.toFixed(2)}`,
        });
        aiPriceLines.push(entryLine);
    }

    // 3. Stop Loss Line (Red)
    if (sl && sl > 0) {
        const slLine = candleSeries.createPriceLine({
            price: sl,
            color: "#ef4444",
            lineWidth: 2,
            lineStyle: LightweightCharts.LineStyle.Dashed,
            axisLabelVisible: true,
            title: `Stop Loss: $${sl.toFixed(2)}`,
        });
        aiPriceLines.push(slLine);
    }

    // 4. Take Profit 1 Line (Green)
    if (tp1 && tp1 > 0) {
        const tp1Line = candleSeries.createPriceLine({
            price: tp1,
            color: "#10b981",
            lineWidth: 1,
            lineStyle: LightweightCharts.LineStyle.Dashed,
            axisLabelVisible: true,
            title: `TP1: $${tp1.toFixed(2)}`,
        });
        aiPriceLines.push(tp1Line);
    }

    // 5. Take Profit 2 Line (Emerald)
    if (tp2 && tp2 > 0) {
        const tp2Line = candleSeries.createPriceLine({
            price: tp2,
            color: "#059669",
            lineWidth: 1,
            lineStyle: LightweightCharts.LineStyle.Dashed,
            axisLabelVisible: true,
            title: `TP2: $${tp2.toFixed(2)}`,
        });
        aiPriceLines.push(tp2Line);
    }
}

// ─── Session Range Levels ─────────────────────────────────────────────────

async function fetchAndRenderSessionLevels() {
    try {
        const res = await fetch("/api/session_levels");
        const data = await res.json();
        if (data.status === "success") {
            lastSessionData = data;
            renderSessionLevels();
            updateSessionLevelsBadge(data);
        }
    } catch (err) {
        console.warn("Session levels fetch failed:", err);
    }
}

function renderSessionLevels() {
    // Remove old session lines
    if (candleSeries) {
        sessionPriceLines.forEach((line) => {
            try { candleSeries.removePriceLine(line); } catch (e) {}
        });
    }
    sessionPriceLines = [];

    if (!showSessionLevels || !candleSeries || !lastSessionData) return;

    const { asian, london } = lastSessionData;

    // Asian High — solid orange
    if (asian && asian.high) {
        sessionPriceLines.push(candleSeries.createPriceLine({
            price: asian.high,
            color: "#f97316",
            lineWidth: 1,
            lineStyle: LightweightCharts.LineStyle.Dashed,
            axisLabelVisible: true,
            title: `Asian High ${asian.high.toFixed(2)}`,
        }));
    }
    // Asian Low — solid orange (dimmer)
    if (asian && asian.low) {
        sessionPriceLines.push(candleSeries.createPriceLine({
            price: asian.low,
            color: "#f97316",
            lineWidth: 1,
            lineStyle: LightweightCharts.LineStyle.Dashed,
            axisLabelVisible: true,
            title: `Asian Low ${asian.low.toFixed(2)}`,
        }));
    }
    // London High — violet
    if (london && london.high) {
        sessionPriceLines.push(candleSeries.createPriceLine({
            price: london.high,
            color: "#a78bfa",
            lineWidth: 1,
            lineStyle: LightweightCharts.LineStyle.Dashed,
            axisLabelVisible: true,
            title: `London High ${london.high.toFixed(2)}`,
        }));
    }
    // London Low — violet
    if (london && london.low) {
        sessionPriceLines.push(candleSeries.createPriceLine({
            price: london.low,
            color: "#a78bfa",
            lineWidth: 1,
            lineStyle: LightweightCharts.LineStyle.Dashed,
            axisLabelVisible: true,
            title: `London Low ${london.low.toFixed(2)}`,
        }));
    }
}

function updateSessionLevelsBadge(data) {
    const badgeEl = document.getElementById("sessionLevelsBadge");
    if (!badgeEl) return;
    const { asian, london } = data;
    const asianStr = asian && asian.high
        ? `🟠 A: ${asian.high.toFixed(2)} / ${asian.low.toFixed(2)}`
        : "🟠 Asia: —";
    const londonStr = london && london.high
        ? `🟣 L: ${london.high.toFixed(2)} / ${london.low.toFixed(2)}`
        : "🟣 London: —";
    badgeEl.textContent = `${asianStr}   ${londonStr}`;
    badgeEl.title = `Asian Range (07:00–13:30 ICT): H ${asian?.high ?? "—"} / L ${asian?.low ?? "—"}\nLondon Range (14:00–19:30 ICT): H ${london?.high ?? "—"} / L ${london?.low ?? "—"}`;
}

// ─── Order Flow / Market Structure Levels ────────────────────────────────

const OF_LINE_STYLE_MAP = {
    solid:  0,  // LightweightCharts.LineStyle.Solid
    dashed: 1,  // LightweightCharts.LineStyle.Dashed
    dotted: 3,  // LightweightCharts.LineStyle.Dotted
};

async function fetchAndRenderOrderFlowLevels() {
    try {
        const res = await fetch("/api/order_flow_levels");
        const data = await res.json();
        if (data.status === "success") {
            lastOrderFlowData = data;
            renderOrderFlowLevels();
            updateOrderFlowBadge(data);
        }
    } catch (err) {
        console.warn("Order Flow levels fetch failed:", err);
    }
}

function renderOrderFlowLevels() {
    // Clear existing Order Flow lines
    if (candleSeries) {
        orderFlowPriceLines.forEach((line) => {
            try { candleSeries.removePriceLine(line); } catch (e) {}
        });
    }
    orderFlowPriceLines = [];

    if (!showOrderFlowLevels || !candleSeries || !lastOrderFlowData) return;

    const levels = lastOrderFlowData.levels || [];

    levels.forEach((lvl) => {
        // Map lineStyle string → LightweightCharts integer
        const style = OF_LINE_STYLE_MAP[lvl.lineStyle] ?? 1;

        // Draw the main price line
        const line = candleSeries.createPriceLine({
            price: lvl.price,
            color: lvl.color,
            lineWidth: lvl.lineWidth || 1,
            lineStyle: style,
            axisLabelVisible: true,
            title: lvl.short_label || lvl.label,
        });
        orderFlowPriceLines.push(line);

        // Draw zone boundary lines (upper/lower) with 20% opacity fill effect
        if (lvl.zone && lvl.zone_top && lvl.zone_bottom) {
            // Upper boundary
            const upperLine = candleSeries.createPriceLine({
                price: lvl.zone_top,
                color: lvl.color + "55",   // 33% alpha
                lineWidth: 1,
                lineStyle: OF_LINE_STYLE_MAP["dotted"],
                axisLabelVisible: false,
                title: "",
            });
            // Lower boundary
            const lowerLine = candleSeries.createPriceLine({
                price: lvl.zone_bottom,
                color: lvl.color + "55",
                lineWidth: 1,
                lineStyle: OF_LINE_STYLE_MAP["dotted"],
                axisLabelVisible: false,
                title: "",
            });
            orderFlowPriceLines.push(upperLine, lowerLine);
        }
    });
}

function updateOrderFlowBadge(data) {
    const biasBadge  = document.getElementById("orderFlowBiasBadge");
    const levelsBadge = document.getElementById("orderFlowLevelsBadge");
    if (!biasBadge) return;

    const bias = data.market_bias || "NEUTRAL";
    const biasColors = {
        BULLISH: "#10b981",
        BEARISH: "#ef4444",
        NEUTRAL: "#94a3b8"
    };
    const biasEmoji = { BULLISH: "🟢", BEARISH: "🔴", NEUTRAL: "⚪" };

    biasBadge.textContent = `${biasEmoji[bias] || "⚪"} ${bias} — ${data.bias_reason || ""}`;
    biasBadge.style.color = biasColors[bias] || "#94a3b8";
    biasBadge.title = data.bias_reason || "";

    if (levelsBadge && data.summary) {
        const s = data.summary;
        levelsBadge.textContent = `🟢 Demand: ${s.demand_zones}   🔴 Supply: ${s.supply_zones}   Total: ${s.total_levels}`;
    }
}

// Global update hook called by app.js whenever status updates
window.updateChartWithAiData = function (data) {
    if (!data) return;
    lastAiStatusData = data;
    renderAiPriceLines();
};

// Global refresh hook for chart candles
window.refreshActiveChartData = function () {
    if (currentChartTf) {
        loadChartTimeframe(currentChartTf, false);
    }
};

// Global hook to refresh session levels on demand (called after fetch cycle)
window.refreshSessionLevels = function () {
    fetchAndRenderSessionLevels();
};

// Global hook to refresh Order Flow levels on demand
window.refreshOrderFlowLevels = function () {
    fetchAndRenderOrderFlowLevels();
};
