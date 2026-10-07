// AI Gold Scalper Web Dashboard Frontend Logic

let isFetching = false;
let lastRenderedUpdatedAt = null;
let lastAlertSignalKey = null;
let activeAlertSignalKey = null;
let lastMtfAlertKey = null; // tracks last MTF alignment alert to prevent repeat
let soundEnabled = true; // Alert sound toggle state (persisted in localStorage)

/**
 * Per-type alert enable state — persisted in localStorage.
 * Keys: "SNIPER_REALIGNMENT" | "SIGNIFICANT_PULLBACK" | "STANDARD" | "MTF"
 */
const ALERT_CFG_KEY = "gold_scalper_alert_cfg";
let alertCfg = {
    SNIPER_REALIGNMENT: true,
    SIGNIFICANT_PULLBACK: true,
    STANDARD: true,
    MTF: true,
};

/**
 * Loads sound preference from localStorage and sets the initial UI state
 */
function initSoundPreference() {
    try {
        const stored = localStorage.getItem("gold_scalper_sound_enabled");
        if (stored !== null) {
            soundEnabled = stored === "true";
        }
    } catch (e) {
        console.warn("Could not read sound setting from localStorage:", e);
    }
    updateSoundButtonUI();
}

/**
 * Loads alertCfg from localStorage and wires up the Alert Config modal UI.
 */
function initAlertConfig() {
    // Load persisted prefs
    try {
        const stored = localStorage.getItem(ALERT_CFG_KEY);
        if (stored) {
            const parsed = JSON.parse(stored);
            Object.assign(alertCfg, parsed);
        }
    } catch (e) {}

    // Sync checkboxes to loaded state
    _syncCfgCheckboxes();

    // Open button
    const openBtn = document.getElementById("alertConfigBtn");
    if (openBtn) openBtn.addEventListener("click", openAlertConfigModal);

    // Close / Done buttons
    const closeBtn = document.getElementById("alertConfigCloseBtn");
    const doneBtn  = document.getElementById("alertConfigDoneBtn");
    if (closeBtn) closeBtn.addEventListener("click", closeAlertConfigModal);
    if (doneBtn)  doneBtn.addEventListener("click",  closeAlertConfigModal);

    // Backdrop click to close
    const backdrop = document.getElementById("alertConfigModal");
    if (backdrop) {
        backdrop.addEventListener("click", (e) => {
            if (e.target === backdrop) closeAlertConfigModal();
        });
    }

    // ESC key
    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape") closeAlertConfigModal();
    });

    // Per-toggle change handlers
    const toggleMap = {
        cfgToggleSniper:   "SNIPER_REALIGNMENT",
        cfgTogglePullback: "SIGNIFICANT_PULLBACK",
        cfgToggleStandard: "STANDARD",
        cfgToggleMtf:      "MTF",
    };
    Object.entries(toggleMap).forEach(([id, key]) => {
        const el = document.getElementById(id);
        if (!el) return;
        el.addEventListener("change", () => {
            alertCfg[key] = el.checked;
            _updateCfgRowStyle(el, key);
            _saveAlertCfg();
            _flashCfgStatus();
        });
    });

    // Enable/Disable ALL buttons
    const disableAll = document.getElementById("alertCfgDisableAll");
    const enableAll  = document.getElementById("alertCfgEnableAll");
    if (disableAll) {
        disableAll.addEventListener("click", () => {
            Object.keys(alertCfg).forEach(k => alertCfg[k] = false);
            _syncCfgCheckboxes();
            _saveAlertCfg();
            _flashCfgStatus();
        });
    }
    if (enableAll) {
        enableAll.addEventListener("click", () => {
            Object.keys(alertCfg).forEach(k => alertCfg[k] = true);
            _syncCfgCheckboxes();
            _saveAlertCfg();
            _flashCfgStatus();
        });
    }
}

function _syncCfgCheckboxes() {
    const toggleMap = {
        cfgToggleSniper:   "SNIPER_REALIGNMENT",
        cfgTogglePullback: "SIGNIFICANT_PULLBACK",
        cfgToggleStandard: "STANDARD",
        cfgToggleMtf:      "MTF",
    };
    Object.entries(toggleMap).forEach(([id, key]) => {
        const el = document.getElementById(id);
        if (!el) return;
        el.checked = alertCfg[key];
        _updateCfgRowStyle(el, key);
    });
}

function _updateCfgRowStyle(checkboxEl, key) {
    const row = checkboxEl.closest(".alert-cfg-row");
    if (!row) return;
    row.classList.toggle("cfg-disabled", !checkboxEl.checked);
}

function _saveAlertCfg() {
    try {
        localStorage.setItem(ALERT_CFG_KEY, JSON.stringify(alertCfg));
    } catch (e) {}
}

function _flashCfgStatus() {
    const el = document.getElementById("alertCfgStatus");
    if (!el) return;
    el.textContent = "✅ บันทึกแล้ว";
    el.style.color = "#10b981";
    setTimeout(() => {
        el.textContent = "✅ บันทึกอัตโนมัติ";
        el.style.color = "";
    }, 1500);
}

function openAlertConfigModal() {
    _syncCfgCheckboxes();
    const modal = document.getElementById("alertConfigModal");
    if (!modal) return;
    modal.style.display = "flex";
    requestAnimationFrame(() => modal.classList.add("active"));
}

function closeAlertConfigModal() {
    const modal = document.getElementById("alertConfigModal");
    if (!modal) return;
    modal.classList.remove("active");
    setTimeout(() => {
        if (!modal.classList.contains("active")) modal.style.display = "none";
    }, 250);
}

/**
 * Updates the sound toggle button icon, text, title and visual classes
 */
function updateSoundButtonUI() {
    const btn = document.getElementById("soundToggleBtn");
    const icon = document.getElementById("soundBtnIcon");
    const text = document.getElementById("soundBtnText");
    if (!btn) return;

    if (soundEnabled) {
        btn.classList.add("sound-active");
        btn.classList.remove("sound-muted");
        if (icon) icon.textContent = "🔊";
        if (text) text.textContent = "Sound: ON";
        btn.title = "คลิกเพื่อปิดเสียงแจ้งเตือน (Click to Mute Alert Sound)";
    } else {
        btn.classList.remove("sound-active");
        btn.classList.add("sound-muted");
        if (icon) icon.textContent = "🔇";
        if (text) text.textContent = "Sound: OFF";
        btn.title = "คลิกเพื่อเปิดเสียงแจ้งเตือน (Click to Unmute Alert Sound)";
    }
}

// --- Polling loop with stall detection & Page Visibility recovery ---
let _pollTimer = null;
let _watchdogTimer = null;
let _lastPollTs = 0;
const POLL_INTERVAL_MS = 1000;
const WATCHDOG_TIMEOUT_MS = 5000; // restart loop if no poll in 5s

function startPolling() {
    stopPolling();
    _lastPollTs = Date.now();
    _pollTimer = setInterval(async () => {
        _lastPollTs = Date.now();
        await fetchStatus();
    }, POLL_INTERVAL_MS);
    _resetWatchdog();
}

function stopPolling() {
    if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; }
    if (_watchdogTimer) { clearTimeout(_watchdogTimer); _watchdogTimer = null; }
}

function _resetWatchdog() {
    if (_watchdogTimer) clearTimeout(_watchdogTimer);
    _watchdogTimer = setTimeout(() => {
        const elapsed = Date.now() - _lastPollTs;
        if (elapsed > WATCHDOG_TIMEOUT_MS && !document.hidden) {
            console.warn(`[Watchdog] Poll stalled for ${elapsed}ms — restarting polling loop.`);
            startPolling();
        } else {
            _resetWatchdog();
        }
    }, WATCHDOG_TIMEOUT_MS + 500);
}

// Pause when tab is hidden, resume immediately when visible again
document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
        stopPolling();
    } else {
        fetchStatus(); // immediate catch-up poll
        startPolling();
    }
});

document.addEventListener("DOMContentLoaded", () => {
    initControls();
    fetchStatus();
    startPolling();
    startSetupTrackerPolling();  // MTF Setup Tracker
});

function initControls() {
    initSoundPreference();
    initAlertConfig();

    const toggle = document.getElementById("autoUpdateToggle");
    const intervalSelect = document.getElementById("intervalSelect");
    const fetchNowBtn = document.getElementById("fetchNowBtn");
    const symbolInput = document.getElementById("symbolInput");
    const saveSymbolBtn = document.getElementById("saveSymbolBtn");

    async function applySymbol() {
        const sym = symbolInput.value.trim();
        if (!sym) return;
        setButtonLoading(true);
        try {
            await fetch("/api/settings", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ symbol: sym })
            });
            fetchStatus();
        } catch (e) {
            console.error("Failed to update symbol:", e);
        }
    }

    saveSymbolBtn.addEventListener("click", applySymbol);
    symbolInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
            applySymbol();
        }
    });

    toggle.addEventListener("change", async () => {
        const isChecked = toggle.checked;
        document.getElementById("autoUpdateStatusText").textContent = isChecked ? "ON" : "OFF";
        document.getElementById("autoUpdateStatusText").className = isChecked ? "status-on" : "status-off";

        try {
            await fetch("/api/settings", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ enabled: isChecked })
            });
            fetchStatus();
        } catch (e) {
            console.error("Failed to update toggle setting:", e);
        }
    });

    intervalSelect.addEventListener("change", async () => {
        const selectedInterval = intervalSelect.value;
        try {
            await fetch("/api/settings", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ interval: selectedInterval })
            });
            fetchStatus();
        } catch (e) {
            console.error("Failed to update interval setting:", e);
        }
    });

    const baseTfSelect = document.getElementById("baseTfSelect");
    if (baseTfSelect) {
        baseTfSelect.addEventListener("change", async () => {
            const selectedTf = baseTfSelect.value;
            setButtonLoading(true);
            try {
                await fetch("/api/settings", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ base_tf: selectedTf })
                });
                fetchStatus();
            } catch (e) {
                console.error("Failed to update base TF setting:", e);
            }
        });
    }

    fetchNowBtn.addEventListener("click", async () => {
        if (isFetching) return;
        setButtonLoading(true);
        try {
            await fetch("/api/fetch_now", { method: "POST" });
            fetchStatus();
        } catch (e) {
            console.error("Manual fetch trigger failed:", e);
        }
    });

    // Alert modal listeners
    const modalCloseBtn = document.getElementById("alertModalCloseBtn");
    if (modalCloseBtn) modalCloseBtn.addEventListener("click", closeSignalAlertModal);

    const modalAckBtn = document.getElementById("modalAckBtn");
    if (modalAckBtn) {
        modalAckBtn.addEventListener("click", () => {
            if (activeAlertSignalKey) {
                try {
                    sessionStorage.setItem("gold_scalper_last_ack_signal", activeAlertSignalKey);
                } catch (e) {}
            }
            closeSignalAlertModal();
        });
    }

    const modalFocusChartBtn = document.getElementById("modalFocusChartBtn");
    if (modalFocusChartBtn) {
        modalFocusChartBtn.addEventListener("click", () => {
            if (activeAlertSignalKey) {
                try {
                    sessionStorage.setItem("gold_scalper_last_ack_signal", activeAlertSignalKey);
                } catch (e) {}
            }
            closeSignalAlertModal();
            const chartElem = document.getElementById("tvChartContainer");
            if (chartElem) {
                chartElem.scrollIntoView({ behavior: "smooth", block: "center" });
            }
        });
    }

    const modalBackdrop = document.getElementById("signalAlertModal");
    if (modalBackdrop) {
        modalBackdrop.addEventListener("click", (e) => {
            if (e.target === modalBackdrop) {
                closeSignalAlertModal();
            }
        });
    }

    // MTF Alert modal listeners
    const mtfCloseBtn = document.getElementById("mtfModalCloseBtn");
    if (mtfCloseBtn) mtfCloseBtn.addEventListener("click", closeMtfAlertModal);

    const mtfAckBtn = document.getElementById("mtfModalAckBtn");
    if (mtfAckBtn) {
        mtfAckBtn.addEventListener("click", () => {
            if (lastMtfAlertKey) {
                try { sessionStorage.setItem("gold_scalper_last_mtf_ack", lastMtfAlertKey); } catch (e) {}
            }
            closeMtfAlertModal();
        });
    }

    const mtfFocusBtn = document.getElementById("mtfModalFocusBtn");
    if (mtfFocusBtn) {
        mtfFocusBtn.addEventListener("click", () => {
            if (lastMtfAlertKey) {
                try { sessionStorage.setItem("gold_scalper_last_mtf_ack", lastMtfAlertKey); } catch (e) {}
            }
            closeMtfAlertModal();
            const chartElem = document.getElementById("tvChartContainer");
            if (chartElem) {
                chartElem.scrollIntoView({ behavior: "smooth", block: "center" });
            }
        });
    }

    const mtfBackdrop = document.getElementById("mtfAlertModal");
    if (mtfBackdrop) {
        mtfBackdrop.addEventListener("click", (e) => {
            if (e.target === mtfBackdrop) {
                closeMtfAlertModal();
            }
        });
    }

    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape") {
            closeSignalAlertModal();
            closeMtfAlertModal();
        }
    });

    const testAlertBtn = document.getElementById("testAlertBtn");
    if (testAlertBtn) {
        testAlertBtn.addEventListener("click", () => {
            triggerTestModal();
        });
    }

    // Sound Toggle Button (Sound ON/OFF)
    const soundToggleBtn = document.getElementById("soundToggleBtn");
    if (soundToggleBtn) {
        soundToggleBtn.addEventListener("click", () => {
            soundEnabled = !soundEnabled;
            try {
                localStorage.setItem("gold_scalper_sound_enabled", soundEnabled ? "true" : "false");
            } catch (e) {}
            updateSoundButtonUI();
            if (soundEnabled) {
                playAlertSound("standard"); // Quick feedback chime when unmuting
            }
        });
    }

    // Initialize sound preference from localStorage
    initSoundPreference();
}

function setButtonLoading(loading) {
    isFetching = loading;
    const btn = document.getElementById("fetchNowBtn");
    const textSpan = btn.querySelector(".btn-text");
    const iconSpan = btn.querySelector(".btn-icon");

    if (loading) {
        btn.classList.add("btn-loading");
        iconSpan.textContent = "⏳";
        textSpan.textContent = "Syncing MT5 & AI...";
    } else {
        btn.classList.remove("btn-loading");
        iconSpan.textContent = "⚡";
        textSpan.textContent = "Fetch & Analyze Now";
    }
}

async function fetchStatus() {
    try {
        const res = await fetch("/api/status");
        if (!res.ok) return;
        const payload = await res.json();
        _setConnectionError(false);
        renderDashboard(payload);
    } catch (e) {
        console.error("Error fetching status:", e);
        _setConnectionError(true);
    }
}

function _setConnectionError(hasError) {
    const el = document.getElementById("serverTime");
    if (!el) return;
    if (hasError) {
        el.textContent = "Reconnecting...";
        el.style.color = "#f59e0b";
    } else {
        el.style.color = "";
    }
}

function renderDashboard(payload) {
    const data = payload.data || {};
    const sched = payload.scheduler || {};
    const serverTime = payload.server_time || "--:--:--";

    // Update TradingView Chart AI Levels & data
    try {
        if (window.updateChartWithAiData) {
            window.updateChartWithAiData(data);
        }
        if (data.updated_at && data.updated_at !== lastRenderedUpdatedAt) {
            lastRenderedUpdatedAt = data.updated_at;
            if (window.refreshActiveChartData) {
                window.refreshActiveChartData();
            }
        }
    } catch (chartErr) {
        console.warn("Chart update non-fatal error:", chartErr);
    }

    // Server time
    document.getElementById("serverTime").textContent = serverTime.split(" ")[1] || serverTime;

    // Active Symbol
    const activeSymbol = payload.symbol || data.symbol || "XAUUSD";
    const symbolBadge = document.getElementById("activeSymbolBadge");
    if (symbolBadge) symbolBadge.textContent = activeSymbol;

    const symbolInput = document.getElementById("symbolInput");
    if (symbolInput && document.activeElement !== symbolInput && !symbolInput.value) {
        symbolInput.value = activeSymbol;
    }

    // Available symbols datalist
    const availableSyms = payload.available_symbols || [];
    const datalist = document.getElementById("symbolDatalist");
    if (datalist && availableSyms.length > 0) {
        let opts = "";
        for (const s of availableSyms) {
            opts += `<option value="${s}"></option>`;
        }
        datalist.innerHTML = opts;
    }

    // Error banner
    const errorBanner = document.getElementById("errorBanner");
    if (data.last_error) {
        errorBanner.style.display = "flex";
        document.getElementById("errorMessage").textContent = data.last_error;
    } else {
        errorBanner.style.display = "none";
    }

    // Scheduler controls sync
    const toggle = document.getElementById("autoUpdateToggle");
    if (toggle && toggle.checked !== sched.is_enabled) {
        toggle.checked = sched.is_enabled;
        const statusText = document.getElementById("autoUpdateStatusText");
        statusText.textContent = sched.is_enabled ? "ON" : "OFF";
        statusText.className = sched.is_enabled ? "status-on" : "status-off";
    }

    const intervalSelect = document.getElementById("intervalSelect");
    if (intervalSelect && sched.interval_key && intervalSelect.value !== sched.interval_key) {
        intervalSelect.value = sched.interval_key;
    }

    // Base Timeframe sync
    const baseTf = payload.base_tf || data.execution_timeframe || "M5";
    const baseTfSelect = document.getElementById("baseTfSelect");
    if (baseTfSelect && baseTfSelect.value !== baseTf) {
        baseTfSelect.value = baseTf;
    }
    const execTfPill = document.getElementById("execTfPill");
    if (execTfPill) execTfPill.textContent = `TF: ${baseTf}`;
    const regimeTfPill = document.getElementById("regimeTfPill");
    if (regimeTfPill) regimeTfPill.textContent = `TF: ${baseTf}`;

    // Next run & countdown
    const nextClock = document.getElementById("nextRunClock");
    const countdownTag = document.getElementById("nextRunCountdown");
    if (sched.is_enabled && sched.next_run_time) {
        nextClock.textContent = sched.next_run_time;
        const sec = sched.next_run_seconds || 0;
        const m = Math.floor(sec / 60);
        const s = sec % 60;
        const mStr = m > 0 ? `${m}m ` : "";
        countdownTag.textContent = `in ${mStr}${s}s`;
        countdownTag.className = "countdown-tag countdown-active";
    } else {
        nextClock.textContent = "Paused";
        countdownTag.textContent = "Toggle OFF";
        countdownTag.className = "countdown-tag";
    }

    // Busy state
    if (sched.is_busy) {
        setButtonLoading(true);
    } else if (isFetching) {
        setButtonLoading(false);
    }

    // Latest MT5 Bar Time & Staging Dir
    const barTimeElem = document.getElementById("latestBarTime");
    barTimeElem.textContent = data.latest_bar_time || "N/A";
    if (data.staging_dir) {
        const stagingElem = document.getElementById("stagingPathDisplay");
        if (stagingElem) stagingElem.textContent = data.staging_dir;
    }

    // Data source indicator (MT5 Live vs CSV Cached)
    const dataSourceElem = document.getElementById("dataSourceBadge");
    if (dataSourceElem) {
        const src = data.data_source || "CSV Cached";
        dataSourceElem.textContent = src;
        dataSourceElem.style.background = src === "MT5 Live" ? "rgba(16,185,129,0.2)" : "rgba(245,158,11,0.2)";
        dataSourceElem.style.color = src === "MT5 Live" ? "#10b981" : "#f59e0b";
        dataSourceElem.style.border = src === "MT5 Live" ? "1px solid #10b981" : "1px solid #f59e0b";
    }


    // Live Price Bar
    const currentPrice = data.current_price || data.latest_price || 0.0;
    const currentPriceElem = document.getElementById("currentPriceDisplay");
    if (currentPriceElem) {
        currentPriceElem.textContent = `$${currentPrice.toLocaleString("en-US", {minimumFractionDigits: 2})}`;
        currentPriceElem.title = "Latest close price from MT5 data";
    }

    // Staging directory path
    const stagingElem = document.getElementById("stagingPathDisplay");
    if (stagingElem && data.staging_dir) {
        stagingElem.textContent = data.staging_dir;
    }

    // MTF Last Updated timestamp
    const mtfUpdatedElem = document.getElementById("mtfLastUpdated");
    if (mtfUpdatedElem && data.updated_at) {
        mtfUpdatedElem.textContent = `Updated: ${data.updated_at}`;
    }

    // MTF Table (Strict descending order: D1 -> H4 -> H1 -> M15 -> M5 -> M1)
    const mtfTbody = document.getElementById("mtfTableBody");
    const mtf = data.multi_timeframe || {};
    const tfOrder = ["D1", "H4", "H1", "M15", "M5", "M1"];
    if (Object.keys(mtf).length > 0) {
        let mtfHtml = "";
        for (const tf of tfOrder) {
            if (!mtf[tf]) continue;
            const tfData = mtf[tf];
            const tfReg = tfData.regime || "RANGING";
            let color = "#94a3b8";
            if (tfReg === "TRENDING_UP") color = "#10b981";
            if (tfReg === "TRENDING_DOWN") color = "#ef4444";
            if (tfReg === "HIGH_VOLATILITY") color = "#f59e0b";

            const ker = tfData.ker !== undefined ? Number(tfData.ker).toFixed(2) : "—";
            const kerLbl = (tfData.ker_label || "").toLowerCase().replace(" ", "-");
            const kerColor = kerLbl === "trending" ? "#10b981" : (kerLbl === "choppy" ? "#ef4444" : "#f59e0b");

            mtfHtml += `
            <tr>
                <td style="font-weight: 700; color: #fbbf24;">${tf}</td>
                <td><span style="color: ${color}; font-weight: 600; font-size: 0.8rem;">${tfReg}</span></td>
                <td class="mono">$${(tfData.latest_close || 0).toLocaleString("en-US", {minimumFractionDigits: 2})}</td>
                <td class="mono" style="color: #94a3b8;">${(tfData.adx || 0).toFixed(1)}</td>
                <td class="mono" style="color: #94a3b8;">$${(tfData.atr || 0).toFixed(2)}</td>
                <td class="mono" style="color: ${kerColor}; font-weight: 600;">${ker}</td>
            </tr>
            `;
        }
        mtfTbody.innerHTML = mtfHtml;
    }

    // Check Executive Signal for Alert Dialog Popup (BUY / SELL only)
    checkAndTriggerSignalAlert(data, payload);

    // Check MTF Alignment (H1+M15+M5+M1 same trending direction)
    checkAndTriggerMtfAlert(data, payload);

    // Render AI Radar Sniper Panel
    renderSniperPanel(data);

    // Render Professional Advice's Trade Setup
    if (payload.professional_advice) {
        renderProfessionalAdvice(payload.professional_advice);
    }
}

/**
 * Renders the AI Radar — Price Action Sniper Panel
 * Reads `data.directional_bias` from the API and updates:
 *   - Directional Bias display (BULLISH / BEARISH / NEUTRAL)
 *   - Edge Score + progress bar
 *   - KER Score + label
 *   - MTF Stack pills (H1, M15, M5, M1)
 *   - Falling Knife Banner
 *   - NO TRADE ZONE indicator
 */
function renderSniperPanel(data) {
    const bias = data.directional_bias || {};
    const mtf = data.multi_timeframe || {};
    const watchTfs = ["H1", "M15", "M5", "M1"];

    // ── Falling Knife Banner ──
    const fkBanner = document.getElementById("fallingKnifeBanner");
    if (fkBanner) {
        const isFk = Boolean(bias.falling_knife_warning || bias.falling_knife_active || data.ensemble?.falling_knife_warning);
        fkBanner.style.display = isFk ? "flex" : "none";
    }

    // ── MTF Stack Pills & Alignment Calculation ──
    const mtfStackEl = document.getElementById("mtfStackPills");
    const mtfCountEl = document.getElementById("mtfAlignCount");
    const mtfBrk = bias.mtf_breakdown || {};
    let upCount = 0;
    let downCount = 0;

    if (mtfStackEl) {
        let pillsHtml = "";
        for (const tf of watchTfs) {
            // Priority: bias.mtf_breakdown -> data.multi_timeframe[tf].regime -> "N/A"
            const rawRegime = (mtfBrk[tf] || mtf[tf]?.regime || "N/A").toUpperCase();
            let cls = "neutral";
            let arrow = "—";

            if (rawRegime === "TRENDING_UP") {
                cls = "up";
                arrow = "▲";
                upCount++;
            } else if (rawRegime === "TRENDING_DOWN") {
                cls = "down";
                arrow = "▼";
                downCount++;
            } else if (rawRegime === "RANGING") {
                cls = "ranging";
                arrow = "≈";
            } else if (rawRegime.includes("VOLATILITY")) {
                cls = "high-vol";
                arrow = "⚡";
            }

            pillsHtml += `<span class="mtf-stack-pill ${cls}" title="${tf}: ${rawRegime}">${tf} ${arrow}</span>`;
        }
        mtfStackEl.innerHTML = pillsHtml;

        if (mtfCountEl) {
            const alignCount = Math.max(upCount, downCount);
            mtfCountEl.textContent = `${alignCount}/4`;
            mtfCountEl.style.color = alignCount >= 3 ? "#10b981" : (alignCount === 2 ? "#f59e0b" : "#94a3b8");
        }
    }

    // ── Directional Bias ──
    const biasEl = document.getElementById("biasDisplay");
    const biasDetail = document.getElementById("biasDetail");
    let currentBias = bias.directional_bias;
    if (!currentBias) {
        // Fallback calculation from MTF counts if bias engine output missing
        if (upCount >= 3) currentBias = "STRONG BULLISH";
        else if (upCount === 2 && downCount === 0) currentBias = "BULLISH";
        else if (downCount >= 3) currentBias = "STRONG BEARISH";
        else if (downCount === 2 && upCount === 0) currentBias = "BEARISH";
        else currentBias = "NEUTRAL";
    }

    if (biasEl) {
        const b = currentBias.toLowerCase().replace(/[^a-z]/g, "");
        const bClass = currentBias.includes("BULLISH") ? "bullish" : (currentBias.includes("BEARISH") ? "bearish" : "neutral");
        biasEl.className = `bias-display ${bClass}`;
        biasEl.textContent = currentBias;
    }
    if (biasDetail) {
        biasDetail.textContent = bias.bias_detail || (currentBias === "NEUTRAL" ? "Market is choppy or TF-misaligned — NO TRADE ZONE" : `Bias aligned with ${currentBias.toLowerCase()} structure`);
    }

    // ── Edge Score ──
    const edgeNum = document.getElementById("edgeScoreNum");
    const edgeBar = document.getElementById("edgeScoreBar");
    const edgeLbl = document.getElementById("edgeScoreLabel");
    let score = bias.edge_score;
    if (score === undefined || score === null) {
        // Approximate fallback score from MTF alignment
        score = Math.max(upCount, downCount) * 15;
    }

    if (edgeNum) {
        edgeNum.textContent = score;
        edgeNum.style.color = score >= 70 ? "#10b981" : (score >= 45 ? "#f59e0b" : "#ef4444");
    }
    if (edgeBar) {
        edgeBar.style.width = `${Math.min(100, Math.max(0, score))}%`;
    }
    if (edgeLbl) {
        const lbl = bias.edge_label || (score >= 70 ? "HIGH EDGE" : (score >= 45 ? "MODERATE" : "LOW / CHOPPY"));
        edgeLbl.textContent = lbl;
        edgeLbl.className = "edge-label " + (score >= 70 ? "high" : (score >= 45 ? "moderate" : "low"));
    }

    // ── KER Score ──
    const kerScoreEl = document.getElementById("kerScore");
    const kerLabelEl = document.getElementById("kerLabel");
    let kerVal = bias.ker_score;
    let kerLbl = bias.ker_label;

    if (kerVal === undefined || kerVal === null) {
        // Fallback from H1 / M15 in MTF table
        const h1Ker = mtf["H1"]?.ker;
        const m15Ker = mtf["M15"]?.ker;
        if (h1Ker !== undefined && m15Ker !== undefined) {
            kerVal = (h1Ker + m15Ker) / 2;
        } else if (m15Ker !== undefined) {
            kerVal = m15Ker;
        } else {
            kerVal = 0.50;
        }
        kerLbl = kerVal >= 0.60 ? "TRENDING" : (kerVal >= 0.30 ? "DRIFTING" : "CHOPPY");
    }

    if (kerScoreEl) {
        kerScoreEl.textContent = Number(kerVal).toFixed(2);
        const kStr = (kerLbl || "DRIFTING").toLowerCase();
        kerScoreEl.style.color = kStr === "trending" ? "#10b981" : (kStr === "choppy" ? "#ef4444" : "#38bdf8");
    }
    if (kerLabelEl) {
        kerLabelEl.textContent = kerLbl || "DRIFTING";
        kerLabelEl.className = "ker-label " + (kerLbl || "DRIFTING").toLowerCase().replace(" ", "-");
    }

    // ── NO TRADE ZONE indicator ──
    const noTradeEl = document.getElementById("noTradeZone");
    if (noTradeEl) {
        const isNoTrade = currentBias.includes("NEUTRAL") || score < 45 || (kerVal !== undefined && kerVal < 0.30);
        noTradeEl.style.display = isNoTrade ? "block" : "none";
    }
}


/**
 * Synthesizes clean, high-fidelity audio chimes via browser Web Audio API
 */
function playAlertSound(type = "standard") {
    if (!soundEnabled) return;
    try {
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        if (!AudioCtx) return;
        const ctx = new AudioCtx();
        if (ctx.state === "suspended") {
            ctx.resume();
        }

        const now = ctx.currentTime;
        if (type === "sniper") {
            // Triumphant 4-tone ascending arpeggio: C5 (523Hz), E5 (659Hz), G5 (784Hz), C6 (1046Hz)
            const freqs = [523.25, 659.25, 783.99, 1046.50];
            freqs.forEach((f, idx) => {
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();
                osc.type = "sine";
                osc.frequency.setValueAtTime(f, now + idx * 0.11);
                gain.gain.setValueAtTime(0, now + idx * 0.11);
                gain.gain.linearRampToValueAtTime(0.28, now + idx * 0.11 + 0.03);
                gain.gain.exponentialRampToValueAtTime(0.001, now + idx * 0.11 + 0.38);
                osc.connect(gain);
                gain.connect(ctx.destination);
                osc.start(now + idx * 0.11);
                osc.stop(now + idx * 0.11 + 0.40);
            });
        } else if (type === "pullback") {
            // Distinct 2-tone counter-trend warning chime: A5 (880Hz) -> D5 (587Hz)
            const freqs = [880.0, 587.33];
            freqs.forEach((f, idx) => {
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();
                osc.type = "triangle";
                osc.frequency.setValueAtTime(f, now + idx * 0.18);
                gain.gain.setValueAtTime(0, now + idx * 0.18);
                gain.gain.linearRampToValueAtTime(0.22, now + idx * 0.18 + 0.04);
                gain.gain.exponentialRampToValueAtTime(0.001, now + idx * 0.18 + 0.42);
                osc.connect(gain);
                gain.connect(ctx.destination);
                osc.start(now + idx * 0.18);
                osc.stop(now + idx * 0.18 + 0.45);
            });
        } else {
            // Standard crisp 2-tone chime: E5 (659Hz) -> A5 (880Hz)
            const freqs = [659.25, 880.0];
            freqs.forEach((f, idx) => {
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();
                osc.type = "sine";
                osc.frequency.setValueAtTime(f, now + idx * 0.14);
                gain.gain.setValueAtTime(0, now + idx * 0.14);
                gain.gain.linearRampToValueAtTime(0.24, now + idx * 0.14 + 0.03);
                gain.gain.exponentialRampToValueAtTime(0.001, now + idx * 0.14 + 0.36);
                osc.connect(gain);
                gain.connect(ctx.destination);
                osc.start(now + idx * 0.14);
                osc.stop(now + idx * 0.14 + 0.38);
            });
        }
    } catch (e) {
        console.warn("Audio chime prevented by browser autoplay policy:", e);
    }
}



function checkAndTriggerSignalAlert(data, payload) {
    if (!data) return;

    // Alert is now driven purely by Directional Bias, not ensemble votes
    const bias = data.directional_bias || {};
    const rawBiasDir = (bias.directional_bias || "NEUTRAL").toUpperCase();
    const edgeScore = bias.edge_score || 0;
    const isBullish = rawBiasDir.includes("BULLISH");
    const isBearish = rawBiasDir.includes("BEARISH");

    // Only BUY or SELL bias triggers popup
    if (!isBullish && !isBearish) return;

    const action = isBullish ? "BUY" : "SELL";
    const symbol = payload?.symbol || data.symbol || "XAUUSD";
    const tf = payload?.base_tf || data.execution_timeframe || "M5";
    const updateTime = data.updated_at || data.latest_bar_time || "";

    let alertType = "STANDARD";
    let title = "";
    let subtitle = "";
    let customReason = "";

    if (edgeScore >= 70) {
        alertType = "SNIPER_REALIGNMENT";
        title = isBullish ? "BULLISH SNIPER ALIGNMENT" : "BEARISH SNIPER ALIGNMENT";
        subtitle = "🎯 High-Edge Setup • Price Action + MTF Aligned";
        customReason = `🎯 Strong ${rawBiasDir} Directional Bias detected with Edge Score ${edgeScore}/100. MTF stack aligned. Look for Price Action confirmation on M1/M5 to execute.`;
    } else {
        alertType = "STANDARD";
        title = isBullish ? "BULLISH BIAS DETECTED" : "BEARISH BIAS DETECTED";
        subtitle = `Directional Bias on ${tf} • Edge: ${edgeScore}/100`;
        customReason = bias.bias_detail || `${rawBiasDir} directional bias detected with Edge Score ${edgeScore}/100.`;
    }

    // Guard: check per-type config toggle
    if (!alertCfg[alertType]) return;

    const signalKey = `${symbol}_${tf}_${updateTime}_${action}_${alertType}`;

    // Prevent re-triggering if already shown in this memory cycle or acknowledged in this session
    let sessionAck = null;
    try {
        sessionAck = sessionStorage.getItem("gold_scalper_last_ack_signal");
    } catch (e) {}

    if (lastAlertSignalKey === signalKey || sessionAck === signalKey) {
        return;
    }

    lastAlertSignalKey = signalKey;
    activeAlertSignalKey = signalKey;

    openSignalAlertModal({
        action: action,
        alertType: alertType,
        title: title,
        subtitle: subtitle,
        customReason: customReason,
        symbol: symbol,
        timeframe: tf,
        confidence: edgeScore,
        entryPrice: data.current_price || data.latest_price || 0,
        slPrice: 0,
        tp1Price: 0,
        rrRatio: 0.0,
        regime: data.regime?.regime || "RANGING",
        edgeScore: edgeScore,
        biasDir: rawBiasDir,
        time: updateTime || payload?.server_time || new Date().toLocaleTimeString()
    });
}

/**
 * Renders and displays the Unified Signal Alert Modal (Single Alert Rule)
 */
function openSignalAlertModal(info) {
    const modal = document.getElementById("signalAlertModal");
    const card = document.getElementById("alertModalCard");
    const hero = document.getElementById("modalSignalHero");
    const icon = document.getElementById("modalSignalIcon");
    const text = document.getElementById("modalSignalText");
    const subText = document.getElementById("modalSignalSub");
    const symbol = document.getElementById("modalSignalSymbol");
    const confVal = document.getElementById("modalConfidenceVal");
    const entry = document.getElementById("modalEntryPrice");
    const sl = document.getElementById("modalSlPrice");
    const tp = document.getElementById("modalTpPrice");
    const rr = document.getElementById("modalRrRatio");
    const regimeBadge = document.getElementById("modalRegimeBadge");
    const alignmentBadge = document.getElementById("modalAlignmentBadge");
    const reasonText = document.getElementById("modalReasonText");
    const timeElem = document.getElementById("modalAlertTime");
    const alertTag = document.getElementById("modalAlertTag");
    const alertTagText = document.getElementById("modalAlertTagText");

    if (!modal) return;

    const isBuy = info.action === "BUY";
    const alertType = info.alertType || "STANDARD";

    // Play synthesized Audio Chime
    const soundType = alertType === "SNIPER_REALIGNMENT" ? "sniper" : (alertType === "SIGNIFICANT_PULLBACK" ? "pullback" : "standard");
    playAlertSound(soundType);

    // Reset card classes
    card.classList.remove("buy-mode", "sell-mode", "sniper-mode", "pullback-mode");
    hero.classList.remove("buy", "sell");
    if (alertTag) alertTag.classList.remove("sniper", "pullback");

    if (alertType === "SNIPER_REALIGNMENT") {
        card.classList.add("sniper-mode");
        hero.classList.add(isBuy ? "buy" : "sell");
        if (alertTag) {
            alertTag.classList.add("sniper");
            if (alertTagText) alertTagText.textContent = "🎯 SNIPER RE-ALIGNMENT DETECTED";
        }
        icon.textContent = isBuy ? "▲" : "▼";
        text.textContent = info.title || (isBuy ? "BULLISH SNIPER ALIGNMENT" : "BEARISH SNIPER ALIGNMENT");
        if (subText) {
            subText.style.display = "block";
            subText.style.color = "#10b981";
            subText.textContent = info.subtitle || "Pullback Completed • Bias & Executive Synchronized";
        }
        if (alignmentBadge) {
            alignmentBadge.style.display = "inline-block";
            alignmentBadge.className = "modal-regime-pill sniper";
            alignmentBadge.textContent = `SNIPER ALIGNED (${info.edgeScore || 0}/100)`;
        }
    } else if (alertType === "SIGNIFICANT_PULLBACK") {
        card.classList.add("pullback-mode");
        hero.classList.add(isBuy ? "buy" : "sell");
        if (alertTag) {
            alertTag.classList.add("pullback");
            if (alertTagText) alertTagText.textContent = "⚠️ SIGNIFICANT PULLBACK DETECTED";
        }
        icon.textContent = isBuy ? "▲" : "▼";
        text.textContent = info.title || (isBuy ? "SIGNIFICANT BOUNCE (M5 BUY)" : "SIGNIFICANT PULLBACK (M5 SELL)");
        if (subText) {
            subText.style.display = "block";
            subText.style.color = "#f59e0b";
            subText.textContent = info.subtitle || `Counter-Trend Retracement • Macro Bias: ${info.biasDir}`;
        }
        if (alignmentBadge) {
            alignmentBadge.style.display = "inline-block";
            alignmentBadge.className = "modal-regime-pill pullback";
            alignmentBadge.textContent = "SIGNIFICANT PULLBACK";
        }
    } else {
        // Standard Buy / Sell
        if (isBuy) {
            card.classList.add("buy-mode");
            hero.classList.add("buy");
            icon.textContent = "▲";
            text.textContent = "BUY SIGNAL DETECTED";
        } else {
            card.classList.add("sell-mode");
            hero.classList.add("sell");
            icon.textContent = "▼";
            text.textContent = "SELL SIGNAL DETECTED";
        }
        if (alertTag) {
            if (alertTagText) alertTagText.textContent = "EXECUTIVE DECISION DETECTED";
        }
        if (subText) {
            subText.style.display = info.subtitle ? "block" : "none";
            subText.style.color = "#94a3b8";
            subText.textContent = info.subtitle || "";
        }
        if (alignmentBadge) {
            alignmentBadge.style.display = "none";
        }
    }

    symbol.textContent = `${info.symbol} • ${info.timeframe}`;
    confVal.textContent = `${info.confidence}%`;
    entry.textContent = `$${Number(info.entryPrice || 0).toLocaleString("en-US", {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    sl.textContent = info.slPrice ? `$${Number(info.slPrice).toLocaleString("en-US", {minimumFractionDigits: 2, maximumFractionDigits: 2})}` : "N/A";
    tp.textContent = info.tp1Price ? `$${Number(info.tp1Price).toLocaleString("en-US", {minimumFractionDigits: 2, maximumFractionDigits: 2})}` : "N/A";
    rr.textContent = `1:${info.rrRatio || "1.0"}`;

    if (regimeBadge) {
        regimeBadge.textContent = (info.regime || "RANGING").replace("_", " ");
    }
    if (reasonText) {
        reasonText.textContent = info.customReason || info.reason || "Executive consensus reached across models.";
    }
    if (timeElem) {
        timeElem.textContent = info.time || new Date().toLocaleTimeString();
    }

    modal.style.display = "flex";
    requestAnimationFrame(() => {
        modal.classList.add("active");
    });
}

/**
 * Closes the Executive Signal Alert Modal
 */
function closeSignalAlertModal() {
    const modal = document.getElementById("signalAlertModal");
    if (!modal) return;
    modal.classList.remove("active");
    setTimeout(() => {
        if (!modal.classList.contains("active")) {
            modal.style.display = "none";
        }
    }, 250);
}

/**
 * Manual test helper to trigger Alert Modal Dialog
 * Cycles through 3 previews: Sniper Re-alignment, Significant Pullback, and Standard
 */
let testModalStep = 0;
function triggerTestModal() {
    const activeSym = document.getElementById("activeSymbolBadge")?.textContent?.trim() || "XAUUSD";
    const baseTf = document.getElementById("baseTfSelect")?.value || "M5";
    const curPriceStr = document.getElementById("currentPriceDisplay")?.textContent?.replace(/[^0-9.]/g, "") || "2450.00";
    const curPrice = parseFloat(curPriceStr) || 2450.00;

    activeAlertSignalKey = null; // Do not suppress next real alert

    const step = testModalStep % 3;
    testModalStep++;

    if (step === 0) {
        // Preview 1: Sniper Re-Alignment
        openSignalAlertModal({
            action: "BUY",
            alertType: "SNIPER_REALIGNMENT",
            title: "BULLISH SNIPER RE-ALIGNMENT",
            subtitle: "🎯 Pullback Completed • Bias & Executive Synchronized • M1/M5 Entry Ready",
            customReason: "[TEST 1/3] 🎯 Golden Sniper Setup: Directional Bias [BULLISH] and Executive Decision [BUY] are now in full harmony (Edge: 85/100). The significant pullback has completed. Look for Price Action confirmation on M1/M5 to execute!",
            symbol: activeSym,
            timeframe: baseTf,
            confidence: 90,
            entryPrice: curPrice,
            slPrice: curPrice - 5.0,
            tp1Price: curPrice + 10.0,
            rrRatio: 2.0,
            regime: "TRENDING_UP",
            edgeScore: 85,
            biasDir: "BULLISH",
            time: `${new Date().toLocaleTimeString()} (Preview: Sniper Alignment)`
        });
    } else if (step === 1) {
        // Preview 2: Significant Pullback
        openSignalAlertModal({
            action: "SELL",
            alertType: "SIGNIFICANT_PULLBACK",
            title: "SIGNIFICANT PULLBACK (M5 SELL)",
            subtitle: "⚠️ Counter-Trend Retracement • Macro Bias: BULLISH • DO NOT CHOP",
            customReason: "[TEST 2/3] ⚠️ Significant Retracement: AI models on M5 detected heavy downward momentum (6/9 models) opposite to Macro Bias [BULLISH]. Do NOT sell into support — wait for price to reach key support levels for a Sniper BUY opportunity!",
            symbol: activeSym,
            timeframe: baseTf,
            confidence: 68,
            entryPrice: curPrice,
            slPrice: curPrice + 6.0,
            tp1Price: curPrice - 8.0,
            rrRatio: 1.5,
            regime: "RANGING",
            edgeScore: 40,
            biasDir: "BULLISH",
            time: `${new Date().toLocaleTimeString()} (Preview: Significant Pullback)`
        });
    } else {
        // Preview 3: Standard Signal
        openSignalAlertModal({
            action: "BUY",
            alertType: "STANDARD",
            title: "BUY SIGNAL DETECTED",
            subtitle: "Executive Decision on M5 • Directional Bias: NEUTRAL",
            customReason: "[TEST 3/3] ⚡ Standard Executive Decision: 7/9 models voted BUY in neutral/choppy conditions.",
            symbol: activeSym,
            timeframe: baseTf,
            confidence: 72,
            entryPrice: curPrice,
            slPrice: curPrice - 4.5,
            tp1Price: curPrice + 9.0,
            rrRatio: 2.0,
            regime: "RANGING",
            edgeScore: 30,
            biasDir: "NEUTRAL",
            time: `${new Date().toLocaleTimeString()} (Preview: Standard)`
        });
    }
}

// Expose functions globally for debugging/console invocation
window.showSignalAlert = openSignalAlertModal;
window.closeSignalAlert = closeSignalAlertModal;
window.triggerTestAlert = triggerTestModal;
window.toggleSound = function(overrideState) {
    if (typeof overrideState === "boolean") {
        soundEnabled = overrideState;
    } else {
        soundEnabled = !soundEnabled;
    }
    try {
        localStorage.setItem("gold_scalper_sound_enabled", soundEnabled ? "true" : "false");
    } catch (e) {}
    updateSoundButtonUI();
    return soundEnabled;
};
window.isSoundEnabled = () => soundEnabled;

/**
 * Checks H1, M15, M5, M1 regimes — triggers MTF Alignment Alert
 * if all 4 are TRENDING_UP or all 4 are TRENDING_DOWN simultaneously.
 * Single-Alert rule: Suppresses if Signal modal is currently visible.
 */
function checkAndTriggerMtfAlert(data, payload) {
    if (!data) return;

    // Guard: check MTF alert config toggle
    if (!alertCfg.MTF) return;

    // Single alert rule: If signal modal is open, do not show MTF modal over it
    const signalModal = document.getElementById("signalAlertModal");
    if (signalModal && (signalModal.style.display === "flex" || signalModal.classList.contains("active"))) {
        return;
    }

    const mtf = data.multi_timeframe || {};
    const watchTfs = ["H1", "M15", "M5", "M1"];

    // Collect regimes for the 4 target TFs
    const regimes = {};
    for (const tf of watchTfs) {
        if (mtf[tf] && mtf[tf].regime) {
            regimes[tf] = mtf[tf].regime.toUpperCase();
        }
    }

    // All 4 must be present
    if (Object.keys(regimes).length < 4) return;

    const allUp   = watchTfs.every(tf => regimes[tf] === "TRENDING_UP");
    const allDown = watchTfs.every(tf => regimes[tf] === "TRENDING_DOWN");

    if (!allUp && !allDown) return;

    const direction = allUp ? "UP" : "DOWN";
    const symbol = payload?.symbol || data.symbol || "XAUUSD";
    const updateTime = data.updated_at || data.latest_bar_time || "";
    const alertKey = `MTF_${symbol}_${direction}_${updateTime}`;

    // Prevent re-triggering same event
    let sessionAck = null;
    try { sessionAck = sessionStorage.getItem("gold_scalper_last_mtf_ack"); } catch(e) {}

    if (lastMtfAlertKey === alertKey || sessionAck === alertKey) return;

    lastMtfAlertKey = alertKey;

    openMtfAlertModal({
        direction,
        symbol,
        regimes,
        time: updateTime || payload?.server_time || new Date().toLocaleTimeString()
    });
}

/**
 * Opens the MTF Alignment Alert Modal
 */
function openMtfAlertModal(info) {
    const modal   = document.getElementById("mtfAlertModal");
    const card    = document.getElementById("mtfAlertCard");
    const hero    = document.getElementById("mtfModalHero");
    const icon    = document.getElementById("mtfModalIcon");
    const title   = document.getElementById("mtfModalTitle");
    const symbol  = document.getElementById("mtfModalSymbol");
    const tfCount = document.getElementById("mtfModalTfCount");
    const pill    = document.getElementById("mtfModalRegimePill");
    const tfList  = document.getElementById("mtfModalTfList");
    const reason  = document.getElementById("mtfModalReasonText");
    const timeEl  = document.getElementById("mtfModalTime");
    if (!modal) return;

    playAlertSound("sniper");

    const isUp = info.direction === "UP";

    card.classList.remove("buy-mode", "sell-mode");
    hero.classList.remove("buy", "sell");

    if (isUp) {
        card.classList.add("buy-mode");
        hero.classList.add("buy");
        icon.textContent = "▲";
        title.textContent = "BULLISH MTF ALIGNMENT";
        pill.textContent = "TRENDING UP";
        pill.style.background = "rgba(16,185,129,0.18)";
        pill.style.color = "#10b981";
        reason.textContent = "H1, M15, M5 และ M1 ทุก Timeframe แสดง Trending Up พร้อมกัน — โมเมนตัม Bullish แข็งแกร่ง";
    } else {
        card.classList.add("sell-mode");
        hero.classList.add("sell");
        icon.textContent = "▼";
        title.textContent = "BEARISH MTF ALIGNMENT";
        pill.textContent = "TRENDING DOWN";
        pill.style.background = "rgba(239,68,68,0.18)";
        pill.style.color = "#ef4444";
        reason.textContent = "H1, M15, M5 และ M1 ทุก Timeframe แสดง Trending Down พร้อมกัน — แรงขายครอบงำตลาด";
    }

    symbol.textContent = `${info.symbol} • H1+M15+M5+M1`;
    tfCount.textContent = "4/4";
    if (timeEl) timeEl.textContent = info.time || new Date().toLocaleTimeString();

    // Build TF pill list
    if (tfList) {
        const watchTfs = ["H1", "M15", "M5", "M1"];
        tfList.innerHTML = watchTfs.map(tf => {
            const cls = isUp ? "up" : "down";
            const arrow = isUp ? "▲" : "▼";
            return `<span class="mtf-tf-pill ${cls}">${tf} ${arrow}</span>`;
        }).join("");
    }

    modal.style.display = "flex";
    requestAnimationFrame(() => modal.classList.add("active"));
}

/**
 * Closes the MTF Alignment Alert Modal
 */
function closeMtfAlertModal() {
    const modal = document.getElementById("mtfAlertModal");
    if (!modal) return;
    modal.classList.remove("active");
    setTimeout(() => {
        if (!modal.classList.contains("active")) modal.style.display = "none";
    }, 250);
}

window.closeMtfAlert = closeMtfAlertModal;

// Alert Config Modal public API
window.openAlertConfig  = openAlertConfigModal;
window.closeAlertConfig = closeAlertConfigModal;
window.getAlertCfg = () => ({ ...alertCfg });


// ─── MTF Setup Tracker ─────────────────────────────────────────────────────

let _lastSetupAlertKey = null;
let _setupTrackerTimer = null;

/**
 * Start polling /api/setup_status every 10 seconds.
 */
function startSetupTrackerPolling() {
    if (_setupTrackerTimer) clearInterval(_setupTrackerTimer);
    fetchSetupStatus();  // immediate on load
    _setupTrackerTimer = setInterval(fetchSetupStatus, 10000);
}

async function fetchSetupStatus() {
    try {
        const res = await fetch("/api/setup_status");
        if (!res.ok) return;
        const data = await res.json();
        renderSetupTracker(data);
    } catch (e) {
        console.warn("[SetupTracker] fetch error:", e);
    }
}

/**
 * Renders the MTF Setup Tracker card from API response.
 */
function renderSetupTracker(d) {
    const state       = (d.state || "IDLE").toUpperCase();
    const bias        = (d.bias  || "").toUpperCase();
    const step1       = !!d.step1_ok;
    const step2       = !!d.step2_ok;
    const step3       = !!d.step3_ok;
    const confidence  = d.confidence_score || 0;
    const pattern     = d.price_action   || null;
    const patternTf   = d.price_action_tf || "";
    const zonesHit    = d.zones_hit || [];
    const alertMsg    = d.alert_message || null;
    const cooldown    = d.cooldown_remaining || 0;
    const alertKey    = d.alert_key || null;

    // ── Bias badge
    const biasBadge = document.getElementById("setupBiasBadge");
    if (biasBadge) {
        biasBadge.textContent = bias || "WAITING";
        biasBadge.className = "setup-bias-badge " + (bias === "BULLISH" ? "bullish" : bias === "BEARISH" ? "bearish" : "neutral");
    }

    // ── State badge
    const stateBadge = document.getElementById("setupStateBadge");
    if (stateBadge) {
        stateBadge.textContent = state;
        stateBadge.className   = "setup-state-badge " + state.toLowerCase();
    }

    // ── Card glow on ALERT
    const card = document.getElementById("setupTrackerCard");
    if (card) {
        card.classList.toggle("alert-active", state === "ALERT");
    }

    // ── Step 1
    _updateStep("setupStep1", "setupStep1Status", step1, state === "STEP1" && !step2, "✅", "🟡");

    // ── Step 2
    _updateStep("setupStep2", "setupStep2Status", step2, state === "STEP2" && !step3, "✅", "🟡");
    if (step2 && d.step2_detail) {
        const d2 = d.step2_detail;
        const parts = [];
        if (d2.ranging_tfs && d2.ranging_tfs.length) parts.push(d2.ranging_tfs.join("/") + " RANGING");
        if (d2.opposite_tfs && d2.opposite_tfs.length) parts.push(d2.opposite_tfs.join("/") + " reversed");
        const el = document.getElementById("setupStep2Desc");
        if (el && parts.length) el.textContent = parts.join(" | ");
    }

    // ── Step 3
    _updateStep("setupStep3", "setupStep3Status", step3, state === "STEP2" && !step3, "🔔", "⏳");
    if (pattern) {
        const el = document.getElementById("setupStep3Desc");
        if (el) el.textContent = pattern.replace(/_/g, " ") + (patternTf ? " on " + patternTf : "");
    }

    // ── Confidence bar
    const fill = document.getElementById("setupConfidenceFill");
    const pct  = document.getElementById("setupConfidencePct");
    if (fill) {
        fill.style.width = confidence + "%";
        fill.classList.toggle("high", confidence >= 60);
    }
    if (pct) pct.textContent = confidence + "%";

    // ── Zones hit
    const zonesEl = document.getElementById("setupZonesHit");
    if (zonesEl) {
        if (zonesHit.length) {
            zonesEl.innerHTML = zonesHit.map(z =>
                `<span class="zone-pill">${z.replace(/_/g, " ")}</span>`
            ).join("");
        } else {
            zonesEl.textContent = "—";
        }
    }

    // ── Pattern label
    const patEl = document.getElementById("setupPatternLabel");
    if (patEl) {
        patEl.textContent = pattern ? pattern.replace(/_/g, " ") : "—";
        patEl.style.display = pattern ? "inline-block" : "none";
    }

    // ── Alert box
    const alertBox = document.getElementById("setupAlertBox");
    const alertMsgEl = document.getElementById("setupAlertMsg");
    const cooldownEl = document.getElementById("setupCooldownBadge");

    if (state === "ALERT" && alertMsg) {
        if (alertBox) alertBox.style.display = "flex";
        if (alertMsgEl) alertMsgEl.textContent = alertMsg;
        if (cooldownEl) cooldownEl.textContent = cooldown > 0 ? `Cooldown: ${Math.ceil(cooldown/60)}m` : "";

        // Browser Notification — fire once per unique alert
        if (alertKey && alertKey !== _lastSetupAlertKey) {
            _lastSetupAlertKey = alertKey;
            _fireSetupBrowserNotification(alertMsg, bias);
        }
    } else {
        if (alertBox) alertBox.style.display = "none";
    }
}

function _updateStep(stepId, statusId, isDone, isActive, doneIcon, activeIcon) {
    const step = document.getElementById(stepId);
    const status = document.getElementById(statusId);
    if (!step || !status) return;
    step.classList.remove("step-done", "step-active");
    if (isDone) {
        step.classList.add("step-done");
        status.textContent = doneIcon;
    } else if (isActive) {
        step.classList.add("step-active");
        status.textContent = activeIcon;
    } else {
        status.textContent = "⏳";
    }
}

function _fireSetupBrowserNotification(msg, bias) {
    const emoji = bias === "BULLISH" ? "🟢" : bias === "BEARISH" ? "🔴" : "🎯";
    const title = `${emoji} AI Gold — Setup Ready!`;
    const body  = msg.replace(/\n/g, " | ");

    if (!window.Notification) return;
    if (Notification.permission === "granted") {
        new Notification(title, { body, icon: "/static/favicon.ico" });
    } else if (Notification.permission !== "denied") {
        Notification.requestPermission().then(perm => {
            if (perm === "granted") new Notification(title, { body });
        });
    }
}

/**
 * ═══════════════════════════════════════════════════════════════════════════════
 * Professional Advice & Institutional Flow Tracker
 * ═══════════════════════════════════════════════════════════════════════════════
 */
function renderProfessionalAdvice(advice) {
    if (!advice || typeof advice !== "object" || !advice.trade_setup) return;

    const setup = advice.trade_setup || {};
    const narrative = advice.market_narrative || [];
    const energy = advice.energy_budget || {};

    // ── Header Timestamps & Badges ──
    const timeEl = document.getElementById("proAdviceUpdated");
    if (timeEl && advice.updated_at) {
        timeEl.textContent = `Updated: ${advice.updated_at}`;
    }

    const actionBadge = document.getElementById("proAdviceActionBadge");
    if (actionBadge) {
        actionBadge.textContent = setup.action || "MONITORING";
        actionBadge.className = `pro-badge ${setup.badge_class || "neutral"}`;
    }

    const setupNameEl = document.getElementById("proAdviceSetupName");
    if (setupNameEl) {
        setupNameEl.textContent = setup.setup_name || "Awaiting Analysis...";
    }

    const rrBadge = document.getElementById("proAdviceRrBadge");
    if (rrBadge) {
        rrBadge.textContent = `R:R: ${setup.rr_ratio || "—"}`;
    }

    // ── Execution Matrix ──
    const actionVal = document.getElementById("proActionVal");
    if (actionVal) {
        actionVal.textContent = setup.action || "HOLD";
        let colClass = "text-gold";
        if (setup.action === "BUY") colClass = "text-green";
        else if (setup.action === "SELL") colClass = "text-red";
        else if (setup.badge_class === "weekend") colClass = "text-muted";
        else if (setup.badge_class === "caution") colClass = "text-crimson";
        actionVal.className = `pro-matrix-val ${colClass}`;
    }

    const entryVal = document.getElementById("proEntryVal");
    if (entryVal) entryVal.textContent = setup.entry_zone || "—";

    const slVal = document.getElementById("proSlVal");
    if (slVal) slVal.textContent = setup.stop_loss || "—";

    const tp1Val = document.getElementById("proTp1Val");
    if (tp1Val) tp1Val.textContent = setup.tp1 || "—";

    const tp2Val = document.getElementById("proTp2Val");
    if (tp2Val) tp2Val.textContent = setup.tp2 || "—";

    // ── Section 1: Market Narrative ──
    const narrativeTag = document.getElementById("proNarrativeTag");
    if (narrativeTag) {
        if (energy.is_weekend) {
            narrativeTag.textContent = "WEEKEND RECAP";
            narrativeTag.className = "pro-narrative-tag weekend mono";
        } else {
            narrativeTag.textContent = "TECHNICAL PA";
            narrativeTag.className = "pro-narrative-tag mono";
        }
    }

    const narrativeList = document.getElementById("proNarrativeList");
    if (narrativeList) {
        if (Array.isArray(narrative) && narrative.length > 0) {
            narrativeList.innerHTML = narrative
                .map(item => `<div class="pro-narrative-item">${item}</div>`)
                .join("");
        } else {
            narrativeList.innerHTML = `<div class="pro-narrative-item">⏳ กำลังเชื่อมโยงข้อมูลโครงสร้างราคาและแท่งเทียน...</div>`;
        }
    }

    // ── Section 2: Energy Budget & Institutional Flow ──
    const levelTag = document.getElementById("proEnergyLevelTag");
    if (levelTag) {
        const lvl = (energy.energy_level || "MODERATE").toUpperCase();
        levelTag.className = "pro-energy-level-tag mono";
        if (energy.is_weekend || lvl === "WEEKEND") {
            levelTag.textContent = "WEEKEND";
            levelTag.classList.add("weekend");
        } else if (lvl === "HIGH" || lvl === "FULL") {
            levelTag.textContent = "HIGH ENERGY";
            levelTag.classList.add("high");
        } else if (lvl === "EXHAUSTED" || lvl === "RESTRICTED") {
            levelTag.textContent = "EXHAUSTED";
            levelTag.classList.add("exhausted");
        } else if (lvl === "CHOPPY_CHURN") {
            levelTag.textContent = "MEAT GRINDER";
            levelTag.classList.add("choppy-churn");
        } else {
            levelTag.textContent = "MODERATE";
        }
    }

    const rangeUsed = document.getElementById("proRangeUsed");
    if (rangeUsed) {
        rangeUsed.textContent = `$${(energy.day_range || 0).toFixed(2)}`;
    }

    const adrTotal = document.getElementById("proAdrTotal");
    if (adrTotal) {
        adrTotal.textContent = `$${(energy.adr14 || 0).toFixed(2)}`;
    }

    const sessionTypeBadge = document.getElementById("proSessionTypeBadge");
    if (sessionTypeBadge) {
        sessionTypeBadge.textContent = energy.session_type || "NORMAL BALANCED DYNAMICS";
        sessionTypeBadge.className = `pro-session-type-badge ${energy.session_badge || 'type-normal'}`;
    }

    const energyFill = document.getElementById("proEnergyFill");
    if (energyFill) {
        const pct = Math.min(Math.max(energy.energy_used_pct || 0, 0), 100);
        energyFill.style.width = `${pct}%`;
        if (pct >= 85) {
            energyFill.classList.add("exhausted");
        } else {
            energyFill.classList.remove("exhausted");
        }
    }

    const capMark = document.getElementById("proEnergyCapMark");
    if (capMark) {
        if (energy.is_friday) {
            capMark.style.display = "block";
            capMark.style.left = `${energy.friday_cap || 65}%`;
        } else {
            capMark.style.display = "none";
        }
    }

    const energyPctEl = document.getElementById("proEnergyUsedPct");
    if (energyPctEl) {
        energyPctEl.textContent = `${energy.energy_used_pct || 0}% ADR Used`;
    }

    const energyDescEl = document.getElementById("proEnergyDesc");
    if (energyDescEl) {
        energyDescEl.textContent = energy.energy_desc || "ประเมินพลังงานคงเหลือ...";
    }

    // ── Deep Energy Quality & Dynamics Metrics ──
    const grossTravelLabelEl = document.getElementById("proGrossTravelLabel");
    if (grossTravelLabelEl) {
        const rawLabel = energy.active_session_label || energy.active_session || "Active";
        const cleanLabel = rawLabel.replace(" Session", "").trim();
        grossTravelLabelEl.textContent = `GROSS TRAVEL (4H ${cleanLabel})`;
    }

    const grossTravelEl = document.getElementById("proGrossTravel");
    if (grossTravelEl) {
        grossTravelEl.textContent = `$${(energy.gross_travel || 0).toFixed(2)}`;
    }

    const activeRangeEl = document.getElementById("proActiveRange");
    if (activeRangeEl) {
        activeRangeEl.textContent = `$${(energy.active_range || 0).toFixed(2)}`;
    }

    const travelRatioEl = document.getElementById("proTravelRatio");
    if (travelRatioEl) {
        travelRatioEl.textContent = `${(energy.travel_ratio || 1.0).toFixed(1)}x Net`;
    }

    const travelDescEl = document.getElementById("proTravelDesc");
    if (travelDescEl) {
        travelDescEl.textContent = energy.travel_desc || "วิ่งตรง ไม่สะบัดวนลูป";
    }

    const eerValEl = document.getElementById("proEerVal");
    if (eerValEl) {
        eerValEl.textContent = `${(energy.eer || 0).toFixed(1)}% EER`;
    }

    const kerBadgeEl = document.getElementById("proKerBadge");
    if (kerBadgeEl) {
        kerBadgeEl.textContent = `KER ${(energy.ker || 0.5).toFixed(2)} (${energy.ker_label || 'DRIFTING'})`;
    }

    const flowDescEl = document.getElementById("proFlowDesc");
    if (flowDescEl) {
        flowDescEl.textContent = energy.flow_desc || "ประเมินความสะอาดทิศทาง...";
    }

    const volBadgeEl = document.getElementById("proVolBadge");
    if (volBadgeEl) {
        volBadgeEl.textContent = energy.vol_badge || "BALANCED ⚖️";
        volBadgeEl.className = `mini-tag vol-state-badge ${energy.vol_color || 'blue'}`;
    }

    const atrRatioEl = document.getElementById("proAtrRatio");
    if (atrRatioEl) {
        atrRatioEl.textContent = `${(energy.atr_ratio || 1.0).toFixed(2)}x`;
    }

    const volDescEl = document.getElementById("proVolDesc");
    if (volDescEl) {
        volDescEl.textContent = energy.vol_desc || "ประเมินการอัดพลังงาน...";
    }

    const outlookDescEl = document.getElementById("proOutlookDesc");
    if (outlookDescEl) {
        outlookDescEl.textContent = energy.outlook_text || "กำลังคำนวณแนวโน้มการเข้าเทรดของสถาบัน...";
    }

    const protocolStrip = document.getElementById("proProtocolStrip");
    const protocolText = document.getElementById("proProtocolText");
    const protocolIcon = document.getElementById("proProtocolIcon");
    if (protocolText) {
        const proto = energy.day_protocol || "Active Institutional Flow";
        const warn = energy.protocol_warning ? ` • ${energy.protocol_warning}` : "";
        protocolText.textContent = `${proto}${warn}`;
    }
    if (protocolStrip) {
        if (energy.is_weekend) {
            protocolStrip.className = "pro-protocol-strip weekend";
            if (protocolIcon) protocolIcon.textContent = "🏖️";
        } else if (energy.friday_restricted) {
            protocolStrip.className = "pro-protocol-strip warning";
            if (protocolIcon) protocolIcon.textContent = "⚠️";
        } else {
            protocolStrip.className = "pro-protocol-strip";
            if (protocolIcon) protocolIcon.textContent = "🛡️";
        }
    }
}

