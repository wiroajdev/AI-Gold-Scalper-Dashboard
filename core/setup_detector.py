"""
MTF Setup Detector — AI Gold Scalper Dashboard
Tracks the 3-step trading setup plan:
  Step 1: H1/M15 trending in one direction (macro bias confirmed)
  Step 2: M1/M5 pullback detected (ranging or opposite direction)
  Step 3: Bullish/Bearish Price Action at key zone (entry signal)
"""

from __future__ import annotations
import time
from typing import Any, Dict, Optional
import numpy as np
import pandas as pd


# ─── Constants ────────────────────────────────────────────────────────────────

MACRO_TFS = ["H1", "M15"]       # Trend confirmation timeframes
ENTRY_TFS  = ["M5", "M1"]       # Pullback / entry timeframes

ALERT_COOLDOWN_SEC = 900        # 15-minute cooldown after alert fires
ALERT_SCORE_THRESHOLD = 60      # Minimum confidence score to fire alert


# ─── Price Action Detector ─────────────────────────────────────────────────────

class PriceActionDetector:
    """Detects Pinbar and Engulfing candlestick patterns on a DataFrame."""

    @staticmethod
    def is_bullish_pinbar(df: pd.DataFrame) -> bool:
        """
        Bullish Pinbar: Long lower wick >= 2x body, closes bullish or near top.
        Requires at least 2 rows (current + previous).
        """
        if len(df) < 2:
            return False
        c = df.iloc[-1]
        body = abs(c["Close"] - c["Open"])
        lower_wick = c["Open"] - c["Low"] if c["Close"] >= c["Open"] else c["Close"] - c["Low"]
        upper_wick = c["High"] - c["Close"] if c["Close"] >= c["Open"] else c["High"] - c["Open"]
        if body < 1e-8:
            return False
        return lower_wick >= 2.0 * body and upper_wick <= body

    @staticmethod
    def is_bearish_pinbar(df: pd.DataFrame) -> bool:
        """
        Bearish Pinbar: Long upper wick >= 2x body, closes bearish or near bottom.
        """
        if len(df) < 2:
            return False
        c = df.iloc[-1]
        body = abs(c["Close"] - c["Open"])
        upper_wick = c["High"] - c["Open"] if c["Close"] >= c["Open"] else c["High"] - c["Close"]
        lower_wick = c["Open"] - c["Low"] if c["Close"] >= c["Open"] else c["Close"] - c["Low"]
        if body < 1e-8:
            return False
        return upper_wick >= 2.0 * body and lower_wick <= body

    @staticmethod
    def is_bullish_engulfing(df: pd.DataFrame) -> bool:
        """
        Bullish Engulfing: Current bullish candle's body fully engulfs previous bearish candle's body.
        """
        if len(df) < 2:
            return False
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        prev_bearish = prev["Close"] < prev["Open"]
        curr_bullish = curr["Close"] > curr["Open"]
        engulfs = curr["Open"] <= prev["Close"] and curr["Close"] >= prev["Open"]
        return prev_bearish and curr_bullish and engulfs

    @staticmethod
    def is_bearish_engulfing(df: pd.DataFrame) -> bool:
        """
        Bearish Engulfing: Current bearish candle's body fully engulfs previous bullish candle's body.
        """
        if len(df) < 2:
            return False
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        prev_bullish = prev["Close"] > prev["Open"]
        curr_bearish = curr["Close"] < curr["Open"]
        engulfs = curr["Open"] >= prev["Close"] and curr["Close"] <= prev["Open"]
        return prev_bullish and curr_bearish and engulfs

    @classmethod
    def scan(cls, df: pd.DataFrame, bias: str) -> Dict[str, Any]:
        """
        Scan a DataFrame for relevant price action patterns based on bias.
        Returns pattern name, strength, and whether it fired.
        """
        result = {"pattern": None, "fired": False, "score": 0}
        if df is None or len(df) < 2:
            return result

        if bias == "BULLISH":
            if cls.is_bullish_engulfing(df):
                result.update({"pattern": "BULLISH_ENGULFING", "fired": True, "score": 30})
            elif cls.is_bullish_pinbar(df):
                result.update({"pattern": "BULLISH_PINBAR", "fired": True, "score": 35})
        elif bias == "BEARISH":
            if cls.is_bearish_engulfing(df):
                result.update({"pattern": "BEARISH_ENGULFING", "fired": True, "score": 30})
            elif cls.is_bearish_pinbar(df):
                result.update({"pattern": "BEARISH_PINBAR", "fired": True, "score": 35})

        return result


# ─── Zone Confluence Scorer ────────────────────────────────────────────────────

class ZoneScorer:
    """
    Scores whether price is at a key support/resistance zone.
    Checks five zone types (in order of institutional significance):
      1. S/R Flip Level   — old S/R that changed polarity after a break (25 pts)
      2. Order Block      — institutional supply/demand candle before impulse (25 pts)
      3. Fair Value Gap   — unfilled 3-candle imbalance gap (20 pts)
      4. EMA 20 proximity — dynamic mean-reversion reference (20 pts)
      5. Swing High/Low   — recent ATR-based structural pivot (15 pts)

    Scoring summary (max 105 → capped at 100):
      PA Pinbar(35) + OB(25)    = 60 → Alert fires  ✅
      PA Engulfing(30) + Flip(25) + EMA(20) = 75 → Alert fires ✅
      EMA(20) + FVG(20) alone   = 40 → No alert  ✅ (correct — weak zone)
    """

    @staticmethod
    def _ema20(closes: pd.Series) -> float:
        return float(closes.ewm(span=20, adjust=False).mean().iloc[-1])

    @staticmethod
    def _current_atr(df: pd.DataFrame, period: int = 14) -> float:
        high, low, close = df["High"], df["Low"], df["Close"]
        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low  - close.shift(1)).abs()
        ], axis=1).max(axis=1)
        atr = tr.rolling(period).mean()
        val = float(atr.iloc[-1])
        return val if not np.isnan(val) else 2.0

    @staticmethod
    def _find_swing_low(df: pd.DataFrame, lookback: int = 20) -> Optional[float]:
        """Find the lowest low in recent lookback bars (3-bar pivot)."""
        if len(df) < lookback + 2:
            return None
        lows = df["Low"].iloc[-(lookback + 2):-1]
        return float(lows.min())

    @staticmethod
    def _find_swing_high(df: pd.DataFrame, lookback: int = 20) -> Optional[float]:
        """Find the highest high in recent lookback bars (3-bar pivot)."""
        if len(df) < lookback + 2:
            return None
        highs = df["High"].iloc[-(lookback + 2):-1]
        return float(highs.max())

    @staticmethod
    def _find_fvg_zone(df: pd.DataFrame, bias: str) -> Optional[tuple]:
        """
        Detect the most recent Fair Value Gap (FVG) based on 3-candle pattern.
        Bullish FVG: candle[i].High < candle[i+2].Low  (gap above candle[i])
        Bearish FVG: candle[i].Low > candle[i+2].High  (gap below candle[i])
        Returns (zone_low, zone_high) or None.
        """
        if len(df) < 10:
            return None
        lookback = min(15, len(df) - 2)
        for i in range(-lookback, -2):
            c0 = df.iloc[i]
            c2 = df.iloc[i + 2]
            if bias == "BULLISH":
                if c0["High"] < c2["Low"]:
                    zone = (c0["High"], c2["Low"])
                    later_lows = df["Low"].iloc[i + 2:]
                    if float(later_lows.min()) > zone[0]:
                        return zone
            elif bias == "BEARISH":
                if c0["Low"] > c2["High"]:
                    zone = (c2["High"], c0["Low"])
                    later_highs = df["High"].iloc[i + 2:]
                    if float(later_highs.max()) < zone[1]:
                        return zone
        return None

    @staticmethod
    def _find_swing_pivots(df: pd.DataFrame, lookback: int = 80) -> list:
        """
        3-bar pivot rule: bar[i].High > bar[i-1].High AND bar[i].High > bar[i+1].High.
        Scans last `lookback` bars (excluding final 2 which need right-side confirmation).
        Returns list of dicts: {type: 'HIGH'|'LOW', price: float, idx: int}
        """
        pivots = []
        n = len(df)
        if n < 5:
            return pivots
        scan_start = max(1, n - lookback - 1)
        scan_end   = n - 2  # need one confirmed bar to the right
        for i in range(scan_start, scan_end):
            h = df["High"].iloc
            l = df["Low"].iloc
            if h[i] > h[i - 1] and h[i] > h[i + 1]:
                pivots.append({"type": "HIGH", "price": float(df["High"].iloc[i]), "idx": i})
            if l[i] < l[i - 1] and l[i] < l[i + 1]:
                pivots.append({"type": "LOW",  "price": float(df["Low"].iloc[i]),  "idx": i})
        return pivots

    @staticmethod
    def _find_flip_zone(
        df: pd.DataFrame,
        bias: str,
        atr: float,
        htf_df: Optional[pd.DataFrame] = None,
    ) -> Optional[float]:
        """
        S/R Flip Level Detection:
          BULLISH — find a past Swing High that price broke above (old resistance → new support).
                    Return it if current price is retesting from above (within 0.6 ATR).
          BEARISH — find a past Swing Low that price broke below (old support → new resistance).
                    Return it if current price is retesting from below (within 0.6 ATR).

        Prefers HTF (M15/H1) data for cleaner pivot structure.
        """
        ref_df    = htf_df if (htf_df is not None and len(htf_df) >= 20) else df
        if len(ref_df) < 10:
            return None

        current_price = float(df["Close"].iloc[-1])
        proximity     = atr * 0.6
        pivots        = ZoneScorer._find_swing_pivots(ref_df, lookback=80)

        best_flip = None
        best_dist = float("inf")

        if bias == "BULLISH":
            for p in pivots:
                if p["type"] != "HIGH":
                    continue
                level = p["price"]
                # Price must currently be above this old high (broke through it)
                if current_price <= level:
                    continue
                # Confirm the break: at least one close after the pivot is above level
                subseq_closes = ref_df["Close"].iloc[p["idx"] + 1:]
                if len(subseq_closes) == 0 or float(subseq_closes.max()) <= level:
                    continue
                dist = abs(current_price - level)
                if dist <= proximity and dist < best_dist:
                    best_flip = level
                    best_dist = dist

        elif bias == "BEARISH":
            for p in pivots:
                if p["type"] != "LOW":
                    continue
                level = p["price"]
                # Price must currently be below this old low
                if current_price >= level:
                    continue
                subseq_closes = ref_df["Close"].iloc[p["idx"] + 1:]
                if len(subseq_closes) == 0 or float(subseq_closes.min()) >= level:
                    continue
                dist = abs(current_price - level)
                if dist <= proximity and dist < best_dist:
                    best_flip = level
                    best_dist = dist

        return round(best_flip, 2) if best_flip is not None else None

    @staticmethod
    def _find_order_block(
        df: pd.DataFrame,
        bias: str,
        atr: float,
    ) -> Optional[Dict]:
        """
        Institutional Order Block (OB) Detection:

        Bullish OB (Demand Zone):
          Last BEARISH candle before a bullish impulse move (≥ 2 bullish candles,
          total move ≥ 1.5x ATR). Unmitigated = no close below OB's low since formation.

        Bearish OB (Supply Zone):
          Last BULLISH candle before a bearish impulse move.
          Unmitigated = no close above OB's high since formation.

        Returns dict(ob_high, ob_low, ob_mid, type) or None if none found / all mitigated.
        """
        if len(df) < 10:
            return None

        current_price     = float(df["Close"].iloc[-1])
        proximity         = atr * 0.8
        impulse_threshold = atr * 1.5
        n                 = len(df)
        scan_start        = max(1, n - 60)
        scan_end          = n - 3  # need ≥ 2 bars after the OB candle

        if bias == "BULLISH":
            for i in range(scan_end, scan_start, -1):
                c = df.iloc[i]
                if c["Close"] >= c["Open"]:  # must be bearish candle
                    continue
                next_bars = df.iloc[i + 1: i + 4]
                if len(next_bars) < 2:
                    continue
                bull_count  = int((next_bars["Close"] > next_bars["Open"]).sum())
                total_move  = float(next_bars["Close"].iloc[-1] - c["Close"])
                if bull_count < 2 or total_move < impulse_threshold:
                    continue
                ob_high = float(c["High"])
                ob_low  = float(c["Low"])
                # Mitigation check: price closed below OB low AFTER the impulse
                post_impulse_lows = df["Low"].iloc[i + 4:]
                if len(post_impulse_lows) > 0 and float(post_impulse_lows.min()) < ob_low:
                    continue  # fully mitigated — price returned through OB
                # Is price currently in / near the OB zone?
                if ob_low - proximity <= current_price <= ob_high + proximity:
                    return {
                        "ob_high": round(ob_high, 2),
                        "ob_low":  round(ob_low,  2),
                        "ob_mid":  round((ob_high + ob_low) / 2, 2),
                        "type":    "DEMAND",
                    }

        elif bias == "BEARISH":
            for i in range(scan_end, scan_start, -1):
                c = df.iloc[i]
                if c["Close"] <= c["Open"]:  # must be bullish candle
                    continue
                next_bars = df.iloc[i + 1: i + 4]
                if len(next_bars) < 2:
                    continue
                bear_count  = int((next_bars["Close"] < next_bars["Open"]).sum())
                total_move  = float(c["Close"] - next_bars["Close"].iloc[-1])
                if bear_count < 2 or total_move < impulse_threshold:
                    continue
                ob_high = float(c["High"])
                ob_low  = float(c["Low"])
                # Mitigation check: price closed above OB high AFTER the impulse
                post_impulse_highs = df["High"].iloc[i + 4:]
                if len(post_impulse_highs) > 0 and float(post_impulse_highs.max()) > ob_high:
                    continue  # fully mitigated
                if ob_low - proximity <= current_price <= ob_high + proximity:
                    return {
                        "ob_high": round(ob_high, 2),
                        "ob_low":  round(ob_low,  2),
                        "ob_mid":  round((ob_high + ob_low) / 2, 2),
                        "type":    "SUPPLY",
                    }

        return None

    @classmethod
    def score(
        cls,
        df: pd.DataFrame,
        bias: str,
        htf_df: Optional[pd.DataFrame] = None,
    ) -> Dict[str, Any]:
        """
        Returns zone_score (0–100), zones_hit (list), and all zone details.
        htf_df (optional M15/H1 df) improves S/R Flip pivot accuracy.
        """
        empty = {
            "zone_score": 0, "zones_hit": [],
            "ema20": None, "fvg_zone": None, "swing_level": None,
            "flip_zone": None, "order_block": None,
        }
        if df is None or len(df) < 25:
            return empty

        price     = float(df["Close"].iloc[-1])
        atr       = cls._current_atr(df)
        proximity = atr * 0.5

        zones_hit  = []
        zone_score = 0

        # ── 1. S/R Flip Zone (25 pts) ─────────────────────────────────────────
        flip_zone = cls._find_flip_zone(df, bias, atr, htf_df)
        if flip_zone is not None:
            zones_hit.append("FLIP_ZONE")
            zone_score += 25

        # ── 2. Order Block / Supply-Demand Zone (25 pts) ──────────────────────
        order_block = cls._find_order_block(df, bias, atr)
        if order_block is not None:
            zones_hit.append("ORDER_BLOCK")
            zone_score += 25

        # ── 3. FVG Zone (20 pts) ──────────────────────────────────────────────
        fvg = cls._find_fvg_zone(df, bias)
        fvg_hit = False
        if fvg:
            fvg_low, fvg_high = fvg
            if fvg_low <= price <= fvg_high or abs(price - fvg_low) <= proximity or abs(price - fvg_high) <= proximity:
                zones_hit.append("FVG")
                zone_score += 20
                fvg_hit = True

        # ── 4. EMA 20 Zone (20 pts) ───────────────────────────────────────────
        ema20 = cls._ema20(df["Close"])
        if abs(price - ema20) <= proximity:
            zones_hit.append("EMA20")
            zone_score += 20

        # ── 5. ATR-based Swing Level (15 pts) ─────────────────────────────────
        swing_level = None
        if bias == "BULLISH":
            swing_level = cls._find_swing_low(df)
            if swing_level and abs(price - swing_level) <= atr * 1.0:
                zones_hit.append("SWING_LOW")
                zone_score += 15
        elif bias == "BEARISH":
            swing_level = cls._find_swing_high(df)
            if swing_level and abs(price - swing_level) <= atr * 1.0:
                zones_hit.append("SWING_HIGH")
                zone_score += 15

        return {
            "zone_score":  min(100, zone_score),
            "zones_hit":   zones_hit,
            "ema20":       round(ema20, 2),
            "fvg_zone":    (round(fvg[0], 2), round(fvg[1], 2)) if fvg else None,
            "swing_level": round(swing_level, 2) if swing_level else None,
            "flip_zone":   flip_zone,
            "order_block": order_block,
        }


# ─── MTF Setup State Machine ───────────────────────────────────────────────────

class MTFSetupDetector:
    """
    Tracks the 3-step MTF Pullback Setup and fires alert when all conditions met.

    State transitions:
      IDLE → STEP1 (H1 & M15 both trending same direction)
      STEP1 → STEP2 (M1 or M5 pullback: RANGING or opposite direction)
      STEP2 → ALERT (Price Action + Zone confluence threshold reached)
      ALERT → IDLE (after cooldown, or macro regime change)
    """

    STATES = ("IDLE", "STEP1", "STEP2", "ALERT")

    def __init__(self):
        self.state: str = "IDLE"
        self.bias: Optional[str] = None         # "BULLISH" or "BEARISH"
        self.last_alert_time: float = 0.0
        self.last_alert_key: Optional[str] = None
        self._step2_bars: int = 0               # Consecutive bars in Step2

    # ── Public API ──────────────────────────────────────────────────────────

    def evaluate(
        self,
        mtf_regimes: Dict[str, Dict[str, Any]],
        data_store: Dict[str, pd.DataFrame],
    ) -> Dict[str, Any]:
        """
        Main evaluation method called on each data cycle.
        Returns full status dict consumed by /api/setup_status endpoint.
        """
        now = time.time()

        # ── Guard: cooldown reset ────────────────────────────────────────────
        if self.state == "ALERT" and (now - self.last_alert_time) >= ALERT_COOLDOWN_SEC:
            self._reset()

        # ── Step 1: Check macro trend (H1 + M15) ────────────────────────────
        step1_ok, bias = self._check_step1(mtf_regimes)

        # If macro bias changed or no longer valid → reset
        if not step1_ok:
            self._reset()
            return self._build_result(step1_ok=False)

        # Macro trend confirmed — update bias
        if self.state == "IDLE":
            self.state = "STEP1"
            self.bias = bias
        elif bias != self.bias:
            # Regime flipped — full reset
            self._reset()
            return self._build_result(step1_ok=False)

        # ── Step 2: Check entry TF pullback (M1 / M5) ───────────────────────
        step2_ok, step2_detail = self._check_step2(mtf_regimes)

        if step2_ok and self.state == "STEP1":
            self.state = "STEP2"
            self._step2_bars = 1
        elif step2_ok and self.state == "STEP2":
            self._step2_bars += 1
        elif not step2_ok and self.state == "STEP2":
            # Pullback over (M1/M5 resumed trend) — back to Step1 watching
            self.state = "STEP1"
            self._step2_bars = 0

        if self.state not in ("STEP2", "ALERT"):
            return self._build_result(step1_ok=True, step2_detail=step2_detail)

        # ── Step 3: Price Action + Zone Confluence ───────────────────────────
        pa_result, zone_result, confidence = self._check_step3(data_store)

        if self.state == "STEP2" and confidence >= ALERT_SCORE_THRESHOLD:
            self.state = "ALERT"
            self.last_alert_time = now
            alert_key = f"{self.bias}_{pa_result.get('pattern', 'PA')}_{int(now)}"
            self.last_alert_key = alert_key

        alert_msg = self._build_alert_message(pa_result, zone_result, confidence) \
                    if self.state == "ALERT" else None

        return self._build_result(
            step1_ok=True,
            step2_ok=step2_ok,
            step2_detail=step2_detail,
            step3_ok=(self.state == "ALERT"),
            pa_result=pa_result,
            zone_result=zone_result,
            confidence=confidence,
            alert_msg=alert_msg,
        )

    # ── Private helpers ──────────────────────────────────────────────────────

    def _reset(self):
        self.state = "IDLE"
        self.bias = None
        self._step2_bars = 0

    def _check_step1(self, mtf_regimes: Dict) -> tuple[bool, Optional[str]]:
        """Returns (valid, bias) — both H1 and M15 must trend same direction."""
        h1_reg  = mtf_regimes.get("H1",  {}).get("regime", "")
        m15_reg = mtf_regimes.get("M15", {}).get("regime", "")

        if h1_reg == "TRENDING_UP" and m15_reg == "TRENDING_UP":
            return True, "BULLISH"
        if h1_reg == "TRENDING_DOWN" and m15_reg == "TRENDING_DOWN":
            return True, "BEARISH"
        return False, None

    def _check_step2(self, mtf_regimes: Dict) -> tuple[bool, Dict]:
        """
        Step 2 passes when at least one of M1/M5 shows a pullback:
        RANGING or opposite direction to macro bias.
        """
        pullback_tfs  = []
        opposite_tfs  = []
        opposite_reg  = "TRENDING_DOWN" if self.bias == "BULLISH" else "TRENDING_UP"

        for tf in ENTRY_TFS:
            reg = mtf_regimes.get(tf, {}).get("regime", "")
            if reg == "RANGING":
                pullback_tfs.append(tf)
            elif reg == opposite_reg:
                opposite_tfs.append(tf)

        pullback_detected = len(pullback_tfs) > 0 or len(opposite_tfs) > 0
        return pullback_detected, {
            "ranging_tfs":  pullback_tfs,
            "opposite_tfs": opposite_tfs,
            "both_tfs":     len(pullback_tfs) + len(opposite_tfs) >= 2,
        }

    def _check_step3(self, data_store: Dict) -> tuple[Dict, Dict, int]:
        """
        Step 3: Scan M1 and M5 for Price Action patterns + Zone Confluence.
        Confidence = PA score + Zone score + bonus if both TFs fire.
        Uses M15 as HTF reference for S/R Flip accuracy.
        """
        best_pa    = {"pattern": None, "fired": False, "score": 0, "tf": None}
        best_zone  = {"zone_score": 0, "zones_hit": [], "flip_zone": None, "order_block": None}
        both_fired = 0

        htf_df = data_store.get("M15") or data_store.get("H1")

        for tf in ENTRY_TFS:
            df = data_store.get(tf)
            if df is None or len(df) < 5:
                continue

            pa = PriceActionDetector.scan(df, self.bias)
            zn = ZoneScorer.score(df, self.bias, htf_df=htf_df)

            if pa["fired"]:
                both_fired += 1
                if pa["score"] > best_pa["score"]:
                    best_pa = {**pa, "tf": tf}

            if zn["zone_score"] > best_zone["zone_score"]:
                best_zone = zn

        # Bonus: both M1 & M5 fired PA simultaneously
        bonus = 20 if both_fired >= 2 else 0

        confidence = min(100, best_pa["score"] + best_zone["zone_score"] + bonus)
        return best_pa, best_zone, confidence

    def _build_alert_message(self, pa: Dict, zone: Dict, confidence: int) -> str:
        direction = "🟢 BUY" if self.bias == "BULLISH" else "🔴 SELL"
        pattern   = pa.get("pattern", "Price Action").replace("_", " ").title()
        tf        = pa.get("tf", "M5")
        zones     = " + ".join(zone.get("zones_hit", [])) or "Near Key Level"
        return (
            f"{direction} Setup Ready — {pattern} on {tf}\n"
            f"Zone: {zones} | Confidence: {confidence}%\n"
            f"H1/M15 trend confirmed ✅ | Pullback complete ✅ | PA entry signal ✅"
        )

    def _build_result(
        self,
        step1_ok: bool = False,
        step2_ok: bool = False,
        step2_detail: Optional[Dict] = None,
        step3_ok: bool = False,
        pa_result: Optional[Dict] = None,
        zone_result: Optional[Dict] = None,
        confidence: int = 0,
        alert_msg: Optional[str] = None,
    ) -> Dict[str, Any]:
        cooldown_remaining = 0
        if self.state == "ALERT":
            elapsed = time.time() - self.last_alert_time
            cooldown_remaining = max(0, int(ALERT_COOLDOWN_SEC - elapsed))

        return {
            "state":              self.state,
            "bias":               self.bias,
            "step1_ok":           step1_ok,
            "step2_ok":           step2_ok,
            "step2_detail":       step2_detail or {},
            "step3_ok":           step3_ok,
            "confidence_score":   confidence,
            "price_action":       pa_result.get("pattern") if pa_result else None,
            "price_action_tf":    pa_result.get("tf")      if pa_result else None,
            "zones_hit":          zone_result.get("zones_hit", []) if zone_result else [],
            "ema20":              zone_result.get("ema20")         if zone_result else None,
            "fvg_zone":           zone_result.get("fvg_zone")      if zone_result else None,
            "swing_level":        zone_result.get("swing_level")   if zone_result else None,
            "flip_zone":          zone_result.get("flip_zone")     if zone_result else None,
            "order_block":        zone_result.get("order_block")   if zone_result else None,
            "alert_message":      alert_msg,
            "alert_key":          self.last_alert_key,
            "cooldown_remaining": cooldown_remaining,
            "alert_threshold":    ALERT_SCORE_THRESHOLD,
        }


# ─── Singleton instance (shared across Flask requests) ────────────────────────

_setup_detector_instance: Optional[MTFSetupDetector] = None


def get_setup_detector() -> MTFSetupDetector:
    global _setup_detector_instance
    if _setup_detector_instance is None:
        _setup_detector_instance = MTFSetupDetector()
    return _setup_detector_instance
