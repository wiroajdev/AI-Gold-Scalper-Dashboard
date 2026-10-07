"""
AI Gold Scalper — Local Web Dashboard Application
Flask Server providing real-time MT5 ingestion, AI Ensemble analysis,
configurable symbol selection, and clock-aligned scheduling.
"""

import sys
import json
import threading
from pathlib import Path
from datetime import datetime, timezone, timedelta
from flask import Flask, render_template, jsonify, request, Response

# Fix Windows console encoding (cp874 / cp1252)
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from core.mt5_fetcher import fetch_and_stage_mt5_data, get_available_gold_symbols, DEFAULT_STAGING_DIR
from core.ai_engine import analyze_staged_data
from core.scheduler import GoldScheduler
from core.setup_detector import get_setup_detector
from core.professional_advisor import get_professional_advisor

CONFIG_PATH = BASE_DIR / "config.json"


def load_config() -> dict:
    default_cfg = {
        "symbol": "XAUUSD.iux",
        "interval": "5m",
        "auto_update": False,
        "base_tf": "M5"
    }
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
                default_cfg.update(saved)
        except Exception as e:
            print(f"Error reading config.json: {e}")
    return default_cfg


def save_config(cfg: dict):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        print(f"Error writing config.json: {e}")


app_config = load_config()
current_symbol = app_config.get("symbol", "XAUUSD.iux")
current_base_tf = app_config.get("base_tf", "M5")
available_symbols_cache = []

app = Flask(__name__, template_folder=str(BASE_DIR / "templates"), static_folder=str(BASE_DIR / "static"))
app.json.sort_keys = False
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

# State storage
latest_data = {
    "status": "pending",
    "symbol": current_symbol,
    "latest_bar_time": "Connecting to MT5...",
    "current_price": 0.0,
    "execution_timeframe": current_base_tf,
    "regime": {},
    "ensemble": {},
    "multi_timeframe": {},
    "last_error": None
}
latest_setup_status: dict = {"state": "IDLE", "bias": None}  # MTF Setup Tracker state
latest_professional_advice: dict = {}  # Professional Advice & Institutional Flow state
data_lock = threading.Lock()


def run_fetch_and_analysis_cycle():
    """Worker job: fetches data from MT5 (Hybrid Mode).
    Tries MT5 direct connection first; if MT5 is unavailable, falls back to
    reading existing CSV files from the staging directory.
    """
    global latest_data, latest_setup_status, latest_professional_advice, available_symbols_cache, current_base_tf
    try:
        ts = datetime.now().strftime('%H:%M:%S')
        print(f"[{ts}] Executing MT5 Fetch & AI Analysis cycle for symbol '{current_symbol}' (Base TF: {current_base_tf})...")

        # --- Step 1: Try MT5 direct fetch ---
        fetch_res = fetch_and_stage_mt5_data(target_symbol=current_symbol, primary_tf=current_base_tf)
        mt5_ok = fetch_res.get("status") == "success"

        if mt5_ok:
            # MT5 succeeded — update symbols cache and bar time metadata
            if "available_symbols" in fetch_res:
                available_symbols_cache = fetch_res["available_symbols"]
            print(f"[{datetime.now().strftime('%H:%M:%S')}] MT5 fetch OK. Running analysis...")
        else:
            err_msg = fetch_res.get("message", "Unknown MT5 fetch error")
            print(f"[{datetime.now().strftime('%H:%M:%S')}] MT5 unavailable: {err_msg}")
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Fallback: analysing existing CSV files in staging dir...")

        # --- Step 2: Analyse staged CSVs (works whether MT5 fetched fresh data or not) ---
        analysis_res = analyze_staged_data(staging_dir=DEFAULT_STAGING_DIR, primary_tf=current_base_tf)
        if analysis_res.get("status") != "success":
            err_msg = analysis_res.get("message", "Unknown Analysis error")
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Analysis Failed: {err_msg}")
            with data_lock:
                latest_data["last_error"] = err_msg
                latest_data["status"] = "error"
            return

        # --- Step 3: Run MTF Setup Detector (State Machine) ---
        try:
            from core.ai_engine import _load_staged_csvs  # internal helper
            data_store = _load_staged_csvs(DEFAULT_STAGING_DIR)
            mtf_regimes = analysis_res.get("_mtf_regimes", {})
            if mtf_regimes and data_store:
                detector = get_setup_detector()
                setup_result = detector.evaluate(mtf_regimes, data_store)
                with data_lock:
                    latest_setup_status = setup_result
        except Exception as se:
            print(f"[SetupDetector] Non-fatal error: {se}")

        # --- Step 4: Run Professional Advisor Engine ---
        try:
            advisor = get_professional_advisor()
            session_res = compute_session_levels_dict()
            sr_res = compute_order_flow_levels_dict()

            curr_px = float(analysis_res.get("latest_price") or analysis_res.get("current_price") or latest_data.get("latest_price") or latest_data.get("current_price") or 0.0)
            if curr_px == 0.0 and data_store:
                df_m5_tmp = data_store.get("M5")
                if df_m5_tmp is not None and len(df_m5_tmp) > 0:
                    curr_px = float(df_m5_tmp["Close"].iloc[-1])

            advice_res = advisor.evaluate(
                current_price=curr_px,
                mtf_regimes=mtf_regimes if mtf_regimes else {},
                session_levels=session_res if session_res.get("status") == "success" else {},
                sr_levels=sr_res.get("levels", []) if sr_res.get("status") == "success" else [],
                setup_status=latest_setup_status,
                data_store=data_store if data_store else {},
            )
            with data_lock:
                latest_professional_advice = advice_res
            print(
                f"[{datetime.now().strftime('%H:%M:%S')}] Professional Advice: "
                f"{advice_res.get('trade_setup', {}).get('action')} | "
                f"Setup: {advice_res.get('trade_setup', {}).get('setup_name')} | "
                f"Energy: {advice_res.get('energy_budget', {}).get('energy_level')}"
            )
        except Exception as pae:
            print(f"[ProfessionalAdvisor] Non-fatal error: {pae}")

        with data_lock:
            latest_data.update(analysis_res)
            latest_data["symbol"] = current_symbol
            latest_data["execution_timeframe"] = current_base_tf
            latest_data["last_error"] = None if mt5_ok else fetch_res.get("message")
            latest_data["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            latest_data["data_source"] = "MT5 Live" if mt5_ok else "CSV Cached"

            # Copy MT5 bar time metadata when available
            if mt5_ok and "latest_bar_time" in fetch_res:
                latest_data["latest_bar_time"] = fetch_res["latest_bar_time"]
                latest_data["latest_broker_time"] = fetch_res.get("latest_broker_time")
                latest_data["latest_thai_time"] = fetch_res.get("latest_thai_time")
                latest_data["broker_timezone"] = fetch_res.get("broker_timezone")
                latest_data["staging_dir"] = fetch_res.get("staging_dir")
                latest_data["latest_price"] = fetch_res.get("latest_price")  # Bug #1 fix
                latest_data["current_price"] = fetch_res.get("latest_price")

        print(
            f"[{datetime.now().strftime('%H:%M:%S')}] Cycle complete! "
            f"Symbol: {current_symbol} | Base TF: {current_base_tf} | "
            f"Source: {'MT5' if mt5_ok else 'CSV'} | "
            f"Latest Bar: {latest_data.get('latest_bar_time')} | "
            f"Bias: {latest_data.get('directional_bias', {}).get('directional_bias')} "
            f"(Edge: {latest_data.get('directional_bias', {}).get('edge_score')}/100)"
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        with data_lock:
            latest_data["last_error"] = str(e)
            latest_data["status"] = "error"


# Initialize scheduler with cycle callback
scheduler = GoldScheduler(callback_task=run_fetch_and_analysis_cycle)
scheduler.interval_key = app_config.get("interval", "5m")
if app_config.get("auto_update", False):
    scheduler.set_enabled(True)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/report")
def report():
    return render_template("ensemble_analysis_report.html")


@app.route("/guide")
def user_guide():
    # Try multiple possible locations for the guide file
    possible_paths = [
        BASE_DIR / "USER_GUIDE_AND_INTERPRETATION.md",
        BASE_DIR.parent / "USER_GUIDE_AND_INTERPRETATION.md",
        Path("USER_GUIDE_AND_INTERPRETATION.md"),
    ]
    md_content = None
    found_path = None
    for p in possible_paths:
        if p.exists():
            md_content = p.read_text(encoding="utf-8")
            found_path = str(p)
            break
    if md_content is None:
        md_content = f"# User Guide\n\nFile not found.\n\nSearched paths:\n" + "\n".join(f"- `{p}`" for p in possible_paths)
    try:
        import markdown as md_lib
        html_body = md_lib.markdown(
            md_content,
            extensions=["tables", "fenced_code", "nl2br", "toc"],
        )
    except ImportError:
        import html as html_module
        html_body = "<pre>" + html_module.escape(md_content) + "</pre>"
    page = f"""<!DOCTYPE html>
<html lang='th'>
<head>
<meta charset='UTF-8'>
<meta name='viewport' content='width=device-width, initial-scale=1.0'>
<title>User Guide — AI Gold Scalper Dashboard</title>
<link rel='preconnect' href='https://fonts.googleapis.com'>
<link href='https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap' rel='stylesheet'>
<style>
  :root {{
    --bg: #0d1117; --surface: #161b22; --border: #30363d;
    --text: #e6edf3; --muted: #8b949e; --accent: #f59e0b;
    --green: #3fb950; --red: #f85149; --blue: #58a6ff;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text); font-family: 'Inter', sans-serif;
          font-size: 0.95rem; line-height: 1.75; padding: 2rem 1rem; }}
  .page-wrapper {{ max-width: 900px; margin: 0 auto; }}
  .back-btn {{ display: inline-flex; align-items: center; gap: 0.5rem;
               background: rgba(245,158,11,0.1); color: var(--accent);
               border: 1px solid rgba(245,158,11,0.3); border-radius: 8px;
               padding: 0.5rem 1.1rem; font-size: 0.85rem; font-weight: 600;
               text-decoration: none; margin-bottom: 2rem;
               transition: all 0.2s; }}
  .back-btn:hover {{ background: rgba(245,158,11,0.2); }}
  h1 {{ font-size: 1.9rem; font-weight: 800; color: var(--accent);
        border-bottom: 2px solid rgba(245,158,11,0.3); padding-bottom: 0.75rem; margin: 1.5rem 0 1rem; }}
  h2 {{ font-size: 1.35rem; font-weight: 700; color: var(--blue);
        margin: 2rem 0 0.75rem; padding: 0.4rem 0 0.4rem 0.8rem;
        border-left: 3px solid var(--blue); }}
  h3 {{ font-size: 1.1rem; font-weight: 600; color: var(--green); margin: 1.5rem 0 0.5rem; }}
  h4 {{ font-size: 1rem; font-weight: 600; color: var(--accent); margin: 1.2rem 0 0.4rem; }}
  p {{ margin: 0.6rem 0; color: var(--text); }}
  ul, ol {{ padding-left: 1.5rem; margin: 0.5rem 0; }}
  li {{ margin: 0.3rem 0; }}
  code {{ background: rgba(255,255,255,0.07); color: #79c0ff;
          padding: 0.15em 0.4em; border-radius: 4px;
          font-family: 'JetBrains Mono', monospace; font-size: 0.88em; }}
  pre {{ background: var(--surface); border: 1px solid var(--border);
         border-radius: 10px; padding: 1.2rem; overflow-x: auto;
         margin: 1rem 0; }}
  pre code {{ background: transparent; color: #e6edf3; padding: 0; }}
  table {{ width: 100%; border-collapse: collapse; margin: 1rem 0;
           background: var(--surface); border-radius: 10px; overflow: hidden; }}
  th {{ background: rgba(245,158,11,0.15); color: var(--accent);
        font-weight: 700; padding: 0.7rem 1rem; text-align: left;
        border-bottom: 2px solid rgba(245,158,11,0.3); font-size: 0.85rem; }}
  td {{ padding: 0.65rem 1rem; border-bottom: 1px solid var(--border); color: var(--text); }}
  tr:last-child td {{ border-bottom: none; }}
  tr:hover td {{ background: rgba(255,255,255,0.03); }}
  blockquote {{ border-left: 3px solid var(--accent); margin: 1rem 0;
                padding: 0.5rem 1rem; background: rgba(245,158,11,0.06);
                border-radius: 0 8px 8px 0; color: var(--muted); }}
  hr {{ border: none; border-top: 1px solid var(--border); margin: 2rem 0; }}
  a {{ color: var(--blue); text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  strong {{ color: #f0f6fc; font-weight: 600; }}
  em {{ color: var(--muted); }}
</style>
</head>
<body>
<div class='page-wrapper'>
  <a href='/' class='back-btn'>← กลับ Dashboard</a>
  {html_body}
</div>
</body>
</html>"""
    return Response(page, mimetype="text/html")


@app.route("/api/status", methods=["GET"])
def api_status():
    with data_lock:
        data_copy = dict(latest_data)
        setup_copy = dict(latest_setup_status)
        advice_copy = dict(latest_professional_advice)

    sched_status = scheduler.get_status()
    return jsonify({
        "data": data_copy,
        "symbol": current_symbol,
        "base_tf": current_base_tf,
        "available_symbols": available_symbols_cache,
        "scheduler": sched_status,
        "setup_status": setup_copy,
        "professional_advice": advice_copy,
        "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })


@app.route("/api/professional_advice", methods=["GET"])
def api_professional_advice():
    """Returns the latest Professional Advice & Institutional Flow analysis."""
    with data_lock:
        advice_copy = dict(latest_professional_advice)
    return jsonify(advice_copy or {"status": "pending"})


@app.route("/api/settings", methods=["POST"])
def api_settings():
    global current_symbol, current_base_tf
    payload = request.get_json() or {}
    symbol_changed = False
    tf_changed = False

    if "symbol" in payload:
        new_sym = str(payload["symbol"]).strip()
        if new_sym and new_sym != current_symbol:
            current_symbol = new_sym
            app_config["symbol"] = current_symbol
            symbol_changed = True

    if "base_tf" in payload:
        new_tf = str(payload["base_tf"]).strip().upper()
        if new_tf in ["M1", "M5", "M15", "H1", "H4", "D1"] and new_tf != current_base_tf:
            current_base_tf = new_tf
            app_config["base_tf"] = current_base_tf
            tf_changed = True

    if "enabled" in payload:
        enabled = bool(payload["enabled"])
        scheduler.set_enabled(enabled)
        app_config["auto_update"] = enabled

    if "interval" in payload:
        interval_key = str(payload["interval"]).strip()
        scheduler.set_interval(interval_key)
        app_config["interval"] = interval_key

    save_config(app_config)

    if symbol_changed or tf_changed:
        scheduler.trigger_immediate_run()

    return jsonify({
        "status": "ok",
        "symbol": current_symbol,
        "base_tf": current_base_tf,
        "scheduler": scheduler.get_status()
    })


@app.route("/api/fetch_now", methods=["POST"])
def api_fetch_now():
    scheduler.trigger_immediate_run()
    return jsonify({"status": "ok", "message": "Immediate fetch and analysis triggered."})


@app.route("/api/chart_data/<tf>", methods=["GET"])
def api_chart_data(tf):
    """Provides candlestick and volume data formatted for TradingView Lightweight Charts."""
    tf = tf.upper()
    if tf not in ["M1", "M5", "M15", "H1", "H4", "D1"]:
        return jsonify({"status": "error", "message": f"Invalid timeframe: {tf}"}), 400

    csv_file = DEFAULT_STAGING_DIR / f"XAUUSD_{tf}.csv"
    if not csv_file.exists():
        fallback = Path(__file__).resolve().parent.parent / "exportedpricedata" / f"XAUUSD_{tf}.csv"
        if fallback.exists():
            csv_file = fallback
        else:
            return jsonify({"status": "error", "message": f"CSV file not found for {tf}"}), 404

    broker_tz = "UTC+1"
    raw_candles = []
    raw_volumes = []
    try:
        with open(csv_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if line.startswith("#"):
                    if "Timezone," in line:
                        parts = line.split(",")
                        for idx, p in enumerate(parts):
                            if p == "Timezone" and idx + 1 < len(parts):
                                broker_tz = parts[idx + 1].strip()
                    continue
                if line.startswith("Time,") or line.startswith("time,"):
                    continue

                parts = line.split(",")
                if len(parts) < 5:
                    continue

                t_str = parts[0].strip()
                try:
                    o_val = float(parts[1])
                    h_val = float(parts[2])
                    l_val = float(parts[3])
                    c_val = float(parts[4])
                    vol_val = float(parts[5]) if len(parts) > 5 else 0.0

                    if len(t_str) == 10:
                        dt = datetime.strptime(t_str, "%Y.%m.%d")
                    else:
                        dt = datetime.strptime(t_str, "%Y.%m.%d %H:%M")

                    tz_offset = 1
                    if "UTC+" in broker_tz:
                        tz_offset = int(broker_tz.replace("UTC+", ""))
                    elif "UTC-" in broker_tz:
                        tz_offset = -int(broker_tz.replace("UTC-", ""))

                    utc_dt = dt - timedelta(hours=tz_offset)
                    ts = int(utc_dt.replace(tzinfo=timezone.utc).timestamp())

                    color = "rgba(16, 185, 129, 0.45)" if c_val >= o_val else "rgba(239, 68, 68, 0.45)"
                    raw_candles.append({
                        "time": ts,
                        "open": o_val,
                        "high": h_val,
                        "low": l_val,
                        "close": c_val
                    })
                    raw_volumes.append({
                        "time": ts,
                        "value": vol_val,
                        "color": color
                    })
                except Exception:
                    continue

        seen_times = set()
        candles = []
        volumes = []
        for c, v in zip(raw_candles, raw_volumes):
            if c["time"] not in seen_times:
                seen_times.add(c["time"])
                candles.append(c)
                volumes.append(v)

        candles.sort(key=lambda x: x["time"])
        volumes.sort(key=lambda x: x["time"])

        return jsonify({
            "status": "success",
            "timeframe": tf,
            "broker_tz": broker_tz,
            "candles": candles,
            "volumes": volumes,
            "count": len(candles),
            "latest_price": candles[-1]["close"] if candles else 0.0
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500



@app.route("/api/setup_status", methods=["GET"])
def api_setup_status():
    """Returns current MTF Setup Tracker state (3-step trading plan)."""
    with data_lock:
        status_copy = dict(latest_setup_status)
    return jsonify(status_copy)


def compute_session_levels_dict() -> dict:
    """
    Calculates Asian Range and London Range High/Low levels using fixed
    Thai-time (ICT, UTC+7) cut-off windows from M5 CSV data.
    """
    # Try M5 first, fallback to M15 for session resolution
    csv_file = DEFAULT_STAGING_DIR / "XAUUSD_M5.csv"
    if not csv_file.exists():
        csv_file = DEFAULT_STAGING_DIR / "XAUUSD_M15.csv"
    if not csv_file.exists():
        return {
            "status": "error",
            "message": "No M5/M15 CSV found for session level calculation"
        }

    broker_tz_offset = 1  # Default broker UTC+1
    rows = []

    try:
        with open(csv_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if line.startswith("#"):
                    if "Timezone," in line:
                        parts = line.split(",")
                        for idx, p in enumerate(parts):
                            if p == "Timezone" and idx + 1 < len(parts):
                                tz_str = parts[idx + 1].strip()
                                if "UTC+" in tz_str:
                                    broker_tz_offset = int(tz_str.replace("UTC+", ""))
                                elif "UTC-" in tz_str:
                                    broker_tz_offset = -int(tz_str.replace("UTC-", ""))
                    continue
                if line.lower().startswith("time,"):
                    continue

                parts = line.split(",")
                if len(parts) < 5:
                    continue
                try:
                    t_str = parts[0].strip()
                    h_val = float(parts[2])
                    l_val = float(parts[3])
                    dt_broker = datetime.strptime(t_str, "%Y.%m.%d %H:%M")
                    # Convert broker time → UTC → Thai time (UTC+7)
                    dt_utc = dt_broker - timedelta(hours=broker_tz_offset)
                    dt_thai = dt_utc + timedelta(hours=7)
                    rows.append({"dt_thai": dt_thai, "high": h_val, "low": l_val})
                except Exception:
                    continue
    except Exception as e:
        return {"status": "error", "message": str(e)}

    if not rows:
        return {"status": "error", "message": "No valid rows parsed"}

    # Use today's date in Thai time relative to latest bar
    latest_thai = rows[-1]["dt_thai"]
    today_date = latest_thai.date()

    # Session cut-off windows (Thai time)
    asian_start = datetime.combine(today_date, datetime.min.time()).replace(hour=7, minute=0)
    asian_end   = datetime.combine(today_date, datetime.min.time()).replace(hour=13, minute=30)
    london_start = datetime.combine(today_date, datetime.min.time()).replace(hour=14, minute=0)
    london_end   = datetime.combine(today_date, datetime.min.time()).replace(hour=19, minute=30)

    asian_rows  = [r for r in rows if asian_start  <= r["dt_thai"] <= asian_end]
    london_rows = [r for r in rows if london_start <= r["dt_thai"] <= london_end]

    return {
        "status": "success",
        "reference_date": today_date.strftime("%Y-%m-%d"),
        "latest_bar_thai": latest_thai.strftime("%Y-%m-%d %H:%M"),
        "broker_tz": f"UTC+{broker_tz_offset}",
        "asian": {
            "high": round(max(r["high"] for r in asian_rows), 2) if asian_rows else None,
            "low":  round(min(r["low"]  for r in asian_rows), 2) if asian_rows else None,
            "bars": len(asian_rows),
            "window": "07:00–13:30 ICT"
        },
        "london": {
            "high": round(max(r["high"] for r in london_rows), 2) if london_rows else None,
            "low":  round(min(r["low"]  for r in london_rows), 2) if london_rows else None,
            "bars": len(london_rows),
            "window": "14:00–19:30 ICT"
        }
    }


@app.route("/api/session_levels", methods=["GET"])
def api_session_levels():
    res = compute_session_levels_dict()
    if res.get("status") != "success":
        status_code = 500 if "No valid" in res.get("message", "") else 404
        return jsonify(res), status_code
    return jsonify(res)


def compute_order_flow_levels_dict() -> dict:
    """
    Computes Order Flow / Market Structure Key Levels for the current trading day.

    Logic based on session-breakout flip zones and swing structure:
      1. London Breakout Flip Zones  — If price broke above London High (bullish breakout),
         that level becomes primary support (demand zone). If it broke below London Low,
         that becomes primary resistance (supply zone).
      2. Asian Range Flip Zones      — Asian H/L that were violated during London/NY act as
         secondary S/R flip levels.
      3. Significant Swing Highs/Lows — Identified from H1 data: recent swing high that
         was broken (now demand), recent swing low that was broken (now supply).
      4. Intraday Order Blocks        — Last bearish candle before a bullish impulse move
         (demand OB), and last bullish candle before a bearish impulse (supply OB).
         Uses M5 data, minimum 3-candle impulse threshold.
    """
    # Load M5 CSV (primary) — fallback to M15
    csv_m5 = DEFAULT_STAGING_DIR / "XAUUSD_M5.csv"
    csv_h1 = DEFAULT_STAGING_DIR / "XAUUSD_H1.csv"
    if not csv_m5.exists():
        return {"status": "error", "message": "M5 CSV not found"}

    broker_tz_offset = 1

    def parse_csv(path):
        """Parse OHLCV CSV into list of dicts with dt_thai and price fields."""
        rows = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith("#"):
                        if "Timezone," in line:
                            parts = line.split(",")
                            for idx, p in enumerate(parts):
                                if p == "Timezone" and idx + 1 < len(parts):
                                    tz_str = parts[idx + 1].strip()
                                    nonlocal broker_tz_offset
                                    if "UTC+" in tz_str:
                                        broker_tz_offset = int(tz_str.replace("UTC+", ""))
                                    elif "UTC-" in tz_str:
                                        broker_tz_offset = -int(tz_str.replace("UTC-", ""))
                        continue
                    if line.lower().startswith("time,"):
                        continue
                    parts = line.split(",")
                    if len(parts) < 5:
                        continue
                    try:
                        t_str = parts[0].strip()
                        o_val = float(parts[1])
                        h_val = float(parts[2])
                        l_val = float(parts[3])
                        c_val = float(parts[4])
                        dt_broker = datetime.strptime(t_str, "%Y.%m.%d %H:%M")
                        dt_utc = dt_broker - timedelta(hours=broker_tz_offset)
                        dt_thai = dt_utc + timedelta(hours=7)
                        rows.append({
                            "dt_thai": dt_thai,
                            "open": o_val, "high": h_val,
                            "low": l_val, "close": c_val
                        })
                    except Exception:
                        continue
        except Exception:
            pass
        return rows

    m5_rows = parse_csv(csv_m5)
    h1_rows = parse_csv(csv_h1) if csv_h1.exists() else []

    if not m5_rows:
        return {"status": "error", "message": "No valid M5 data"}

    latest_thai = m5_rows[-1]["dt_thai"]
    today_date = latest_thai.date()

    # ── Session windows (Thai time / ICT UTC+7) ──────────────────────────────
    asian_start  = datetime.combine(today_date, datetime.min.time()).replace(hour=7,  minute=0)
    asian_end    = datetime.combine(today_date, datetime.min.time()).replace(hour=13, minute=30)
    london_start = datetime.combine(today_date, datetime.min.time()).replace(hour=14, minute=0)
    london_end   = datetime.combine(today_date, datetime.min.time()).replace(hour=19, minute=30)
    ny_start     = datetime.combine(today_date, datetime.min.time()).replace(hour=19, minute=30)
    # "Pre-London" window = everything before London opens (last 24h max)
    pre_london_cutoff = london_start - timedelta(hours=24)

    asian_rows      = [r for r in m5_rows if asian_start  <= r["dt_thai"] <= asian_end]
    london_rows     = [r for r in m5_rows if london_start <= r["dt_thai"] <= london_end]
    ny_rows         = [r for r in m5_rows if r["dt_thai"] >= ny_start]
    # Pre-London: Asian + Previous NY/London session (up to 24h before current London open)
    pre_london_rows = [r for r in m5_rows if pre_london_cutoff <= r["dt_thai"] < london_start]

    levels = []

    # ── 1. Compute Session Ranges ─────────────────────────────────────────────
    asian_high  = round(max(r["high"] for r in asian_rows), 2) if asian_rows else None
    asian_low   = round(min(r["low"]  for r in asian_rows), 2) if asian_rows else None
    london_high = round(max(r["high"] for r in london_rows), 2) if london_rows else None
    london_low  = round(min(r["low"]  for r in london_rows), 2) if london_rows else None

    # Pre-London structural swing high/low (the KEY level that 4335 represents)
    # Find the most significant swing high BEFORE London that London broke above
    # Strategy: find local swing highs in pre-London data using a 5-bar pivot
    pre_london_swing_highs = []
    pre_london_swing_lows  = []
    if len(pre_london_rows) >= 11:
        for i in range(5, len(pre_london_rows) - 5):
            # Pivot High: bar[i] is highest of surrounding 5 bars on each side
            pivot_h = pre_london_rows[i]["high"]
            left_h  = [pre_london_rows[j]["high"] for j in range(i-5, i)]
            right_h = [pre_london_rows[j]["high"] for j in range(i+1, i+6)]
            if pivot_h > max(left_h) and pivot_h > max(right_h):
                pre_london_swing_highs.append(round(pivot_h, 2))

            # Pivot Low
            pivot_l = pre_london_rows[i]["low"]
            left_l  = [pre_london_rows[j]["low"] for j in range(i-5, i)]
            right_l = [pre_london_rows[j]["low"] for j in range(i+1, i+6)]
            if pivot_l < min(left_l) and pivot_l < min(right_l):
                pre_london_swing_lows.append(round(pivot_l, 2))

    # Current price (last close)
    current_price = m5_rows[-1]["close"]

    # ── 2. London Breakout Flip Zones (Today's London H/L) ───────────────────
    if london_high and ny_rows:
        ny_high = max(r["high"] for r in ny_rows)
        ny_low  = min(r["low"]  for r in ny_rows)
        # Bullish breakout: NY traded above London High → London High = Demand (Support Flip)
        if ny_high > london_high:
            levels.append({
                "price": london_high,
                "type": "demand",
                "label": f"London High Flip (Support) {london_high:.2f}",
                "short_label": f"L.High Flip ▲",
                "color": "#10b981",
                "lineStyle": "solid",
                "lineWidth": 2,
                "zone": True,
                "zone_top": round(london_high + 1.5, 2),
                "zone_bottom": round(london_high - 1.5, 2),
                "description": "London High broken → now acts as Support (Demand Zone / Order Flow Buy Area)",
                "session": "london_flip"
            })
        # Bearish breakout: NY traded below London Low → London Low = Supply (Resistance Flip)
        if ny_low < (london_low or 0):
            levels.append({
                "price": london_low,
                "type": "supply",
                "label": f"London Low Flip (Resistance) {london_low:.2f}",
                "short_label": f"L.Low Flip ▼",
                "color": "#ef4444",
                "lineStyle": "solid",
                "lineWidth": 2,
                "zone": True,
                "zone_top": round(london_low + 1.5, 2),
                "zone_bottom": round(london_low - 1.5, 2),
                "description": "London Low broken → now acts as Resistance (Supply Zone / Order Flow Sell Area)",
                "session": "london_flip"
            })

    # ── 2b. London Intra-Session Structural Swing Flip ────────────────────────
    # KEY CONCEPT: During London's bullish/bearish move, there are intermediate
    # swing highs/lows that get broken on the way up/down.
    # Example: London opens at 14:00, builds a high at 4335 (swing high), then
    # continues higher to 4374. That 4335 pivot becomes the key support for NY.
    # This is the "4335 pattern" the user described.
    if len(london_rows) >= 11:
        london_swing_highs = []
        london_swing_lows  = []
        for i in range(5, len(london_rows) - 5):
            # Pivot High: 5-bar pivot
            ph = london_rows[i]["high"]
            lh = [london_rows[j]["high"] for j in range(i-5, i)]
            rh = [london_rows[j]["high"] for j in range(i+1, i+6)]
            if ph > max(lh) and ph > max(rh):
                london_swing_highs.append((round(ph, 2), i))

            # Pivot Low: 5-bar pivot
            pl = london_rows[i]["low"]
            ll = [london_rows[j]["low"] for j in range(i-5, i)]
            rl = [london_rows[j]["low"] for j in range(i+1, i+6)]
            if pl < min(ll) and pl < min(rl):
                london_swing_lows.append((round(pl, 2), i))

        # Bullish case: London intra-session swing highs that were subsequently broken
        # (meaning a later part of London traded above them) → become Support for NY
        if london_high and ny_rows:
            ny_high = max(r["high"] for r in ny_rows)
            for (sh, bar_idx) in london_swing_highs:
                # Swing high must be: below London High (was broken), and above London open area
                is_broken = london_high > sh
                not_too_close_to_london_high = (london_high - sh) > 2.0
                above_midpoint = sh > (london_rows[0]["low"] if london_rows else 0)
                if is_broken and not_too_close_to_london_high and above_midpoint:
                    levels.append({
                        "price": sh,
                        "type": "demand",
                        "label": f"London Swing High Flip (Support) {sh:.2f}",
                        "short_label": "L.Swing ▲",
                        "color": "#34d399",
                        "lineStyle": "solid",
                        "lineWidth": 2,
                        "zone": True,
                        "zone_top": round(sh + 2.0, 2),
                        "zone_bottom": round(sh - 2.0, 2),
                        "description": (
                            f"London intra-session swing high {sh:.2f} was broken during London's "
                            f"bullish continuation → now a primary NY session Support / Demand flip zone. "
                            f"This is the key 'London Broken Structure' level for NY trading."
                        ),
                        "session": "london_swing_flip"
                    })

        # Bearish case: London intra-session swing lows broken → become Resistance for NY
        # Limit to 1 (most relevant = closest to current price)
        if london_low and ny_rows:
            swing_low_candidates_sorted = sorted(
                [(sl, idx) for (sl, idx) in london_swing_lows
                 if (sl - london_low) > 2.0 and london_low < sl],
                key=lambda x: abs(x[0] - current_price)
            )
            # Keep only the 1 most relevant bearish swing flip
            for (sl, bar_idx) in swing_low_candidates_sorted[:1]:
                levels.append({
                    "price": sl,
                    "type": "supply",
                    "label": f"London Swing Low Flip (Resistance) {sl:.2f}",
                    "short_label": "L.Swing ▼",
                    "color": "#f87171",
                    "lineStyle": "dashed",
                    "lineWidth": 1,
                    "zone": True,
                    "zone_top": round(sl + 2.0, 2),
                    "zone_bottom": round(sl - 2.0, 2),
                    "description": (
                        f"London intra-session swing low {sl:.2f} was broken during London's "
                        f"bearish continuation → now a Resistance flip. Only relevant if price pulls back here."
                    ),
                    "session": "london_swing_flip"
                })

    # ── 3. Asian Range Flip Zones ─────────────────────────────────────────────

    if asian_high and london_rows:
        london_max = max(r["high"] for r in london_rows)
        if london_max > asian_high:
            levels.append({
                "price": asian_high,
                "type": "demand",
                "label": f"Asian High Flip (Support) {asian_high:.2f}",
                "short_label": "A.High Flip ▲",
                "color": "#22d3ee",
                "lineStyle": "dashed",
                "lineWidth": 1,
                "zone": True,
                "zone_top": round(asian_high + 1.0, 2),
                "zone_bottom": round(asian_high - 1.0, 2),
                "description": "Asian High broken by London → Judas Swing cleared, now acts as intraday Support",
                "session": "asian_flip"
            })

    if asian_low and london_rows:
        london_min = min(r["low"] for r in london_rows)
        if london_min < asian_low:
            levels.append({
                "price": asian_low,
                "type": "supply",
                "label": f"Asian Low Flip (Resistance) {asian_low:.2f}",
                "short_label": "A.Low Flip ▼",
                "color": "#f97316",
                "lineStyle": "dashed",
                "lineWidth": 1,
                "zone": True,
                "zone_top": round(asian_low + 1.0, 2),
                "zone_bottom": round(asian_low - 1.0, 2),
                "description": "Asian Low broken by London → Judas Swing cleared, now acts as intraday Resistance",
                "session": "asian_flip"
            })

    # ── 4. H1 Swing Structure Flip Levels ────────────────────────────────────
    # NOTE: Pre-London Flip levels removed — too noisy/redundant vs London Swing Flips.

    if len(h1_rows) >= 10:
        # Look at last 20 H1 bars only
        recent_h1 = h1_rows[-20:]
        swing_high_candidates = sorted(recent_h1[:-3], key=lambda r: r["high"], reverse=True)[:3]
        swing_low_candidates  = sorted(recent_h1[:-3], key=lambda r: r["low"])[:3]

        last_high = max(r["high"] for r in recent_h1[-3:])
        last_low  = min(r["low"]  for r in recent_h1[-3:])

        for sh in swing_high_candidates:
            if last_high > sh["high"] and sh["high"] > (london_high or 0) - 5:
                # Swing high broken → becomes support demand zone
                levels.append({
                    "price": round(sh["high"], 2),
                    "type": "demand",
                    "label": f"H1 Swing High Flip {sh['high']:.2f}",
                    "short_label": "H1 Swing ▲",
                    "color": "#a3e635",
                    "lineStyle": "dashed",
                    "lineWidth": 1,
                    "zone": False,
                    "description": "H1 Swing High was broken → BOS (Break of Structure) confirmed, now a key demand level",
                    "session": "structure"
                })
                break

        for sl in swing_low_candidates:
            if last_low < sl["low"] and sl["low"] < (london_low or 9999) + 5:
                levels.append({
                    "price": round(sl["low"], 2),
                    "type": "supply",
                    "label": f"H1 Swing Low Flip {sl['low']:.2f}",
                    "short_label": "H1 Swing ▼",
                    "color": "#fb923c",
                    "lineStyle": "dashed",
                    "lineWidth": 1,
                    "zone": False,
                    "description": "H1 Swing Low was broken → BOS confirmed, now a key supply level",
                    "session": "structure"
                })
                break

    # ── 5. Intraday M5 Order Blocks (last 100 bars) ──────────────────────────
    recent_m5 = m5_rows[-100:]
    demand_obs = []
    supply_obs = []

    for i in range(2, len(recent_m5) - 3):
        # Demand OB: bearish candle (i) followed by 3+ consecutive bullish closes
        if recent_m5[i]["close"] < recent_m5[i]["open"]:  # bearish candle
            next_3 = recent_m5[i+1:i+4]
            if all(r["close"] > r["open"] for r in next_3):
                impulse_move = next_3[-1]["close"] - recent_m5[i]["low"]
                if impulse_move >= 3.0:  # Minimum $3 impulse for XAU
                    ob_high = round(recent_m5[i]["high"], 2)
                    ob_low = round(recent_m5[i]["low"], 2)
                    ob_mid = round((ob_high + ob_low) / 2, 2)

                    # SMC Validation: Must be unbroken and at or below current price (Active Demand / Support)
                    subsequent_bars = recent_m5[i+4:]
                    is_broken = any(r["close"] < ob_low for r in subsequent_bars)

                    if not is_broken and current_price >= ob_low:
                        demand_obs.append({
                            "price": ob_mid,
                            "ob_high": ob_high,
                            "ob_low": ob_low,
                            "bar_idx": i,
                            "impulse": round(impulse_move, 2)
                        })

        # Supply OB: bullish candle (i) followed by 3+ consecutive bearish closes
        if recent_m5[i]["close"] > recent_m5[i]["open"]:  # bullish candle
            next_3 = recent_m5[i+1:i+4]
            if all(r["close"] < r["open"] for r in next_3):
                impulse_move = recent_m5[i]["high"] - next_3[-1]["close"]
                if impulse_move >= 3.0:
                    ob_high = round(recent_m5[i]["high"], 2)
                    ob_low = round(recent_m5[i]["low"], 2)
                    ob_mid = round((ob_high + ob_low) / 2, 2)

                    # SMC Validation: Must be unbroken and at or above current price (Active Supply / Resistance)
                    subsequent_bars = recent_m5[i+4:]
                    is_broken = any(r["close"] > ob_high for r in subsequent_bars)

                    if not is_broken and current_price <= ob_high:
                        supply_obs.append({
                            "price": ob_mid,
                            "ob_high": ob_high,
                            "ob_low": ob_low,
                            "bar_idx": i,
                            "impulse": round(impulse_move, 2)
                        })

    # Keep only the most recent 2 active OBs closest to current price
    if demand_obs:
        best_demand_ob = sorted(demand_obs, key=lambda ob: current_price - ob["price"])[:2]
        for ob in best_demand_ob:
            levels.append({
                "price": ob["price"],
                "type": "demand_ob",
                "label": f"Demand OB {ob['ob_low']:.2f}–{ob['ob_high']:.2f}",
                "short_label": f"Demand OB",
                "color": "#34d399",
                "lineStyle": "dotted",
                "lineWidth": 1,
                "zone": True,
                "zone_top": ob["ob_high"],
                "zone_bottom": ob["ob_low"],
                "description": f"M5 Demand Order Block — Bearish candle before ${ob['impulse']:.1f} bullish impulse. Institutional buy orders expected here.",
                "session": "order_block"
            })

    if supply_obs:
        best_supply_ob = sorted(supply_obs, key=lambda ob: ob["price"] - current_price)[:2]
        for ob in best_supply_ob:
            levels.append({
                "price": ob["price"],
                "type": "supply_ob",
                "label": f"Supply OB {ob['ob_low']:.2f}–{ob['ob_high']:.2f}",
                "short_label": f"Supply OB",
                "color": "#f87171",
                "lineStyle": "dotted",
                "lineWidth": 1,
                "zone": True,
                "zone_top": ob["ob_high"],
                "zone_bottom": ob["ob_low"],
                "description": f"M5 Supply Order Block — Bullish candle before ${ob['impulse']:.1f} bearish impulse. Institutional sell orders expected here.",
                "session": "order_block"
            })

    # ── 6. Market Bias Summary ────────────────────────────────────────────────
    demand_levels = [l for l in levels if l["type"] in ("demand", "demand_ob")]
    supply_levels = [l for l in levels if l["type"] in ("supply", "supply_ob")]

    # Determine structural bias: price above London High flip = bullish; below London Low flip = bearish
    bias = "NEUTRAL"
    bias_reason = "Price inside session range — no clear directional breakout yet"
    if london_high and current_price > london_high:
        bias = "BULLISH"
        bias_reason = f"Price ({current_price:.2f}) above London High ({london_high:.2f}) — Bullish structure. Expect demand at flip zones below."
    elif london_low and current_price < london_low:
        bias = "BEARISH"
        bias_reason = f"Price ({current_price:.2f}) below London Low ({london_low:.2f}) — Bearish structure. Expect supply at flip zones above."

    # Sort levels by price descending for readability
    levels.sort(key=lambda l: l["price"], reverse=True)

    return {
        "status": "success",
        "reference_date": today_date.strftime("%Y-%m-%d"),
        "latest_bar_thai": latest_thai.strftime("%Y-%m-%d %H:%M"),
        "current_price": round(current_price, 2),
        "market_bias": bias,
        "bias_reason": bias_reason,
        "levels": levels,
        "summary": {
            "total_levels": len(levels),
            "demand_zones": len(demand_levels),
            "supply_zones": len(supply_levels),
            "london_high": london_high,
            "london_low": london_low,
            "asian_high": asian_high,
            "asian_low": asian_low,
        }
    }


@app.route("/api/order_flow_levels", methods=["GET"])
def api_order_flow_levels():
    res = compute_order_flow_levels_dict()
    if res.get("status") != "success":
        status_code = 500 if "No valid" in res.get("message", "") else 404
        return jsonify(res), status_code
    return jsonify(res)


if __name__ == "__main__":

    # Initial run on startup
    threading.Thread(target=run_fetch_and_analysis_cycle, daemon=True).start()
    print("\n" + "=" * 65)
    print("AI GOLD SCALPER -- WEB DASHBOARD SERVER")
    print(f"   Active Symbol:   {current_symbol}")
    print("   Open in Browser: http://127.0.0.1:5000")
    print(f"   Staging Folder:  {DEFAULT_STAGING_DIR}")
    print("=" * 65 + "\n")
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)
