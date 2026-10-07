"""
AI Engine for Web Dashboard — Price Action Sniper Mode (v2.0)
Upgraded from micro-scalper (3-bar) to Day Trading Radar:
- forward_bars = 12 (60-min horizon on M5, aligns with 1-hour session)
- Kaufman Efficiency Ratio (KER) for Chop vs. Trend detection
- Anti-Falling-Knife Interceptor (prevents BUY on bearish momentum candles)
- DirectionalBiasEngine: outputs Bullish/Bearish/Neutral bias with Edge Score
"""

import warnings
warnings.filterwarnings("ignore")
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, Union, List
import numpy as np
import pandas as pd

from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier, ExtraTreesClassifier
from sklearn.neighbors import KNeighborsClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.neural_network import MLPClassifier
from sklearn.svm import SVC
from sklearn.preprocessing import StandardScaler


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
# ENSEMBLE ENGINE (forward_bars=12, Anti-Falling-Knife Interceptor)
# ─────────────────────────────────────────────────────────────────────────────

class EnsembleEngine:
    def __init__(self):
        self.scaler = StandardScaler()
        self.model_names = [
            "Random Forest",
            "Gradient Boosting",
            "Extra Trees",
            "Support Vector Classifier (SVC)",
            "K-Nearest Neighbors (KNN)",
            "Logistic Regression",
            "Neural Network (MLP)",
            "Gold Trend-Following Engine",
            "Gold Mean-Reversion Engine"
        ]

    @staticmethod
    def extract_features(df: pd.DataFrame) -> pd.DataFrame:
        data = df.copy()
        c = data["Close"]
        h = data["High"]
        l = data["Low"]
        o = data["Open"]
        v = data["TickVolume"] if "TickVolume" in data.columns else (data["Volume"] if "Volume" in data.columns else pd.Series(1, index=data.index))

        def get_rsi(series, period):
            delta = series.diff()
            gain = (delta.where(delta > 0, 0)).rolling(period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
            rs = gain / loss.replace(0, 1e-6)
            return 100 - (100 / (1 + rs))

        data["rsi_14"] = get_rsi(c, 14)
        data["rsi_7"] = get_rsi(c, 7)

        ema12 = c.ewm(span=12, adjust=False).mean()
        ema26 = c.ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        data["macd_diff"] = macd - signal

        sma20 = c.rolling(20).mean()
        std20 = c.rolling(20).std()
        upper = sma20 + 2.0 * std20
        lower = sma20 - 2.0 * std20
        data["bb_pos"] = (c - lower) / (upper - lower).replace(0, 1e-6)

        lowest14 = l.rolling(14).min()
        highest14 = h.rolling(14).max()
        data["stoch_k"] = 100 * (c - lowest14) / (highest14 - lowest14).replace(0, 1e-6)

        tr = pd.concat([h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)
        atr14 = tr.rolling(14).mean().replace(0, 1e-6)
        data["atr14"] = atr14

        ema9 = c.ewm(span=9, adjust=False).mean()
        ema21 = c.ewm(span=21, adjust=False).mean()
        data["ema_diff_atr"] = (ema9 - ema21) / atr14

        data["candle_body"] = (c - o) / (h - l + 1e-4)
        data["upper_shadow"] = (h - np.maximum(c, o)) / (h - l + 1e-4)
        data["lower_shadow"] = (np.minimum(c, o) - l) / (h - l + 1e-4)

        data["mom_3"] = (c - c.shift(3)) / atr14
        data["mom_5"] = (c - c.shift(5)) / atr14

        vol_avg = v.rolling(20).mean().replace(0, 1)
        data["vol_ratio"] = v / vol_avg

        feature_cols = [
            "rsi_14", "rsi_7", "macd_diff", "bb_pos", "stoch_k",
            "ema_diff_atr", "candle_body", "upper_shadow", "lower_shadow",
            "mom_3", "mom_5", "vol_ratio"
        ]
        return data[feature_cols].bfill().fillna(0)

    @staticmethod
    def create_labels(df: pd.DataFrame, forward_bars: int = 12) -> pd.Series:
        """
        Triple-Barrier inspired labeling:
        - Look 12 bars ahead (60 mins on M5) — day trading horizon
        - Threshold = 1.0 ATR (requires meaningful move, not just noise)
        - Label +1 (BUY) if price gains > 1.0 ATR within horizon
        - Label -1 (SELL) if price drops > 1.0 ATR within horizon
        - Label  0 (HOLD/CHOP) if price stays within ±1.0 ATR (no clear direction)
        """
        close = df["Close"]
        tr = pd.concat([
            df["High"] - df["Low"],
            (df["High"] - close.shift(1)).abs(),
            (df["Low"] - close.shift(1)).abs()
        ], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().fillna(1.5)

        future_ret = (close.shift(-forward_bars) - close)
        # Raised threshold from 0.6 ATR (scalper) to 1.0 ATR (day trader)
        threshold = atr * 1.0

        labels = pd.Series(0, index=df.index)
        labels[future_ret > threshold] = 1
        labels[future_ret < -threshold] = -1
        return labels

    @staticmethod
    def _check_falling_knife(df: pd.DataFrame, atr: float) -> bool:
        """
        Anti-Falling-Knife Interceptor.
        Returns True if the latest candle shows aggressive bearish momentum
        that should BLOCK a BUY signal (catching a falling knife).

        Conditions (both must be true):
        1. Latest candle body is strongly bearish (body < -65% of candle range)
        2. 3-bar momentum is strongly negative (< -1.5 ATR) — still in free-fall
        """
        if len(df) < 5:
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
        Conditions: Strongly bullish candle body + 3-bar mom > +1.5 ATR
        """
        if len(df) < 5:
            return False
        last = df.iloc[-1]
        candle_range = float(last["High"] - last["Low"])
        if candle_range < 1e-4:
            return False
        body_ratio = float(last["Close"] - last["Open"]) / candle_range
        mom_3bar = float(last["Close"] - df["Close"].iloc[-4]) / max(atr, 0.01)
        return body_ratio > 0.65 and mom_3bar > 1.5

    def predict(self, df: pd.DataFrame, regime_info: Dict[str, Any]) -> Dict[str, Any]:
        current_atr = regime_info.get("atr", 2.0)
        current_price = float(df["Close"].iloc[-1]) if not df.empty else 0.0

        if len(df) < 50:
            return {
                "action": "HOLD",
                "confidence": 0,
                "buy_votes": 0,
                "sell_votes": 0,
                "hold_votes": 9,
                "total_models": 9,
                "votes": {name: "HOLD" for name in self.model_names},
                "filter_reason": "Insufficient bars for ensemble inference",
                "falling_knife_warning": False,
                "entry_price": current_price,
                "sl_price": 0.0,
                "tp1_price": 0.0,
                "tp2_price": 0.0,
                "risk_reward_ratio": 0.0
            }

        features = self.extract_features(df)
        # Day trading horizon: 12 bars (60 min on M5)
        labels = self.create_labels(df, forward_bars=12)

        valid_idx = labels.iloc[:-13].index  # exclude last 12 unlabeled bars
        X_train = features.loc[valid_idx]
        y_train = labels.loc[valid_idx]
        X_latest = features.iloc[[-1]]

        X_train_scaled = self.scaler.fit_transform(X_train)
        X_latest_scaled = self.scaler.transform(X_latest)

        votes: Dict[str, str] = {}

        # 1. Random Forest
        rf = RandomForestClassifier(n_estimators=40, max_depth=5, random_state=42)
        rf.fit(X_train_scaled, y_train)
        pred_rf = int(rf.predict(X_latest_scaled)[0])
        votes["Random Forest"] = "BUY" if pred_rf == 1 else ("SELL" if pred_rf == -1 else "HOLD")

        # 2. Gradient Boosting
        gb = GradientBoostingClassifier(n_estimators=35, max_depth=3, random_state=42)
        gb.fit(X_train_scaled, y_train)
        pred_gb = int(gb.predict(X_latest_scaled)[0])
        votes["Gradient Boosting"] = "BUY" if pred_gb == 1 else ("SELL" if pred_gb == -1 else "HOLD")

        # 3. Extra Trees
        et = ExtraTreesClassifier(n_estimators=35, max_depth=5, random_state=42)
        et.fit(X_train_scaled, y_train)
        pred_et = int(et.predict(X_latest_scaled)[0])
        votes["Extra Trees"] = "BUY" if pred_et == 1 else ("SELL" if pred_et == -1 else "HOLD")

        # 4. SVC
        svc = SVC(kernel="rbf", C=1.0, random_state=42)
        svc.fit(X_train_scaled, y_train)
        pred_svc = int(svc.predict(X_latest_scaled)[0])
        votes["Support Vector Classifier (SVC)"] = "BUY" if pred_svc == 1 else ("SELL" if pred_svc == -1 else "HOLD")

        # 5. KNN
        knn = KNeighborsClassifier(n_neighbors=min(7, len(X_train)))
        knn.fit(X_train_scaled, y_train)
        pred_knn = int(knn.predict(X_latest_scaled)[0])
        votes["K-Nearest Neighbors (KNN)"] = "BUY" if pred_knn == 1 else ("SELL" if pred_knn == -1 else "HOLD")

        # 6. Logistic Regression
        lr = LogisticRegression(max_iter=300, random_state=42)
        lr.fit(X_train_scaled, y_train)
        pred_lr = int(lr.predict(X_latest_scaled)[0])
        votes["Logistic Regression"] = "BUY" if pred_lr == 1 else ("SELL" if pred_lr == -1 else "HOLD")

        # 7. MLP
        mlp = MLPClassifier(hidden_layer_sizes=(32, 16), max_iter=300, random_state=42)
        mlp.fit(X_train_scaled, y_train)
        pred_mlp = int(mlp.predict(X_latest_scaled)[0])
        votes["Neural Network (MLP)"] = "BUY" if pred_mlp == 1 else ("SELL" if pred_mlp == -1 else "HOLD")

        # 8. Gold Trend-Following Engine
        latest_feat = features.iloc[-1]
        trend_score = 0
        if latest_feat["ema_diff_atr"] > 0.15 and latest_feat["rsi_14"] > 52 and latest_feat["macd_diff"] > 0:
            trend_score = 1
        elif latest_feat["ema_diff_atr"] < -0.15 and latest_feat["rsi_14"] < 48 and latest_feat["macd_diff"] < 0:
            trend_score = -1
        votes["Gold Trend-Following Engine"] = "BUY" if trend_score == 1 else ("SELL" if trend_score == -1 else "HOLD")

        # 9. Gold Mean-Reversion Engine
        # NOTE: In day trading mode, mean-reversion signals are treated as HOLD
        # instead of BUY/SELL, to prevent catching falling/rising knives.
        # A "PULLBACK ZONE" note is embedded in the filter reason instead.
        revert_score = 0
        revert_note = ""
        if latest_feat["bb_pos"] < 0.12 and latest_feat["stoch_k"] < 20:
            revert_score = 0  # was 1 (BUY) — now suppressed as standalone signal
            revert_note = "Oversold zone detected — potential pullback support"
        elif latest_feat["bb_pos"] > 0.88 and latest_feat["stoch_k"] > 80:
            revert_score = 0  # was -1 (SELL) — now suppressed as standalone signal
            revert_note = "Overbought zone detected — potential pullback resistance"
        votes["Gold Mean-Reversion Engine"] = "HOLD"  # always HOLD in Sniper Mode

        buy_votes = sum(1 for v in votes.values() if v == "BUY")
        sell_votes = sum(1 for v in votes.values() if v == "SELL")
        hold_votes = sum(1 for v in votes.values() if v == "HOLD")
        total_models = len(votes)

        regime = regime_info.get("regime", "RANGING")

        # ── Anti-Falling-Knife & Anti-Rising-Knife Interceptors ──
        falling_knife = self._check_falling_knife(df, current_atr)
        rising_knife = self._check_rising_knife(df, current_atr)

        # ── Gating Logic (same as before, but interceptors override first) ──
        if regime == "TRENDING_UP" and sell_votes > buy_votes and sell_votes < 6:
            action = "HOLD"
            reason = "Suppressed SELL against TRENDING_UP regime"
        elif regime == "TRENDING_DOWN" and buy_votes > sell_votes and buy_votes < 6:
            action = "HOLD"
            reason = "Suppressed BUY against TRENDING_DOWN regime"
        elif buy_votes >= 5 and buy_votes > sell_votes:
            action = "BUY"
            reason = f"Strong Bullish Consensus ({buy_votes}/{total_models} models)"
        elif sell_votes >= 5 and sell_votes > buy_votes:
            action = "SELL"
            reason = f"Strong Bearish Consensus ({sell_votes}/{total_models} models)"
        elif buy_votes >= 4 and buy_votes > sell_votes and regime == "TRENDING_UP":
            action = "BUY"
            reason = f"Trend-aligned Bullish Consensus ({buy_votes}/{total_models} models)"
        elif sell_votes >= 4 and sell_votes > buy_votes and regime == "TRENDING_DOWN":
            action = "SELL"
            reason = f"Trend-aligned Bearish Consensus ({sell_votes}/{total_models} models)"
        else:
            action = "HOLD"
            reason = f"Market in balance or choppy consensus ({buy_votes} Buy, {sell_votes} Sell, {hold_votes} Hold)"

        # Apply Anti-Falling-Knife Interceptor AFTER gating
        if action == "BUY" and falling_knife:
            action = "HOLD"
            reason = "⚠️ FALLING KNIFE — Wait for rejection/confirmation candle before entry"
        elif action == "SELL" and rising_knife:
            action = "HOLD"
            reason = "⚠️ RISING KNIFE — Wait for rejection/confirmation candle before entry"

        # Append mean-reversion zone note if present
        if revert_note and action == "HOLD":
            reason = f"{reason} | {revert_note}"

        dominant_votes = max(buy_votes, sell_votes, hold_votes)
        confidence = round((dominant_votes / total_models) * 100, 1)

        rec_tp_pts = regime_info.get("recommended_tp_pts", 200)
        rec_sl_pts = regime_info.get("recommended_sl_pts", 120)
        point = 0.1

        if action == "BUY":
            entry_price = current_price
            sl_price = round(entry_price - (rec_sl_pts * point), 2)
            tp1_price = round(entry_price + (rec_tp_pts * 0.6 * point), 2)
            tp2_price = round(entry_price + (rec_tp_pts * point), 2)
            rr = round((tp2_price - entry_price) / max(entry_price - sl_price, 0.1), 2)
        elif action == "SELL":
            entry_price = current_price
            sl_price = round(entry_price + (rec_sl_pts * point), 2)
            tp1_price = round(entry_price - (rec_tp_pts * 0.6 * point), 2)
            tp2_price = round(entry_price - (rec_tp_pts * point), 2)
            rr = round((entry_price - tp2_price) / max(sl_price - entry_price, 0.1), 2)
        else:
            entry_price = current_price
            sl_price = 0.0
            tp1_price = 0.0
            tp2_price = 0.0
            rr = 0.0

        return {
            "action": action,
            "confidence": confidence,
            "buy_votes": buy_votes,
            "sell_votes": sell_votes,
            "hold_votes": hold_votes,
            "total_models": total_models,
            "votes": votes,
            "filter_reason": reason,
            "falling_knife_warning": falling_knife and action == "HOLD",
            "entry_price": entry_price,
            "sl_price": sl_price,
            "tp1_price": tp1_price,
            "tp2_price": tp2_price,
            "risk_reward_ratio": rr,
            "recommended_tp_pts": rec_tp_pts,
            "recommended_sl_pts": rec_sl_pts
        }


# ─────────────────────────────────────────────────────────────────────────────
# DIRECTIONAL BIAS ENGINE — Price Action Sniper Radar
# ─────────────────────────────────────────────────────────────────────────────

class DirectionalBiasEngine:
    """
    Aggregates MTF regime alignment, KER scores, and ensemble consensus
    to produce a single Directional Bias (BULLISH / BEARISH / NEUTRAL)
    and an Edge Score (0–100) for Price Action day trading.

    Scoring Breakdown (total 100 pts):
    - MTF Alignment (H1+M15+M5+M1):  40 pts  — most important for day trading
    - KER (H1+M15 averaged):          30 pts  — chop vs. trend quality
    - AI Consensus Strength:          20 pts  — ensemble vote confidence
    - ADX Trend Power (exec TF):      10 pts  — directional momentum
    """

    MTF_WATCH = ["H1", "M15", "M5", "M1"]   # day trading Timeframes

    def compute(
        self,
        mtf_regimes: Dict[str, Dict[str, Any]],
        ensemble_result: Dict[str, Any],
        exec_regime: Dict[str, Any],
        data_store: Dict[str, "pd.DataFrame"]
    ) -> Dict[str, Any]:

        # ── 1. MTF Alignment Score (40 pts) ──
        regimes_present = {
            tf: mtf_regimes[tf]["regime"]
            for tf in self.MTF_WATCH if tf in mtf_regimes
        }
        up_count = sum(1 for r in regimes_present.values() if r == "TRENDING_UP")
        down_count = sum(1 for r in regimes_present.values() if r == "TRENDING_DOWN")
        total_watch = len(self.MTF_WATCH)

        if up_count == total_watch:
            mtf_dir = "BULLISH"
            mtf_score = 40
        elif down_count == total_watch:
            mtf_dir = "BEARISH"
            mtf_score = 40
        elif up_count >= 3 and up_count > down_count:
            mtf_dir = "BULLISH"
            mtf_score = 28
        elif down_count >= 3 and down_count > up_count:
            mtf_dir = "BEARISH"
            mtf_score = 28
        elif up_count >= 2 and up_count > down_count:
            mtf_dir = "BULLISH"
            mtf_score = 14
        elif down_count >= 2 and down_count > up_count:
            mtf_dir = "BEARISH"
            mtf_score = 14
        else:
            mtf_dir = "NEUTRAL"
            mtf_score = 0

        # ── 2. KER Score (30 pts) — average H1 & M15 for day trading ──
        ker_detector = MarketRegimeDetector()
        ker_values = []
        for tf in ["H1", "M15"]:  # day trading reference TFs
            if tf in data_store and len(data_store[tf]) >= 22:
                ker = ker_detector.calculate_ker(data_store[tf]["Close"], period=20)
                ker_values.append(ker)
        avg_ker = round(sum(ker_values) / len(ker_values), 4) if ker_values else 0.5

        if avg_ker >= 0.60:
            ker_label = "TRENDING"
            ker_score = 30
        elif avg_ker >= 0.45:
            ker_label = "DRIFTING"
            ker_score = 15
        elif avg_ker >= 0.30:
            ker_label = "WEAK DRIFT"
            ker_score = 5
        else:
            ker_label = "CHOPPY"
            ker_score = 0

        # ── 3. AI Consensus Score (20 pts) ──
        buy_v = ensemble_result.get("buy_votes", 0)
        sell_v = ensemble_result.get("sell_votes", 0)
        total_m = ensemble_result.get("total_models", 9)
        dominant_votes = max(buy_v, sell_v)
        consensus_pct = dominant_votes / max(total_m, 1)

        if consensus_pct >= 0.78:   # ≥7/9 models
            ai_score = 20
        elif consensus_pct >= 0.67:  # ≥6/9
            ai_score = 14
        elif consensus_pct >= 0.55:  # ≥5/9
            ai_score = 7
        else:
            ai_score = 0

        # Direction agreement: AI direction must align with MTF direction
        ai_vote_dir = "BULLISH" if buy_v > sell_v else ("BEARISH" if sell_v > buy_v else "NEUTRAL")
        if ai_vote_dir != mtf_dir and mtf_dir != "NEUTRAL":
            ai_score = max(0, ai_score - 10)  # penalize AI-MTF conflict

        # ── 4. ADX Score (10 pts) ──
        adx = exec_regime.get("adx", 20.0)
        if adx >= 35:
            adx_score = 10
        elif adx >= 25:
            adx_score = 7
        elif adx >= 20:
            adx_score = 3
        else:
            adx_score = 0

        # ── Final Edge Score ──
        edge_score = min(100, mtf_score + ker_score + ai_score + adx_score)

        # ── Determine Final Directional Bias ──
        if edge_score >= 60 and mtf_dir == "BULLISH":
            final_bias = "BULLISH"
            bias_detail = f"High-probability bullish environment — look for BUY setups on M1/M5 pullbacks"
        elif edge_score >= 60 and mtf_dir == "BEARISH":
            final_bias = "BEARISH"
            bias_detail = f"High-probability bearish environment — look for SELL setups on M1/M5 bounces"
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

        # ── Falling-knife flag from ensemble ──
        falling_knife_active = ensemble_result.get("falling_knife_warning", False)
        if falling_knife_active:
            bias_detail = "⚠️ FALLING KNIFE DETECTED — Wait for price to stabilize before entry"

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
            "ai_consensus_score": ai_score,
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
    """Loads staged CSVs and runs regime detection, ensemble inference, and directional bias."""
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

    ensemble_engine = EnsembleEngine()
    ensemble_result = ensemble_engine.predict(exec_df, exec_regime)

    # Directional Bias (Price Action Sniper Radar)
    bias_engine = DirectionalBiasEngine()
    directional_bias = bias_engine.compute(
        mtf_regimes=mtf_regimes,
        ensemble_result=ensemble_result,
        exec_regime=exec_regime,
        data_store=data_store
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
        "ensemble": ensemble_result,
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
