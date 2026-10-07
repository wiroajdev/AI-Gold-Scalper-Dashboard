"""
AI Engine for Web Dashboard — Price Action & Multi-Timeframe Radar (v3.0)
Specialized for XAU/USD Day Trading:
- Kaufman Efficiency Ratio (KER) for Chop vs. Trend detection
- Anti-Falling-Knife / Anti-Rising-Knife Interceptors
- DirectionalBiasEngine: outputs Bullish/Bearish/Neutral bias with Edge Score (0-100)
- Multi-Timeframe Alignment (H1, M15, M5, M1)
- 9+ Ensemble ML voting logic removed per user specification.
"""

import warnings
warnings.filterwarnings("ignore")
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, Union, List
import numpy as np
import pandas as pd


# ─────────────────────────────────────────────────────────────────────────────
# MARKET REGIME DETECTOR (with KER integrated)
# ─────────────────────────────────────────────────────────────────────────────

class MarketRegimeDetector:
    @staticmethod
    def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        high = df["High"]
        low = df["Low"]
        close = df["Close"]
        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.rolling(window=period).mean()

    @staticmethod
    def calculate_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
        high = df["High"]
        low = df["Low"]
        close = df["Close"]

        plus_dm = high.diff()
        minus_dm = -low.diff()
        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm < 0] = 0

        mask_p = plus_dm > minus_dm
        plus_dm[~mask_p] = 0
        minus_dm[mask_p] = 0

        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(period).mean().replace(0, 1e-6)

        plus_di = 100 * (plus_dm.rolling(period).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(period).mean() / atr)
        dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1e-6))
        adx = dx.rolling(period).mean()
        return adx.fillna(20.0)

    @staticmethod
    def calculate_ker(closes: pd.Series, period: int = 20) -> float:
        """
        Kaufman Efficiency Ratio (KER / ER).
        Measures how directionally efficient price movement is.
        KER = |NetMove(n)| / SumAbsoluteChanges(n)
        - KER > 0.60 → TRENDING  (price moves like a straight line)
        - KER 0.30–0.60 → DRIFTING (mixed, moderate)
        - KER < 0.30 → CHOPPY   (price moves like random walk)
        """
        if len(closes) < period + 1:
            return 0.5
        net_move = abs(float(closes.iloc[-1]) - float(closes.iloc[-period - 1]))
        path_sum = float(closes.diff().abs().iloc[-period:].sum())
        if path_sum < 1e-6:
            return 0.5
        return round(min(1.0, net_move / path_sum), 4)

    def detect(self, df: pd.DataFrame, tf_name: str = "M5") -> Dict[str, Any]:
        if df.empty or len(df) < 25:
            return {
                "regime": "RANGING",
                "trend_bias": "NEUTRAL",
                "volatility_status": "NORMAL",
                "volatility_score": 50.0,
                "trend_strength": 20.0,
                "adx": 20.0,
                "atr": 2.0,
                "atr_ratio": 1.0,
                "risk_multiplier": 1.0,
                "recommended_tp_pts": 150,
                "recommended_sl_pts": 100,
                "current_price": float(df["Close"].iloc[-1]) if not df.empty else 0.0,
                "ker": 0.5,
                "ker_label": "DRIFTING"
            }

        closes = df["Close"]
        current_price = closes.iloc[-1]

        ema20 = closes.ewm(span=20, adjust=False).mean()
        ema50 = closes.ewm(span=min(50, len(closes)), adjust=False).mean()

        sma20 = closes.rolling(20).mean()
        std20 = closes.rolling(20).std()
        upper_bb = sma20 + 2.0 * std20
        lower_bb = sma20 - 2.0 * std20
        bb_width = ((upper_bb - lower_bb) / sma20) * 100

        atr = self.calculate_atr(df, period=14)
        current_atr = float(atr.iloc[-1]) if not np.isnan(atr.iloc[-1]) else 2.0
        avg_atr = float(atr.rolling(30).mean().iloc[-1]) if len(atr) >= 30 and not np.isnan(atr.rolling(30).mean().iloc[-1]) else current_atr
        atr_ratio = current_atr / max(avg_atr, 0.01)

        adx_series = self.calculate_adx(df, period=14)
        adx = float(adx_series.iloc[-1])

        ema20_now = ema20.iloc[-1]
        ema20_prev5 = ema20.iloc[-6] if len(ema20) >= 6 else ema20.iloc[0]
        ema_slope = (ema20_now - ema20_prev5) / max(current_price * 0.001, 1e-4)

        # KER: use period=20 for day trading resolution
        ker = self.calculate_ker(closes, period=20)
        if ker >= 0.60:
            ker_label = "TRENDING"
        elif ker >= 0.30:
            ker_label = "DRIFTING"
        else:
            ker_label = "CHOPPY"

        if atr_ratio >= 1.7:
            vol_status = "EXTREME_VOLATILITY"
            vol_score = 90.0
        elif atr_ratio >= 1.3:
            vol_status = "HIGH_VOLATILITY"
            vol_score = 75.0
        elif atr_ratio <= 0.7:
            vol_status = "LOW_VOLATILITY"
            vol_score = 30.0
        else:
            vol_status = "NORMAL"
            vol_score = 50.0

        if vol_status in ["EXTREME_VOLATILITY", "HIGH_VOLATILITY"] and bb_width.iloc[-1] > bb_width.rolling(min(30, len(bb_width))).mean().iloc[-1] * 1.5:
            regime = "HIGH_VOLATILITY"
            trend_bias = "BULLISH" if closes.iloc[-1] > ema20_now else "BEARISH"
            trend_strength = min(100.0, max(40.0, adx * 1.5))
            risk_mult = 0.5
            rec_tp = int(max(200, current_atr * 2.5 * 10))
            rec_sl = int(max(150, current_atr * 1.8 * 10))
        elif adx >= 25 and ema20_now > ema50.iloc[-1] and ema_slope > 0.05:
            regime = "TRENDING_UP"
            trend_bias = "STRONG_BULLISH" if adx >= 35 else "BULLISH"
            trend_strength = min(100.0, adx * 1.8)
            risk_mult = 1.0
            rec_tp = 300
            rec_sl = 120
        elif adx >= 25 and ema20_now < ema50.iloc[-1] and ema_slope < -0.05:
            regime = "TRENDING_DOWN"
            trend_bias = "STRONG_BEARISH" if adx >= 35 else "BEARISH"
            trend_strength = min(100.0, adx * 1.8)
            risk_mult = 1.0
            rec_tp = 300
            rec_sl = 120
        else:
            regime = "RANGING"
            trend_bias = "NEUTRAL"
            trend_strength = max(10.0, adx)
            risk_mult = 0.8
            rec_tp = 120
            rec_sl = 80

        return {
            "timeframe": tf_name,
            "regime": regime,
            "trend_bias": trend_bias,
            "volatility_status": vol_status,
            "volatility_score": round(vol_score, 1),
            "trend_strength": round(trend_strength, 1),
            "adx": round(adx, 2),
            "atr": round(current_atr, 2),
            "atr_ratio": round(atr_ratio, 2),
            "risk_multiplier": risk_mult,
            "recommended_tp_pts": rec_tp,
            "recommended_sl_pts": rec_sl,
            "current_price": round(current_price, 2),
            "ker": ker,
            "ker_label": ker_label
        }


# ─────────────────────────────────────────────────────────────────────────────
# ENSEMBLE ENGINE (DEPRECATED STUB)
# ─────────────────────────────────────────────────────────────────────────────

class EnsembleEngine:
    """Legacy placeholder: Ensemble ML models removed per user specification."""
    def __init__(self):
        self.model_names = []

    def predict(self, df: pd.DataFrame, regime_info: Dict[str, Any]) -> Dict[str, Any]:
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# DIRECTIONAL BIAS ENGINE — Price Action Sniper Radar
# ─────────────────────────────────────────────────────────────────────────────

class DirectionalBiasEngine:
    """
    Aggregates MTF regime alignment, KER scores, and ADX momentum
    to produce a single Directional Bias (BULLISH / BEARISH / NEUTRAL)
    and an Edge Score (0–100) for Price Action day trading.

    Scoring Breakdown (total 100 pts):
    - MTF Alignment (H1+M15+M5+M1):  50 pts  — macro + entry alignment
    - KER (H1+M15 averaged):          35 pts  — chop vs. trend quality
    - ADX Trend Power (exec TF):      15 pts  — directional momentum
    """

    MTF_WATCH = ["H1", "M15", "M5", "M1"]   # day trading Timeframes

    @staticmethod
    def _check_falling_knife(df: pd.DataFrame, atr: float) -> bool:
        """
        Anti-Falling-Knife Interceptor.
        Returns True if the latest candle shows aggressive bearish momentum
        that should BLOCK a BUY signal (catching a falling knife).
        """
        if df is None or len(df) < 5:
            return False
        last = df.iloc[-1]
        candle_range = float(last["High"] - last["Low"])
        if candle_range < 1e-4:
            return False
        body_ratio = float(last["Close"] - last["Open"]) / candle_range
        mom_3bar = float(last["Close"] - df["Close"].iloc[-4]) / max(atr, 0.01)
        return body_ratio < -0.65 and mom_3bar < -1.5

    @staticmethod
    def _check_rising_knife(df: pd.DataFrame, atr: float) -> bool:
        """
        Anti-Rising-Knife Interceptor (mirror of falling knife for SELL).
        Blocks SELL when price just spiked up aggressively (potential fakeout).
        """
        if df is None or len(df) < 5:
            return False
        last = df.iloc[-1]
        candle_range = float(last["High"] - last["Low"])
        if candle_range < 1e-4:
            return False
        body_ratio = float(last["Close"] - last["Open"]) / candle_range
        mom_3bar = float(last["Close"] - df["Close"].iloc[-4]) / max(atr, 0.01)
        return body_ratio > 0.65 and mom_3bar > 1.5

    def compute(
        self,
        mtf_regimes: Dict[str, Dict[str, Any]],
        exec_regime: Dict[str, Any],
        data_store: Dict[str, pd.DataFrame],
        exec_tf: str = "M5",
        **kwargs
    ) -> Dict[str, Any]:

        # ── 1. MTF Alignment Score (50 pts) ──
        regimes_present = {
            tf: mtf_regimes[tf]["regime"]
            for tf in self.MTF_WATCH if tf in mtf_regimes
        }
        up_count = sum(1 for r in regimes_present.values() if r == "TRENDING_UP")
        down_count = sum(1 for r in regimes_present.values() if r == "TRENDING_DOWN")
        total_watch = len(self.MTF_WATCH)

        if up_count == total_watch:
            mtf_dir = "BULLISH"
            mtf_score = 50
        elif down_count == total_watch:
            mtf_dir = "BEARISH"
            mtf_score = 50
        elif up_count >= 3 and up_count > down_count:
            mtf_dir = "BULLISH"
            mtf_score = 35
        elif down_count >= 3 and down_count > up_count:
            mtf_dir = "BEARISH"
            mtf_score = 35
        elif up_count >= 2 and up_count > down_count:
            mtf_dir = "BULLISH"
            mtf_score = 18
        elif down_count >= 2 and down_count > up_count:
            mtf_dir = "BEARISH"
            mtf_score = 18
        else:
            mtf_dir = "NEUTRAL"
            mtf_score = 0

        # ── 2. KER Score (35 pts) — average H1 & M15 for day trading ──
        ker_detector = MarketRegimeDetector()
        ker_values = []
        for tf in ["H1", "M15"]:  # day trading reference TFs
            if tf in data_store and len(data_store[tf]) >= 22:
                ker = ker_detector.calculate_ker(data_store[tf]["Close"], period=20)
                ker_values.append(ker)
        avg_ker = round(sum(ker_values) / len(ker_values), 4) if ker_values else 0.5

        if avg_ker >= 0.60:
            ker_label = "TRENDING"
            ker_score = 35
        elif avg_ker >= 0.45:
            ker_label = "DRIFTING"
            ker_score = 20
        elif avg_ker >= 0.30:
            ker_label = "WEAK DRIFT"
            ker_score = 10
        else:
            ker_label = "CHOPPY"
            ker_score = 0

        # ── 3. ADX Score (15 pts) ──
        adx = exec_regime.get("adx", 20.0)
        if adx >= 35:
            adx_score = 15
        elif adx >= 25:
            adx_score = 10
        elif adx >= 20:
            adx_score = 5
        else:
            adx_score = 0

        # ── Final Edge Score (0–100) ──
        edge_score = min(100, mtf_score + ker_score + adx_score)

        # ── Falling-knife / Rising-knife checks ──
        check_df = data_store.get(exec_tf, data_store.get("M5"))
        current_atr = exec_regime.get("atr", 2.0)
        falling_knife_active = self._check_falling_knife(check_df, current_atr)
        rising_knife_active = self._check_rising_knife(check_df, current_atr)

        # ── Determine Final Directional Bias ──
        if falling_knife_active:
            final_bias = "BEARISH" if mtf_dir == "BEARISH" else "NEUTRAL"
            bias_detail = "⚠️ FALLING KNIFE DETECTED — Aggressive bearish momentum, wait for rejection candle before entry"
        elif rising_knife_active:
            final_bias = "BULLISH" if mtf_dir == "BULLISH" else "NEUTRAL"
            bias_detail = "⚠️ RISING KNIFE DETECTED — Aggressive bullish spike, wait for price stabilization"
        elif edge_score >= 60 and mtf_dir == "BULLISH":
            final_bias = "BULLISH"
            bias_detail = "High-probability bullish environment — look for BUY setups on M1/M5 pullbacks"
        elif edge_score >= 60 and mtf_dir == "BEARISH":
            final_bias = "BEARISH"
            bias_detail = "High-probability bearish environment — look for SELL setups on M1/M5 bounces"
        elif edge_score >= 35 and mtf_dir != "NEUTRAL":
            final_bias = mtf_dir
            bias_detail = f"Moderate {mtf_dir.lower()} lean — selective setups only, reduce size"
        else:
            final_bias = "NEUTRAL"
            bias_detail = "Market is choppy or TF-misaligned — NO TRADE ZONE, wait for alignment"

        # ── MTF breakdown for UI display ──
        mtf_breakdown = {
            tf: regimes_present.get(tf, "N/A")
            for tf in self.MTF_WATCH
        }

        return {
            "directional_bias": final_bias,
            "bias_detail": bias_detail,
            "edge_score": edge_score,
            "edge_label": "HIGH EDGE" if edge_score >= 70 else ("MODERATE" if edge_score >= 45 else "LOW / CHOPPY"),
            "ker_score": avg_ker,
            "ker_label": ker_label,
            "mtf_alignment_score": mtf_score,
            "mtf_alignment_count": f"{max(up_count, down_count)}/{total_watch}",
            "mtf_alignment_direction": mtf_dir,
            "mtf_breakdown": mtf_breakdown,
            "ai_consensus_score": 0,
            "adx_score": adx_score,
            "falling_knife_active": falling_knife_active,
        }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN ANALYSIS ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_STAGING_DIR = Path(__file__).resolve().parent.parent / "exportedpricedata"

def _load_staged_csvs(staging_dir: Union[Path, str] = DEFAULT_STAGING_DIR) -> Dict[str, pd.DataFrame]:
    """Load all staged CSVs from disk into a dict. Public helper for setup_detector."""
    staging_dir = Path(staging_dir)
    if not staging_dir.exists():
        fallback = Path(__file__).resolve().parent.parent / "exportedpricedata"
        if fallback.exists():
            staging_dir = fallback
    timeframes = ["D1", "H4", "H1", "M15", "M5", "M1"]
    store: Dict[str, pd.DataFrame] = {}
    for tf in timeframes:
        csv_file = staging_dir / f"XAUUSD_{tf}.csv"
        if csv_file.exists():
            try:
                df = pd.read_csv(csv_file, comment="#", skipinitialspace=True)
                df.columns = [c.strip().title() for c in df.columns]
                if "Tickvolume" in df.columns and "TickVolume" not in df.columns:
                    df["TickVolume"] = df["Tickvolume"]
                if not df.empty and len(df) >= 10:
                    store[tf] = df
            except Exception as e:
                print(f"Error loading {csv_file}: {e}")
    return store


def analyze_staged_data(staging_dir: Union[Path, str] = DEFAULT_STAGING_DIR, primary_tf: str = "M5") -> Dict[str, Any]:
    """Loads staged CSVs and runs regime detection, Price Action & MTF directional bias."""
    staging_dir = Path(staging_dir)
    if not staging_dir.exists():
        fallback = Path(__file__).resolve().parent.parent / "exportedpricedata"
        if fallback.exists():
            staging_dir = fallback

    data_store = _load_staged_csvs(staging_dir)

    if not data_store:
        return {"status": "error", "message": "No price data files found in staging folder."}

    regime_detector = MarketRegimeDetector()
    mtf_regimes = {}
    for tf, df in data_store.items():
        mtf_regimes[tf] = regime_detector.detect(df, tf_name=tf)

    exec_tf = primary_tf if primary_tf in data_store else list(data_store.keys())[0]
    exec_df = data_store[exec_tf]
    exec_regime = mtf_regimes[exec_tf]

    # Directional Bias (Price Action Sniper Radar)
    bias_engine = DirectionalBiasEngine()
    directional_bias = bias_engine.compute(
        mtf_regimes=mtf_regimes,
        exec_regime=exec_regime,
        data_store=data_store,
        exec_tf=exec_tf
    )

    # Use M5 last bar for display and closing price
    display_tf = "M5" if "M5" in data_store else exec_tf
    time_df = data_store.get(display_tf, exec_df)
    latest_row = time_df.iloc[-1]
    raw_time = str(latest_row["Time"]) if "Time" in latest_row else "N/A"

    current_price = float(time_df["Close"].iloc[-1])

    # Broker timezone
    broker_tz = "UTC+1"
    exec_csv = staging_dir / f"XAUUSD_{exec_tf}.csv"
    if exec_csv.exists():
        try:
            with open(exec_csv, "r", encoding="utf-8") as f:
                header = f.readline()
                if "Timezone," in header:
                    parts = header.strip().split(",")
                    for idx, p in enumerate(parts):
                        if p == "Timezone" and idx + 1 < len(parts):
                            broker_tz = parts[idx + 1].strip()
        except Exception:
            pass

    display_bar_time = raw_time
    try:
        dt = datetime.strptime(raw_time, "%Y.%m.%d %H:%M")
        # Add 5 minutes to get M5 candle close time
        dt_close = dt + timedelta(minutes=5)
        offset = 1
        if "UTC+" in broker_tz:
            offset = int(broker_tz.replace("UTC+", ""))
        elif "UTC-" in broker_tz:
            offset = -int(broker_tz.replace("UTC-", ""))
        thai_dt = dt_close + timedelta(hours=(7 - offset))
        close_time_str = dt_close.strftime("%Y.%m.%d %H:%M")
        display_bar_time = f"{close_time_str} ({broker_tz}) | {thai_dt.strftime('%Y.%m.%d %H:%M')} (Thai)"
    except Exception:
        pass

    return {
        "status": "success",
        "symbol": "XAUUSD",
        "latest_bar_time": display_bar_time,
        "current_price": round(current_price, 2),
        "latest_price": round(current_price, 2),
        "execution_timeframe": exec_tf,
        "regime": exec_regime,
        "ensemble": {},
        "directional_bias": directional_bias,
        "_mtf_regimes": mtf_regimes,   # internal: used by setup_detector
        "multi_timeframe": {
            tf: {
                "regime": mtf_regimes[tf]["regime"],
                "trend_bias": mtf_regimes[tf]["trend_bias"],
                "latest_close": round(float(data_store[tf]["Close"].iloc[-1]), 2)
                if tf in data_store else mtf_regimes[tf]["current_price"],
                "adx": mtf_regimes[tf]["adx"],
                "atr": mtf_regimes[tf]["atr"],
                "volatility_status": mtf_regimes[tf]["volatility_status"],
                "ker": mtf_regimes[tf].get("ker", 0.5),
                "ker_label": mtf_regimes[tf].get("ker_label", "DRIFTING")
            }
            for tf in ["D1", "H4", "H1", "M15", "M5", "M1"] if tf in mtf_regimes
        }
    }
