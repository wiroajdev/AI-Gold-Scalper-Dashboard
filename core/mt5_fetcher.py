"""
MT5 Direct Data Fetcher for AI Gold Scalper Web Dashboard
Connects to MetaTrader 5, fetches latest multi-timeframe price bars (pos=1, closed bars only),
calculates broker server timezone via live tick time (not bar time), and writes CSV files into:
C:\\web-apps\\AI-Gold-Dashboard\\exportedpricedata\\
"""

import os
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Tuple, Optional
import MetaTrader5 as mt5
import pandas as pd


# Timeframe mapping to MT5 constant and bars-per-day multiplier
TIMEFRAME_SPECS = {
    "D1":  {"tf": mt5.TIMEFRAME_D1,  "days": 90.0, "bars_per_day": 1,    "min_bars": 90},
    "H4":  {"tf": mt5.TIMEFRAME_H4,  "days": 35.0, "bars_per_day": 6,    "min_bars": 210},
    "H1":  {"tf": mt5.TIMEFRAME_H1,  "days": 14.0, "bars_per_day": 24,   "min_bars": 336},
    "M15": {"tf": mt5.TIMEFRAME_M15, "days": 7.0,  "bars_per_day": 96,   "min_bars": 672},
    "M5":  {"tf": mt5.TIMEFRAME_M5,  "days": 4.0,  "bars_per_day": 288,  "min_bars": 1152},
    "M1":  {"tf": mt5.TIMEFRAME_M1,  "days": 1.5,  "bars_per_day": 1440, "min_bars": 2160},
}

# Dynamic staging directory relative to this project folder
APP_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STAGING_DIR = APP_ROOT / "exportedpricedata"


def find_gold_symbol() -> Optional[str]:
    """Finds the active gold symbol in the connected MT5 terminal."""
    all_symbols = mt5.symbols_get()
    if not all_symbols:
        return None

    names = [s.name for s in all_symbols]
    candidates = ["XAUUSD.iux", "XAUUSD", "GOLD", "XAUUSDm", "XAUUSD.a", "XAUUSD.ecn"]
    for c in candidates:
        if c in names:
            return c

    for name in names:
        if "XAUUSD" in name.upper() or "GOLD" in name.upper():
            return name

    return None


def get_available_gold_symbols() -> list:
    """Returns all gold-related symbols in MT5 Market Watch."""
    all_symbols = mt5.symbols_get()
    if not all_symbols:
        return []
    return [s.name for s in all_symbols if "XAU" in s.name.upper() or "GOLD" in s.name.upper()]


def calculate_timezone_from_tick(symbol: str) -> Tuple[str, int, int]:
    """
    Calculates broker timezone using the CURRENT LIVE TICK time vs system UTC.

    Why tick instead of bar time:
    - Bar time (e.g. D1 at 00:00) can be 12+ hours from now_utc → wildly wrong offset.
    - Tick time = broker server clock RIGHT NOW → offset is always accurate to the minute.

    MT5 stores both tick.time and bar time as Unix epochs where the broker treats
    its LOCAL clock time as if it were UTC (i.e., epoch = calendar.timegm(broker_local_timetuple)).
    So: datetime.utcfromtimestamp(tick.time) == broker_local_now (naive).

    Returns (broker_tz_str, broker_offset_hours, diff_to_thai_hours).
    """
    try:
        tick = mt5.symbol_info_tick(symbol)
        if tick is None or tick.time == 0:
            raise ValueError("No tick data returned from MT5")

        # broker_now: reconstruct broker local time from tick epoch
        broker_now = datetime.utcfromtimestamp(tick.time)          # naive broker local time
        now_utc    = datetime.now(timezone.utc).replace(tzinfo=None)  # naive true UTC

        broker_offset = round((broker_now - now_utc).total_seconds() / 3600)

        local_now    = datetime.now()                              # system local time (Thai UTC+7)
        local_offset = round((local_now - now_utc).total_seconds() / 3600)

        diff_to_thai = local_offset - broker_offset
        sign = "+" if broker_offset >= 0 else ""
        broker_tz_str = f"UTC{sign}{broker_offset}"

        print(f"[TZ] Broker: {broker_tz_str}  |  broker_now={broker_now.strftime('%H:%M:%S')}  "
              f"now_utc={now_utc.strftime('%H:%M:%S')}  diff_to_thai=+{diff_to_thai}h")

        return broker_tz_str, broker_offset, diff_to_thai
    except Exception as e:
        print(f"[TZ] Error calculating timezone from tick: {e} — using fallback UTC+1")
        return "UTC+1", 1, 6


def fetch_and_stage_mt5_data(
    target_symbol: Optional[str] = None,
    staging_dir: Path = DEFAULT_STAGING_DIR,
    primary_tf: str = "M5"
) -> Dict[str, Any]:
    """
    Connects to running MT5 Terminal, pulls historical bars using copy_rates_from_pos(pos=1)
    to get only CLOSED bars (pos=0 = live forming bar whose OHLC is still changing).
    Timezone is calculated ONCE from live tick time before the loop — avoids wrong offset
    when using historical bar time of D1/H4 bars which are many hours from now.
    """
    # Ensure staging directory exists
    staging_dir.mkdir(parents=True, exist_ok=True)

    if not mt5.initialize():
        err_code, err_msg = mt5.last_error()
        return {
            "status": "error",
            "message": f"Cannot initialize MetaTrader 5: {err_msg} (code {err_code}). Make sure MT5 is open and logged in."
        }

    try:
        available_syms = get_available_gold_symbols()

        if target_symbol and target_symbol.strip():
            symbol = target_symbol.strip()
            s_info = mt5.symbol_info(symbol)
            if s_info is None:
                hint = f" Available symbols: {', '.join(available_syms)}" if available_syms else ""
                return {
                    "status": "error",
                    "message": f"Symbol '{symbol}' not found in MetaTrader 5.{hint}"
                }
        else:
            symbol = find_gold_symbol()
            if not symbol:
                return {
                    "status": "error",
                    "message": "Gold symbol (XAUUSD / GOLD) not found in MT5 Market Watch."
                }

        # Select symbol in Market Watch
        mt5.symbol_select(symbol, True)

        timeframe_results = {}
        latest_bar_time_str = "N/A"
        latest_thai_time_str = "N/A"
        latest_price = 0.0

        # ── Timezone: calculate ONCE from live tick, not from historical bar time ──
        # Using bar time caused wrong offset for D1/H4 (bar at 00:00 vs now = -12h offset).
        # Tick time = broker server clock right now → always accurate.
        broker_tz, broker_offset, diff_thai = calculate_timezone_from_tick(symbol)

        for tf_name, spec in TIMEFRAME_SPECS.items():
            mt5_tf = spec["tf"]
            bars_to_fetch = spec["min_bars"]

            # pos=1 → skip index-0 (live/forming bar whose OHLC still changes).
            # pos=1 → index-1 = the last COMPLETED/closed bar → price data is final.
            rates = mt5.copy_rates_from_pos(symbol, mt5_tf, 1, bars_to_fetch)
            if rates is None or len(rates) == 0:
                print(f"[Warning] Failed to fetch rates for {tf_name}")
                continue

            # Convert bar timestamps
            times_utc = [datetime.fromtimestamp(r["time"], timezone.utc).replace(tzinfo=None) for r in rates]
            times_str = [t.strftime("%Y.%m.%d %H:%M" if tf_name != "D1" else "%Y.%m.%d") for t in times_utc]

            df_export = pd.DataFrame({
                "Time": times_str,
                "Open": [round(float(r["open"]), 2) for r in rates],
                "High": [round(float(r["high"]), 2) for r in rates],
                "Low": [round(float(r["low"]), 2) for r in rates],
                "Close": [round(float(r["close"]), 2) for r in rates],
                "TickVolume": [int(r["tick_volume"]) for r in rates]
            })

            # Save fixed overwritten file
            clean_sym = "XAUUSD"
            csv_path = staging_dir / f"{clean_sym}_{tf_name}.csv"

            with open(csv_path, "w", encoding="utf-8") as f:
                f.write(f"# Symbol,{symbol},Timeframe,{tf_name},Timezone,{broker_tz}\n")
                df_export.to_csv(f, index=False)

            # Auto-mirror to C:\web-apps staging dir if it exists and is distinct
            mirror_dir = Path("C:/web-apps/AI-Gold-Scalper-Dashboard/exportedpricedata")
            if mirror_dir.exists() and mirror_dir.resolve() != staging_dir.resolve():
                try:
                    import shutil
                    shutil.copy2(csv_path, mirror_dir / csv_path.name)
                except Exception:
                    pass

            last_row = df_export.iloc[-1]
            last_broker_time = str(last_row["Time"])
            
            # Calculate corresponding Thai local time
            last_bar_dt = times_utc[-1]
            thai_dt = last_bar_dt + timedelta(hours=diff_thai)
            last_thai_time = thai_dt.strftime("%Y.%m.%d %H:%M" if tf_name != "D1" else "%Y.%m.%d")

            # Calculate candle close time (open time + timeframe duration)
            tf_minutes = 5
            if tf_name == "M1": tf_minutes = 1
            elif tf_name == "M5": tf_minutes = 5
            elif tf_name == "M15": tf_minutes = 15
            elif tf_name == "H1": tf_minutes = 60
            elif tf_name == "H4": tf_minutes = 240
            elif tf_name == "D1": tf_minutes = 1440

            close_broker_dt = last_bar_dt + timedelta(minutes=tf_minutes)
            close_thai_dt = thai_dt + timedelta(minutes=tf_minutes)
            close_broker_time = close_broker_dt.strftime("%Y.%m.%d %H:%M" if tf_name != "D1" else "%Y.%m.%d")
            close_thai_time = close_thai_dt.strftime("%Y.%m.%d %H:%M" if tf_name != "D1" else "%Y.%m.%d")

            timeframe_results[tf_name] = {
                "file": csv_path.name,
                "bars": len(df_export),
                "broker_time": last_broker_time,
                "close_broker_time": close_broker_time,
                "thai_time": last_thai_time,
                "close_thai_time": close_thai_time,
                "latest_close": float(last_row["Close"])
            }

        # Select base execution timeframe bar
        chosen_tf = primary_tf if primary_tf in timeframe_results else ("M5" if "M5" in timeframe_results else list(timeframe_results.keys())[0])

        # Use M5 bar for display time and latest price (close time & close price of M5 candle)
        display_tf = "M5" if "M5" in timeframe_results else chosen_tf
        latest_bar_time_str = timeframe_results[display_tf].get("close_broker_time", timeframe_results[display_tf]["broker_time"])
        latest_thai_time_str = timeframe_results[display_tf].get("close_thai_time", timeframe_results[display_tf]["thai_time"])

        # Latest price uses M5 candle close price
        if "M5" in timeframe_results:
            latest_price = timeframe_results["M5"]["latest_close"]
        else:
            latest_price = timeframe_results[chosen_tf]["latest_close"]

        display_time_str = f"{latest_bar_time_str} ({broker_tz}) | {latest_thai_time_str} (Thai)"

        return {
            "status": "success",
            "symbol": symbol,
            "broker_timezone": broker_tz,
            "available_symbols": available_syms,
            "staging_dir": str(staging_dir),
            "latest_bar_time": display_time_str,
            "latest_broker_time": latest_bar_time_str,
            "latest_thai_time": latest_thai_time_str,
            "latest_price": latest_price,
            "timeframes": timeframe_results,
            "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

    finally:
        mt5.shutdown()


if __name__ == "__main__":
    res = fetch_and_stage_mt5_data()
    print("Fetch result:")
    print("  Symbol:", res.get("symbol"))
    print("  Broker TZ:", res.get("broker_timezone"))
    print("  Latest Bar Time:", res.get("latest_bar_time"))
    print("  Staging Dir:", res.get("staging_dir"))
    for tf, d in res.get("timeframes", {}).items():
        print(f"  {tf}: {d['bars']} bars, Broker: {d['broker_time']}, Thai: {d['thai_time']}")
