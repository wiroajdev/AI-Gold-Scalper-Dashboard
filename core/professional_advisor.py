"""
Professional Advisor — AI Gold Scalper Dashboard
Generates professional trade setups, actionable market narratives, and daily
volatility/energy budget analytics based on institutional flow, session ranges,
and multi-timeframe price action principles.
"""

from __future__ import annotations
import math
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd


class ProfessionalAdvisor:
    """
    Expert advisor engine synthesizing:
      1. Trade Setup: Action (BUY/SELL/HOLD), Entry Zone, SL, TP1, TP2, R:R
      2. Market Situation Narrative: Price Action, traps, microstructure, rules
      3. Daily Volatility & Energy Budget: ADR consumption, Type A vs Type B,
         institutional outlook, and Friday thin liquidity protection.
    """

    def __init__(self):
        pass

    def evaluate(
        self,
        current_price: float,
        mtf_regimes: Dict[str, Dict[str, Any]],
        session_levels: Dict[str, Any],
        sr_levels: List[Dict[str, Any]],
        setup_status: Dict[str, Any],
        data_store: Dict[str, pd.DataFrame],
        now_dt: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Main entry point called on each fetch/analysis cycle.
        Returns a structured dictionary with:
          - trade_setup: Dict
          - market_narrative: List[str]
          - energy_budget: Dict
          - updated_at: str
        """
        # 1. Normalize Thai Time (UTC+7)
        if now_dt is None:
            # Use local time or UTC+7
            utc_now = datetime.now(timezone.utc)
            thai_now = utc_now + timedelta(hours=7)
        else:
            if now_dt.tzinfo is None:
                thai_now = now_dt.replace(tzinfo=timezone(timedelta(hours=7)))
            else:
                thai_now = now_dt.astimezone(timezone(timedelta(hours=7)))

        # 2. Extract Session Levels & Key S/R
        asian = session_levels.get("asian", {})
        london = session_levels.get("london", {})
        asian_high = asian.get("high")
        asian_low = asian.get("low")
        london_high = london.get("high")
        london_low = london.get("low")

        # 3. Calculate Daily Range & ADR Energy Budget
        energy_budget = self._calculate_energy_budget(data_store, current_price, thai_now, mtf_regimes)

        # 4. Generate Trade Setup & Tactical Levels
        trade_setup = self._generate_trade_setup(
            current_price=current_price,
            mtf_regimes=mtf_regimes,
            setup_status=setup_status,
            asian_high=asian_high,
            asian_low=asian_low,
            london_high=london_high,
            london_low=london_low,
            sr_levels=sr_levels,
            energy_budget=energy_budget,
            thai_now=thai_now,
        )

        # 5. Generate Market Situation Narrative
        market_narrative = self._generate_market_narrative(
            current_price=current_price,
            mtf_regimes=mtf_regimes,
            setup_status=setup_status,
            trade_setup=trade_setup,
            energy_budget=energy_budget,
            asian_high=asian_high,
            asian_low=asian_low,
            london_high=london_high,
            london_low=london_low,
            thai_now=thai_now,
        )

        return {
            "status": "success",
            "trade_setup": trade_setup,
            "market_narrative": market_narrative,
            "energy_budget": energy_budget,
            "updated_at": thai_now.strftime("%H:%M:%S"),
            "server_date": thai_now.strftime("%Y-%m-%d"),
        }

    # ─── Private Helpers: Energy Budget ───────────────────────────────────────

    def _calculate_energy_budget(
        self,
        data_store: Dict[str, pd.DataFrame],
        current_price: float,
        thai_now: datetime,
        mtf_regimes: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Computes ADR(14), today's high/low, % energy consumed, Gross Traveled Distance,
        Energy Efficiency Ratio (EER), KER/Volatility Squeeze, and classifies market states
        (Spring-Loaded, Meat Grinder, Clean Expansion, Exhaustion, Weekend).
        """
        # Find Day High / Day Low
        day_high = current_price
        day_low = current_price
        adr14 = 34.0  # fallback default gold ADR ~$34

        # Try to find today's bars in M15 or M5
        df_m15 = data_store.get("M15")
        df_m5  = data_store.get("M5")
        df_d1  = data_store.get("D1")

        # 1. ADR from D1 if available
        if df_d1 is not None and len(df_d1) >= 5:
            highs = df_d1["High"].iloc[-15:-1]
            lows  = df_d1["Low"].iloc[-15:-1]
            ranges = (highs - lows).dropna()
            if len(ranges) >= 3:
                adr14 = float(ranges.mean())

        # 2. Today's High / Low & All-Day Gross Traveled Path from M15 or M5
        ref_df = df_m15 if (df_m15 is not None and len(df_m15) >= 20) else df_m5
        daily_gross_travel = 0.0

        if ref_df is not None and "Time" in ref_df.columns:
            try:
                # Find today's date string (e.g. "2026.09.19" or "2026-09-19")
                today_str1 = thai_now.strftime("%Y.%m.%d")
                today_str2 = thai_now.strftime("%Y-%m-%d")
                today_mask = ref_df["Time"].astype(str).str.contains(today_str1) | ref_df["Time"].astype(str).str.contains(today_str2)
                today_rows = ref_df[today_mask]
                
                # If no today_rows matched (broker time offset / market closed), use the date of the latest bar
                if len(today_rows) == 0 and len(ref_df) > 0:
                    latest_date = str(ref_df["Time"].iloc[-1]).split()[0]
                    today_rows = ref_df[ref_df["Time"].astype(str).str.startswith(latest_date)]

                if len(today_rows) > 0:
                    day_high = max(float(today_rows["High"].max()), current_price)
                    day_low  = min(float(today_rows["Low"].min()), current_price)
                    daily_gross_travel = float((today_rows["High"] - today_rows["Low"]).sum())
                else:
                    # Last 48 bars as intraday fallback
                    lookback_rows = ref_df.iloc[-48:]
                    day_high = max(float(lookback_rows["High"].max()), current_price)
                    day_low  = min(float(lookback_rows["Low"].min()), current_price)
                    daily_gross_travel = float((lookback_rows["High"] - lookback_rows["Low"]).sum())
            except Exception:
                pass
        elif ref_df is not None and len(ref_df) >= 24:
            lookback_rows = ref_df.iloc[-48:]
            day_high = max(float(lookback_rows["High"].max()), current_price)
            day_low  = min(float(lookback_rows["Low"].min()), current_price)
            daily_gross_travel = float((lookback_rows["High"] - lookback_rows["Low"]).sum())

        current_day_range = round(max(0.1, day_high - day_low), 2)
        daily_gross_travel = round(max(current_day_range, daily_gross_travel), 2)
        daily_travel_ratio = round(daily_gross_travel / max(current_day_range, 0.1), 1)

        adr14 = round(max(15.0, adr14), 2)
        energy_pct = round(min(150.0, (current_day_range / adr14) * 100), 1)

        # 3. Active 4-Hour Rolling Window (16 bars for M15, 48 bars for M5)
        is_m15 = (ref_df is df_m15)
        active_window_bars = 16 if is_m15 else 48

        if ref_df is not None and len(ref_df) > 0:
            active_rows = ref_df.iloc[-active_window_bars:]
            act_high = max(float(active_rows["High"].max()), current_price)
            act_low  = min(float(active_rows["Low"].min()), current_price)
            active_range = round(max(0.1, act_high - act_low), 2)
            active_gross_travel = round(float((active_rows["High"] - active_rows["Low"]).sum()), 2)
            active_gross_travel = max(active_range, active_gross_travel)
        else:
            active_range = current_day_range
            active_gross_travel = daily_gross_travel

        travel_ratio = round(active_gross_travel / max(active_range, 0.1), 1)
        eer = round((active_range / max(active_gross_travel, 0.1)) * 100, 1)

        # 4. Session Detection (Harmonized with Professional Golden Windows)
        hour = thai_now.hour
        minute = thai_now.minute
        time_dec = hour + minute / 60.0

        if 13.5 <= time_dec < 16.5:
            active_session_name = "LONDON"
            active_session_label = "London Session"
        elif 19.5 <= time_dec < 22.5:
            active_session_name = "NY_OVERLAP"
            active_session_label = "NY Overlap Session"
        elif 5.0 <= time_dec < 13.5:
            active_session_name = "ASIAN"
            active_session_label = "Asian Session"
        else:
            active_session_name = "OFF_HOURS"
            active_session_label = "Off-Hours"

        # 5. Extract KER, Volatility & Squeeze Dynamics from regimes
        m15_reg = (mtf_regimes or {}).get("M15", {})
        m5_reg  = (mtf_regimes or {}).get("M5", {})
        ker = float(m15_reg.get("ker") or m5_reg.get("ker") or 0.5)
        ker_label = str(m15_reg.get("ker_label") or m5_reg.get("ker_label") or "DRIFTING")
        atr_ratio = float(m15_reg.get("atr_ratio") or m5_reg.get("atr_ratio") or 1.0)
        vol_status = str(m15_reg.get("volatility_status") or m5_reg.get("volatility_status") or "NORMAL")

        bb_squeeze = False
        if ref_df is not None and len(ref_df) >= 30:
            try:
                closes = ref_df["Close"]
                std = closes.rolling(20).std()
                mean = closes.rolling(20).mean()
                bw = (std * 2) / mean.replace(0, 1e-6)
                recent_bw = bw.iloc[-1]
                bw_q25 = bw.rolling(min(40, len(bw))).quantile(0.25).iloc[-1]
                if (not np.isnan(recent_bw) and not np.isnan(bw_q25) and recent_bw <= bw_q25) or atr_ratio <= 0.75:
                    bb_squeeze = True
            except Exception:
                if atr_ratio <= 0.75:
                    bb_squeeze = True
        elif atr_ratio <= 0.75:
            bb_squeeze = True

        # 6. Day & Weekend Classification
        weekday = thai_now.weekday()  # Monday=0, Tuesday=1, ... Friday=4, Saturday=5, Sunday=6
        is_weekend = weekday in [5, 6]
        is_saturday = weekday == 5
        is_sunday = weekday == 6
        is_friday = weekday == 4

        # Friday De-risking Threshold (65% ADR cap instead of 80%)
        is_friday_exhausted = is_friday and (energy_pct >= 65.0 or hour >= 21)

        # 7. Energy Status Label & Classification
        is_meat_grinder = (
            (travel_ratio >= 2.5 or eer <= 30.0) or
            ((travel_ratio >= 2.0 or eer <= 35.0) and (ker_label == "CHOPPY" or atr_ratio >= 1.05 or vol_status in ["HIGH_VOLATILITY", "EXTREME_VOLATILITY"]))
        )

        if is_weekend:
            energy_level = "WEEKEND"
            energy_color = "slate"
            energy_desc = f"ตลาดปิดทำการสุดสัปดาห์ — สรุปกรอบราคาปิดวันศุกร์ล่าสุดอยู่ที่ ${current_day_range:.2f} ({energy_pct}% ของ ADR)"
            session_type = "WEEKEND RECAP (Friday Close)"
            session_badge = "type-weekend"
            outlook_text = (
                f"ตลาดทองคำ Forex/MT5 ปิดทำการช่วงวันหยุดสุดสัปดาห์ (ข้อมูลล่าสุดอ้างอิงราคาปิดวันศุกร์ที่ ${current_price:.2f}) "
                "ขณะนี้ไม่มีเงินทุนสถาบันหมุนเวียนในตลาด ให้ใช้เวลานี้ทำการบ้าน ทบทวนสถิติ วางแผนแนวรับแนวต้าน และรอการเปิดตลาดใหม่ในเช้าวันจันทร์"
            )
        elif is_friday_exhausted:
            energy_level = "EXHAUSTED"
            energy_color = "red"
            if hour >= 21:
                energy_desc = f"คืนวันศุกร์หลัง 21:00 น. สถาบันปิดสมุดบัญชีลดความเสี่ยงวันหยุด (De-risking) สภาพคล่องกลวง"
                session_type = "FRIDAY DE-RISK (Thin Liquidity)"
                session_badge = "type-a"
                outlook_text = (
                    f"คืนวันศุกร์หลัง 21:00 น. เงินทุนสถาบันหลักถอนตัวออกหมดแล้ว เหลือเพียงสภาพคล่องที่กลวง (Thin Liquidity) "
                    f"ราคาวันนี้วิ่งไปแล้ว ${current_day_range:.2f} ({energy_pct}% ของ ADR) มักเกิดการสะบัดหลอกกิน SL สองทาง ไม่ควรเปิดสถานะข้ามสัปดาห์"
                )
            else:
                energy_desc = f"วันศุกร์ราคาวิ่งแตะ ${current_day_range:.2f} ({energy_pct}% ของ ADR) ชนเพดานปลอดภัยของสัปดาห์แล้ว"
                session_type = "FRIDAY EXHAUSTED (Weekend Prep)"
                session_badge = "type-a"
                outlook_text = (
                    f"วันศุกร์ราคาวิ่งไปแล้ว ${current_day_range:.2f} ({energy_pct}% ของ ADR) กองทุนใหญ่เริ่มทยอยทำกำไรและไม่เปิดสถานะใหม่ "
                    f"เพื่อป้องกันความเสี่ยงวันหยุด พลังงานคลื่นหลักของสัปดาห์จบลงแล้ว แนะนำปิดจอถือเงินสด"
                )
        elif energy_pct >= 80.0:
            energy_level = "EXHAUSTED"
            energy_color = "red"
            energy_desc = "พลังงานของวันถูกใช้ไปเกือบหมดแล้ว สถาบันเริ่มชะลอการดันราคา โอกาสวิ่งต่อไกลๆ มีจำกัด"
            session_type = "TYPE A (Exhaustion Move)"
            session_badge = "type-a"
            outlook_text = (
                f"วันนี้ราคาวิ่งไปแล้ว ${current_day_range:.2f} ({energy_pct}% ของ ADR) "
                "สถาบันได้ปล่อยของและทำกำไรคลื่นหลักไปแล้ว ในเวลาที่เหลือของวันตลาดมักจะชะลอตัว "
                "เข้าสู่การไซด์เวย์หรือสับขาหลอก แนะนำให้ระมัดระวังเป็นพิเศษ ไม่ไล่ราคา Follow Trend ไกลๆ"
            )
        elif is_meat_grinder:
            energy_level = "CHOPPY_CHURN"
            energy_color = "crimson"
            energy_desc = f"สะบัดฟันปลาล้างพลังงาน (วิ่งสะสม 4H ${active_gross_travel:.2f} หรือ {travel_ratio:.1f}x ของกรอบ) ห้ามเล่น Breakout/Pullback"
            session_type = "TYPE C: MEAT GRINDER (Energy Dissipation)"
            session_badge = "type-c"
            outlook_text = (
                f"ระวังกับดักสับขาหลอกรอบ {active_session_label}! ในรอบ 4 ชม. ล่าสุด ราคาวิ่งสะบัดไปถึง ${active_gross_travel:.2f} "
                f"({travel_ratio:.1f} เท่าของกรอบ 4H ${active_range:.2f}) สะท้อนว่าเกิดการปะทะและสะบัดฟันปลาหลายรอบ "
                f"ขณะที่ระยะสะสมทั้งวันอยู่ที่ ${daily_gross_travel:.2f} ({daily_travel_ratio:.1f}x) "
                "สภาพคล่องรอบนี้ถูกกวาดและพลังงานทิศทางเดียวถูกเผาผลาญทิ้ง ตลาดเป็นเครื่องบดเนื้อ แนะนำ Stand Down ถือเงินสด 100%"
            )
        elif energy_pct <= 55.0 and (bb_squeeze or atr_ratio <= 0.85 or (ker_label != "CHOPPY" and travel_ratio <= 1.8)):
            energy_level = "HIGH"
            energy_color = "green"
            energy_desc = f"พลังงานรอบ {active_session_label} สะสมแน่น (Spring-Loaded) สถาบันบีบอัดวอลุ่ม พร้อมระเบิดคลื่นใหญ่"
            session_type = "TYPE B (Compression / Spring-Loaded)"
            session_badge = "type-b"
            outlook_text = (
                f"ราคาวิ่งอัดอั้นในรอบ 4 ชม. ล่าสุดเพียง ${active_range:.2f} (วิ่งสะบัดเพียง ${active_gross_travel:.2f} หรือ {travel_ratio:.1f}x) "
                f"ขณะที่วันนี้เพิ่งใช้ ADR ไป {energy_pct}% (${current_day_range:.2f}/${adr14:.2f}) "
                f"แท่งเทียนบีบอัดตัวสะอาด (Clean Squeeze) สถาบันกำลังสะสมของรอระเบิดเทรนด์ (True Expansion) เข้าสู่รอบ {active_session_label} "
                "มีโอกาสวิ่งเป็นเทรนด์ทางเดียวคำโต แนะนำเตรียมพร้อมรอดักเทรด Breakout หรือ Pullback ตามเทรนด์"
            )
        elif eer >= 45.0 and ker >= 0.55 and energy_pct > 30.0:
            energy_level = "HIGH"
            energy_color = "blue"
            energy_desc = f"เทรนด์รอบ {active_session_label} วิ่งทางเดียวทรงพลัง (EER 4H {eer:.1f}% • สะบัดน้อย {travel_ratio:.1f}x)"
            session_type = "CLEAN EXPANSION DYNAMICS"
            session_badge = "type-clean"
            outlook_text = (
                f"การเคลื่อนไหวรอบ {active_session_label} วิ่งทิศทางสะอาดและมีประสิทธิภาพสูง (EER {eer:.1f}%, KER {ker:.2f}) "
                f"โดยใช้พลังงานวันไป ${current_day_range:.2f} ({energy_pct}% ของ ADR) และวิ่งรอบ 4H ไป ${active_gross_travel:.2f} "
                "แรงส่งจากสถาบันไหลเข้าต่อเนื่องตามเทรนด์หลัก สามารถหาจังหวะ Follow Trend ตามรอบการย่อตัว (Pullback) ได้อย่างมีแต้มต่อ"
            )
        else:
            energy_level = "MODERATE"
            energy_color = "orange"
            session_type = "NORMAL BALANCED DYNAMICS"
            session_badge = "type-normal"
            is_gw1 = 14.25 <= time_dec <= 16.5  # London Golden Window (14:15–16:30 น.)
            is_gw2 = 20.5  <= time_dec <= 22.5  # Wall Street Golden Window (20:30–22:30 น.)
            is_golden_window = is_gw1 or is_gw2

            if is_golden_window:
                energy_desc = f"ใช้พลังงานระดับปกติ (${current_day_range:.2f} หรือ {energy_pct}% ADR) — อยู่ในหน้าต่างเวลาทองคำ ({active_session_label}) สภาพคล่องสูง"
                outlook_text = (
                    f"การเคลื่อนไหวของวันอยู่ที่ ${current_day_range:.2f} ({energy_pct}% ของ ADR) โดยรอบ 4 ชม. ล่าสุดวิ่งสะสม ${active_gross_travel:.2f} ({travel_ratio:.1f}x) "
                    f"อยู่ในหน้าต่างเวลาทองคำ มีสภาพคล่องจากสถาบันหนาแน่นสำหรับการเทรดตามแนวรับแนวต้านสำคัญในรอบ {active_session_label}"
                )
            else:
                energy_desc = f"ใช้พลังงานระดับปกติ (${current_day_range:.2f} หรือ {energy_pct}% ADR) — นอกช่วงหน้าต่างเวลาทองคำ แนะนำรอรอบถัดไป"
                outlook_text = (
                    f"การเคลื่อนไหวของวันอยู่ที่ ${current_day_range:.2f} ({energy_pct}% ของ ADR) โดยรอบ 4 ชม. ล่าสุดวิ่งสะสม ${active_gross_travel:.2f} "
                    "โครงสร้างตลาดพักตัวนอกหน้าต่างเวลาทองคำ แนะนำให้ชะลอการเปิดสถานะใหม่ และรอจังหวะเทรดรอบตลาดลอนดอน (14:15) หรือนิวยอร์ก (20:30)"
                )

        # 8. Day Protocol
        if is_weekend:
            if is_saturday:
                day_protocol = "SATURDAY: Weekend Market Closed (ตลาดปิดทำการสุดสัปดาห์)"
                protocol_warning = "ตลาดทองคำปิดทำการช่วงวันหยุดสุดสัปดาห์ ไม่มีสภาพคล่องจากสถาบัน พักผ่อนและรอวางแผนเทรดรอบใหม่ช่วงตลาดเปิดเช้าวันจันทร์ (05:00-06:00 น.)"
            else:
                day_protocol = "SUNDAY: Weekend Market Closed (เตรียมตัวรับ Asian Open Gap เช้าวันจันทร์)"
                protocol_warning = "ตลาดปิดทำการ ระวังการเกิด Weekend Gap เมื่อตลาดเปิดเช้าวันจันทร์ (05:00-06:00 น.) ไม่แนะนำให้ถือ Position เสี่ยงข้ามสัปดาห์"
        elif is_friday:
            if hour >= 21 or energy_pct >= 65.0:
                day_protocol = "FRIDAY ALERT: Weekend De-risking Protocol (Max Cap 65%)"
                protocol_warning = "⚠️ วันศุกร์ชะลอการเทรด สถาบันเริ่มปิดสมุดบัญชีเพื่อไม่ถือข้ามสัปดาห์ สภาพคล่องจะกลวงและแกว่งมั่ว ไม่เคารพแนวรับต้าน แนะนำเคลียร์พอร์ตและถือเงินสด"
            else:
                day_protocol = "FRIDAY ACTIVE: Standard Institutional Trading (Pre-21:00, Max Cap 65%)"
                protocol_warning = "วันศุกร์รอบก่อน 21:00 น. ยังมีโวลุ่มปกติ แต่ควรกำหนดเป้ากำไรและเลิกเมื่อแตะ 65% ADR ไม่ถือออเดอร์ข้ามคืน"
        elif weekday == 0 and hour < 10:
            day_protocol = "MONDAY OPEN: Asian Session Kickoff & Gap Fill Monitoring"
            protocol_warning = "เปิดตลาดวันแรกของสัปดาห์ ระวังความผันผวนจากการเปิด Gap และการสะบัดสร้างกรอบสะสมของสถาบันช่วงเช้า"
        else:
            day_name = thai_now.strftime("%A")
            day_protocol = f"{day_name} REGULAR: Active Institutional Flow until 23:00 London Fix"
            protocol_warning = "วันทำการปกติ เงินทุนสถาบันยังคงเปิดสถานะข้ามคืนได้ (Overnight Carry) โวลุ่มไหลต่อเนื่องตาม Fund Flow สหรัฐฯ"

        is_restricted = is_weekend or (is_friday and (hour >= 21 or energy_pct >= 65.0))

        # Mini card details
        if travel_ratio <= 1.8:
            travel_desc = f"วิ่งตรง ไม่สะบัดวนลูป • สะสมทั้งวัน ${daily_gross_travel:.2f} ({daily_travel_ratio:.1f}x)"
        elif travel_ratio <= 2.5:
            travel_desc = f"แกว่งตามรอบสวิงปกติ • สะสมทั้งวัน ${daily_gross_travel:.2f} ({daily_travel_ratio:.1f}x)"
        else:
            travel_desc = f"สะบัดฟันปลา เผาผลาญพลังงานสูง • สะสมทั้งวัน ${daily_gross_travel:.2f} ({daily_travel_ratio:.1f}x)"

        if eer >= 50.0:
            flow_desc = "ทิศทางสะอาด ไหลลื่น"
            flow_badge = "CLEAN"
            flow_color = "green"
        elif eer >= 30.0:
            flow_desc = "สวิงสองทางตามกรอบ"
            flow_badge = "BALANCED"
            flow_color = "orange"
        else:
            flow_desc = "สับขาหลอก สภาพคล่องกลวง"
            flow_badge = "CHOPPY"
            flow_color = "crimson"

        if bb_squeeze:
            vol_desc = "แท่งเล็ก วอลุ่มแห้ง กำลังชาร์จพลัง"
            vol_badge = "SQUEEZE 🔋"
            vol_color = "green"
        elif atr_ratio >= 1.3 or vol_status in ["HIGH_VOLATILITY", "EXTREME_VOLATILITY"]:
            vol_desc = "ไส้ยาว กระชากแรง สภาพคล่องแปรปรวน"
            vol_badge = "EXPANDING ⚠️"
            vol_color = "crimson"
        else:
            vol_desc = "ความผันผวนอยู่ในเกณฑ์สมดุล"
            vol_badge = "BALANCED ⚖️"
            vol_color = "blue"

        return {
            "day_high": round(day_high, 2),
            "day_low": round(day_low, 2),
            "day_range": current_day_range,
            "adr14": adr14,
            "energy_used_pct": energy_pct,
            "energy_level": energy_level,
            "energy_color": energy_color,
            "energy_desc": energy_desc,
            "session_type": session_type,
            "session_badge": session_badge,
            "outlook_text": outlook_text,
            "day_protocol": day_protocol,
            "protocol_warning": protocol_warning,
            "is_friday": is_friday,
            "is_weekend": is_weekend,
            "friday_restricted": is_restricted,
            "friday_cap": 65.0,
            # Active 4-Hour / Session-Aware Engine Metrics
            "active_session": active_session_name,
            "active_session_label": active_session_label,
            "active_range": active_range,
            "gross_travel": active_gross_travel,
            "travel_ratio": travel_ratio,
            "travel_desc": travel_desc,
            "eer": eer,
            # All-day cumulative metrics for macro context
            "daily_gross_travel": daily_gross_travel,
            "daily_travel_ratio": daily_travel_ratio,
            # Regimes & Volatility
            "ker": round(ker, 2),
            "ker_label": ker_label,
            "flow_desc": flow_desc,
            "flow_badge": flow_badge,
            "flow_color": flow_color,
            "bb_squeeze": bb_squeeze,
            "atr_ratio": round(atr_ratio, 2),
            "vol_status": vol_status,
            "vol_desc": vol_desc,
            "vol_badge": vol_badge,
            "vol_color": vol_color,
        }

    # ─── Private Helpers: Trade Setup ─────────────────────────────────────────

    def _generate_trade_setup(
        self,
        current_price: float,
        mtf_regimes: Dict[str, Dict[str, Any]],
        setup_status: Dict[str, Any],
        asian_high: Optional[float],
        asian_low: Optional[float],
        london_high: Optional[float],
        london_low: Optional[float],
        sr_levels: List[Dict[str, Any]],
        energy_budget: Dict[str, Any],
        thai_now: datetime,
    ) -> Dict[str, Any]:
        """
        Determines Action, Setup Name, Entry Zone, SL, TP1, TP2, and R:R Ratio.
        """
        bias = (setup_status.get("bias") or "").upper()
        state = (setup_status.get("state") or "IDLE").upper()
        pattern = setup_status.get("price_action") or ""
        zones_hit = setup_status.get("zones_hit") or []
        step1_ok = setup_status.get("step1_ok", False)
        step2_ok = setup_status.get("step2_ok", False)
        step3_ok = setup_status.get("step3_ok", False)
        ema20 = setup_status.get("ema20") or current_price

        # Check Weekend Restriction
        if energy_budget.get("is_weekend", False):
            return {
                "action": "HOLD",
                "bias": "NEUTRAL",
                "badge_class": "weekend",
                "setup_name": "Weekend Market Closed — Strategy & Recap",
                "entry_zone": "ตลาดปิดทำการ (รอเปิดเช้าวันจันทร์)",
                "stop_loss": "—",
                "tp1": "—",
                "tp2": "—",
                "rr_ratio": "—",
                "confidence": 0,
            }

        # Check Friday Night Restriction
        if energy_budget.get("friday_restricted", False):
            return {
                "action": "HOLD",
                "bias": "NEUTRAL",
                "badge_class": "caution",
                "setup_name": "Friday Night Thin Liquidity — Cash is King",
                "entry_zone": "งดเข้าออเดอร์ใหม่ (Weekend De-risking)",
                "stop_loss": "—",
                "tp1": "—",
                "tp2": "—",
                "rr_ratio": "—",
                "confidence": 0,
            }

        energy_level = energy_budget.get("energy_level", "MODERATE")

        # Check Meat Grinder (TYPE C) — Route to Range Fade or Wait
        if energy_level == "CHOPPY_CHURN":
            return self._generate_range_fade_setup(
                current_price=current_price,
                asian_high=asian_high,
                asian_low=asian_low,
                london_high=london_high,
                london_low=london_low,
                energy_budget=energy_budget,
                thai_now=thai_now,
            )

        # Check ADR Exhaustion (TYPE A) Stand Down Rule
        if energy_level == "EXHAUSTED":
            return {
                "action": "HOLD",
                "bias": "NEUTRAL",
                "badge_class": "caution",
                "setup_name": "Type A: ADR Exhaustion Move — Profit Taking & De-risk",
                "entry_zone": "งด Follow Trend (เพดาน ADR เต็มแล้ว)",
                "stop_loss": "—",
                "tp1": "—",
                "tp2": "—",
                "rr_ratio": "—",
                "confidence": 15,
            }

        # Case 1: Active Alert (Step 3 Complete)
        if state == "ALERT" or (step1_ok and step2_ok and step3_ok):
            action = "BUY" if bias == "BULLISH" else "SELL"
            badge_class = "buy" if action == "BUY" else "sell"

            # Setup Name classification aligned with Master Trade Decision Matrix
            bb_squeeze = energy_budget.get("bb_squeeze", False)
            travel_ratio = float(energy_budget.get("travel_ratio", 2.0))
            energy_used = float(energy_budget.get("energy_used_pct", 50.0))

            if action == "BUY":
                if "ORDER_BLOCK" in zones_hit and "FLIP_ZONE" in zones_hit:
                    setup_name = "Institutional Confluence: OB + Flip Zone Demand Setup"
                elif "ORDER_BLOCK" in zones_hit:
                    setup_name = "Demand Zone: Bullish Order Block Reaction Setup"
                elif "FLIP_ZONE" in zones_hit:
                    setup_name = "S/R Flip: Old Resistance → New Support (Bullish Retest)"
                elif bb_squeeze and travel_ratio <= 1.8 and energy_used <= 45.0:
                    setup_name = "Type B: Spring Breakout Setup"
                elif london_low and abs(current_price - london_low) <= 6.0 and "ENGULFING" in pattern:
                    setup_name = "Liquidity Sweep: Bullish Reversal Setup (Bear Trap)"
                elif "EMA20" in zones_hit or "FVG" in zones_hit or step2_ok:
                    setup_name = "Clean Expansion: Bullish Pullback Setup"
                else:
                    setup_name = "Bullish Price Action Confirmation Setup"

                entry_low = round(current_price - 1.2, 2)
                entry_high = round(current_price + 0.8, 2)
                sl_price = round(current_price - 5.5, 2)
                tp1_price = round(current_price + 9.0, 2)
                tp2_price = round(current_price + 16.0, 2)

                # Anchor TP1 to London/Asian High if realistic
                if london_high and london_high > current_price + 3.0:
                    tp1_price = round(london_high - 1.0, 2)
                elif asian_high and asian_high > current_price + 3.0:
                    tp1_price = round(asian_high - 1.0, 2)

                risk = max(1.0, current_price - sl_price)
                reward1 = max(1.0, tp1_price - current_price)
                rr = round(reward1 / risk, 1)

            else:  # SELL
                if "ORDER_BLOCK" in zones_hit and "FLIP_ZONE" in zones_hit:
                    setup_name = "Institutional Confluence: OB + Flip Zone Supply Setup"
                elif "ORDER_BLOCK" in zones_hit:
                    setup_name = "Supply Zone: Bearish Order Block Reaction Setup"
                elif "FLIP_ZONE" in zones_hit:
                    setup_name = "S/R Flip: Old Support → New Resistance (Bearish Retest)"
                elif bb_squeeze and travel_ratio <= 1.8 and energy_used <= 45.0:
                    setup_name = "Type B: Spring Breakdown Setup"
                elif london_high and abs(current_price - london_high) <= 6.0 and "ENGULFING" in pattern:
                    setup_name = "Liquidity Sweep: Bearish Reversal Setup (Bull Trap)"
                elif "EMA20" in zones_hit or "FVG" in zones_hit or step2_ok:
                    setup_name = "Clean Expansion: Bearish Pullback Setup"
                else:
                    setup_name = "Bearish Price Action Breakdown Setup"

                entry_low = round(current_price - 0.8, 2)
                entry_high = round(current_price + 1.2, 2)
                sl_price = round(current_price + 5.5, 2)
                tp1_price = round(current_price - 9.0, 2)
                tp2_price = round(current_price - 16.0, 2)

                if london_low and london_low < current_price - 3.0:
                    tp1_price = round(london_low + 1.0, 2)
                elif asian_low and asian_low < current_price - 3.0:
                    tp1_price = round(asian_low + 1.0, 2)

                risk = max(1.0, sl_price - current_price)
                reward1 = max(1.0, current_price - tp1_price)
                rr = round(reward1 / risk, 1)

            return {
                "action": action,
                "bias": bias,
                "badge_class": badge_class,
                "setup_name": setup_name,
                "entry_zone": f"{entry_low:.2f} – {entry_high:.2f}",
                "stop_loss": f"{sl_price:.2f} (-${risk:.1f})",
                "tp1": f"{tp1_price:.2f} (+${reward1:.1f})",
                "tp2": f"{tp2_price:.2f}",
                "rr_ratio": f"1:{rr:.1f}",
                "confidence": setup_status.get("confidence_score", 75),
            }

        # Case 2: Step 2 (Pullback in progress)
        if step1_ok and step2_ok:
            action = "HOLD"
            badge_class = "pullback"
            setup_name = f"Waiting for {bias.capitalize()} Trigger (Pullback in Value Zone)"
            if bias == "BULLISH":
                target_zone = round(ema20, 2) if ema20 else round(current_price - 2.5, 2)
                entry_zone_str = f"โซนย่อ {target_zone - 1.5:.2f} – {target_zone + 1.0:.2f}"
                sl_est = f"ใต้โซนย่อ (~${target_zone - 5.0:.2f})"
                tp1_est = f"ยอดเดิม (~${current_price + 8.0:.2f})"
            else:
                target_zone = round(ema20, 2) if ema20 else round(current_price + 2.5, 2)
                entry_zone_str = f"โซนเด้ง {target_zone - 1.0:.2f} – {target_zone + 1.5:.2f}"
                sl_est = f"เหนือก้นเด้ง (~${target_zone + 5.0:.2f})"
                tp1_est = f"ก้นเดิม (~${current_price - 8.0:.2f})"

            return {
                "action": "HOLD",
                "bias": bias,
                "badge_class": badge_class,
                "setup_name": setup_name,
                "entry_zone": entry_zone_str,
                "stop_loss": sl_est,
                "tp1": tp1_est,
                "tp2": "Trailing Run",
                "rr_ratio": "1:2.0+",
                "confidence": 50,
            }

        # Case 3: Step 1 (Super Trend / Extended)
        if step1_ok:
            return {
                "action": "HOLD",
                "bias": bias,
                "badge_class": "waiting",
                "setup_name": f"Macro {bias.capitalize()} Extended — Wait for Pullback",
                "entry_zone": "ห้ามไล่ราคา รอ M1/M5 พักตัว",
                "stop_loss": "รอกำหนดใต้จุดย่อ",
                "tp1": "ตามแนวต้านสำคัญ",
                "tp2": "Runner Target",
                "rr_ratio": "—",
                "confidence": 35,
            }

        # Case 4: Idle / Ranging
        hour = thai_now.hour
        minute = thai_now.minute
        time_dec = hour + minute / 60.0
        is_gw1 = 14.25 <= time_dec <= 16.5  # London Golden Window (14:15–16:30 น.)
        is_gw2 = 20.5  <= time_dec <= 22.5  # Wall Street Golden Window (20:30–22:30 น.)
        is_golden_window = is_gw1 or is_gw2
        bb_squeeze = energy_budget.get("bb_squeeze", False)
        travel_ratio = float(energy_budget.get("travel_ratio", 2.0))

        if is_golden_window and bb_squeeze and travel_ratio <= 1.8:
            setup_name = "Type B: Spring Compression — Awaiting Breakout Trigger"
            entry_zone = "เฝ้าระวังแท่ง M5 ปิดทะลุกรอบ Session"
        elif not is_golden_window:
            setup_name = "Off-Session Consolidation — Awaiting Golden Window"
            entry_zone = "เฝ้าระวังกรอบ Session (รอเวลา 14:15 / 20:30 น.)"
        else:
            setup_name = "Market Consolidating / Awaiting Trigger"
            entry_zone = "เฝ้าระวังกรอบ Session"

        return {
            "action": "HOLD",
            "bias": "NEUTRAL",
            "badge_class": "neutral",
            "setup_name": setup_name,
            "entry_zone": entry_zone,
            "stop_loss": "—",
            "tp1": "—",
            "tp2": "—",
            "rr_ratio": "—",
            "confidence": 20,
        }

    # ─── Private Helpers: Range Fade Setup (Type C) ──────────────────────────

    def _generate_range_fade_setup(
        self,
        current_price: float,
        asian_high: Optional[float],
        asian_low: Optional[float],
        london_high: Optional[float],
        london_low: Optional[float],
        energy_budget: Dict[str, Any],
        thai_now: datetime,
    ) -> Dict[str, Any]:
        """
        When the market is in Meat Grinder (CHOPPY_CHURN), instead of a blanket
        HOLD, intelligently routes to:
          - SELL_FADE  : price near the top of the session range (fade rejection)
          - BUY_FADE   : price near the bottom of the session range (fade sweep)
          - HOLD/WAIT  : price in No Man's Land (middle of range) — wait for edge
        
        Near-edge threshold: price is within 25% of the range from either boundary.
        SL is placed $3–$5 beyond the swept boundary.
        TP1 targets the range midpoint; TP2 targets the opposite boundary.
        """
        gross_travel = energy_budget.get("gross_travel", 0.0)
        travel_ratio = energy_budget.get("travel_ratio", 1.0)

        # Resolve best available session boundaries (prefer London > Asian)
        ref_high = london_high if london_high else asian_high
        ref_low  = london_low  if london_low  else asian_low
        ref_label = "London" if london_high else "Asian"

        # ── Case A: No session levels defined → minimal WAIT guidance ────────
        if ref_high is None or ref_low is None:
            return {
                "action": "HOLD",
                "bias": "NEUTRAL",
                "badge_class": "caution",
                "setup_name": "Type C: Meat Grinder — Awaiting Session Range Lock",
                "entry_zone": "รอให้กรอบ Session ถูกล็อค (Asian High/Low) ก่อนประเมิน Fade Setup",
                "stop_loss": "—",
                "tp1": "—",
                "tp2": "—",
                "rr_ratio": "—",
                "confidence": 15,
                "strategy_mode": "RANGE_FADE",
            }

        session_range = max(ref_high - ref_low, 1.0)
        midpoint      = round((ref_high + ref_low) / 2.0, 2)

        # Near-edge = within 25% of session range from each boundary
        near_top_threshold    = ref_high - session_range * 0.25
        near_bottom_threshold = ref_low  + session_range * 0.25

        # SL buffer: scaled to ATR context, capped between $3–$6
        sl_buffer = round(min(6.0, max(3.0, session_range * 0.12)), 2)
        # TP buffer: leave $1 before the boundary (avoid spread into the wall)
        tp_buffer = 1.0

        # ── Case B: Price near TOP of range → SELL FADE ──────────────────────
        if current_price >= near_top_threshold:
            sl_price  = round(ref_high + sl_buffer, 2)
            tp1_price = round(midpoint + tp_buffer, 2)
            tp2_price = round(ref_low + tp_buffer, 2)
            entry_low  = round(current_price - 0.5, 2)
            entry_high = round(current_price + 1.5, 2)

            risk    = max(1.0, sl_price - current_price)
            reward1 = max(1.0, current_price - tp1_price)
            rr      = round(reward1 / risk, 1)

            # Time-context: add a stronger note during dangerous windows
            hour = thai_now.hour
            extra_note = " ⚠️ Pre-London Judas Window — Confirmation Candle Required" if 13 <= hour < 14 else ""

            return {
                "action": "SELL_FADE",
                "bias": "BEARISH",
                "badge_class": "sell",
                "setup_name": f"Type C: Range Fade — Sell Top of {ref_label} Range{extra_note}",
                "entry_zone": f"{entry_low:.2f} – {entry_high:.2f} (Rejection Zone ใกล้ {ref_label} High {ref_high:.2f})",
                "stop_loss": f"{sl_price:.2f} (-${risk:.1f}) เหนือ {ref_label} High",
                "tp1": f"{tp1_price:.2f} (+${reward1:.1f}) กึ่งกลางกรอบ",
                "tp2": f"{tp2_price:.2f} ขอบล่าง {ref_label} Low",
                "rr_ratio": f"1:{rr:.1f}",
                "confidence": 45,
                "strategy_mode": "RANGE_FADE",
                "fade_context": (
                    f"Meat Grinder: วิ่งสะสม ${gross_travel:.2f} ({travel_ratio:.1f}x กรอบ 4H) "
                    f"ราคาเข้าใกล้ขอบบน {ref_label} High ({ref_high:.2f}) "
                    f"รอแท่ง M5 ทิ้งไส้บนปฏิเสธราคา (Rejection Wick / Bearish Engulfing) แล้วค่อยเข้า Sell Fade"
                ),
            }

        # ── Case C: Price near BOTTOM of range → BUY FADE ────────────────────
        if current_price <= near_bottom_threshold:
            sl_price  = round(ref_low - sl_buffer, 2)
            tp1_price = round(midpoint - tp_buffer, 2)
            tp2_price = round(ref_high - tp_buffer, 2)
            entry_low  = round(current_price - 1.5, 2)
            entry_high = round(current_price + 0.5, 2)

            risk    = max(1.0, current_price - sl_price)
            reward1 = max(1.0, tp1_price - current_price)
            rr      = round(reward1 / risk, 1)

            hour = thai_now.hour
            extra_note = " ⚠️ Pre-London Judas Window — Confirmation Candle Required" if 13 <= hour < 14 else ""

            return {
                "action": "BUY_FADE",
                "bias": "BULLISH",
                "badge_class": "buy",
                "setup_name": f"Type C: Range Fade — Buy Bottom of {ref_label} Range{extra_note}",
                "entry_zone": f"{entry_low:.2f} – {entry_high:.2f} (Sweep Zone ใกล้ {ref_label} Low {ref_low:.2f})",
                "stop_loss": f"{sl_price:.2f} (-${risk:.1f}) ใต้ {ref_label} Low",
                "tp1": f"{tp1_price:.2f} (+${reward1:.1f}) กึ่งกลางกรอบ",
                "tp2": f"{tp2_price:.2f} ขอบบน {ref_label} High",
                "rr_ratio": f"1:{rr:.1f}",
                "confidence": 45,
                "strategy_mode": "RANGE_FADE",
                "fade_context": (
                    f"Meat Grinder: วิ่งสะสม ${gross_travel:.2f} ({travel_ratio:.1f}x กรอบ 4H) "
                    f"ราคาเข้าใกล้ขอบล่าง {ref_label} Low ({ref_low:.2f}) "
                    f"รอแท่ง M5 ทิ้งไส้ล่างปฏิเสธราคา (Long Lower Wick / Bullish Engulfing) แล้วค่อยเข้า Buy Fade"
                ),
            }

        # ── Case D: Price in middle of range → WAIT (No Man's Land) ──────────
        return {
            "action": "HOLD",
            "bias": "NEUTRAL",
            "badge_class": "caution",
            "setup_name": f"Type C: No Man's Land — Wait for {ref_label} Range Edge",
            "entry_zone": (
                f"ราคาอยู่กลางกรอบ (Midpoint: {midpoint:.2f}) "
                f"รอดักที่ขอบบน {ref_high:.2f} (Sell) หรือขอบล่าง {ref_low:.2f} (Buy)"
            ),
            "stop_loss": "—",
            "tp1": "—",
            "tp2": "—",
            "rr_ratio": "—",
            "confidence": 20,
            "strategy_mode": "RANGE_FADE",
            "fade_context": (
                f"Meat Grinder ตลาดวนอยู่กลางกรอบ [{ref_low:.2f} – {ref_high:.2f}] "
                f"ยังไม่มี Edge — ห้ามเข้ากลางกรอบ รอราคาวิ่งไปทดสอบขอบก่อนค่อยประเมิน Fade"
            ),
        }

    # ─── Private Helpers: Market Situation Narrative ─────────────────────────

    def _generate_market_narrative(
        self,
        current_price: float,
        mtf_regimes: Dict[str, Dict[str, Any]],
        setup_status: Dict[str, Any],
        trade_setup: Dict[str, Any],
        energy_budget: Dict[str, Any],
        asian_high: Optional[float],
        asian_low: Optional[float],
        london_high: Optional[float],
        london_low: Optional[float],
        thai_now: datetime,
    ) -> List[str]:
        """
        Generates tactical bullet points focusing purely on Price Action, Session S/R, Traps, and Rules.
        """
        narrative: List[str] = []
        bias = (setup_status.get("bias") or "NEUTRAL").upper()
        state = (setup_status.get("state") or "IDLE").upper()
        pattern = setup_status.get("price_action") or ""
        pattern_tf = setup_status.get("price_action_tf") or "M5"
        zones_hit = setup_status.get("zones_hit") or []
        hour = thai_now.hour
        is_weekend = energy_budget.get("is_weekend", False)
        weekday = thai_now.weekday()

        # 1. Structure & Session Context
        session_info = []
        if asian_high and asian_low:
            session_info.append(f"กรอบเอเชีย [{asian_low:.2f} – {asian_high:.2f}]")
        if london_high and london_low:
            session_info.append(f"กรอบลอนดอน [{london_low:.2f} – {london_high:.2f}]")

        session_str = " | ".join(session_info) if session_info else "ยังไม่มีการล็อคกรอบ Session ชัดเจน"
        session_prefix = "โครงสร้างรอบวันศุกร์ล่าสุด" if is_weekend else "โครงสร้างรอบวัน"
        narrative.append(f"{session_prefix}: {session_str}")

        # 2. Trap / Liquidity Sweep / Energy Trap Detection
        energy_lvl = energy_budget.get("energy_level", "")
        if is_weekend:
            narrative.append(f"ภาพรวมราคาปิดสัปดาห์: ทองคำปิดตลาดที่ระดับ ${current_price:.2f} สรุปกรอบเอเชีย-ลอนดอนวันศุกร์เพื่อใช้อ้างอิง S/R สัปดาห์หน้า")
        elif energy_lvl == "CHOPPY_CHURN":
            gt = energy_budget.get("gross_travel", 0.0)
            tr = energy_budget.get("travel_ratio", 1.0)
            action = trade_setup.get("action", "HOLD")
            strategy_mode = trade_setup.get("strategy_mode", "")
            fade_context  = trade_setup.get("fade_context", "")

            if strategy_mode == "RANGE_FADE" and action in ("SELL_FADE", "BUY_FADE"):
                direction = "Sell Fade (ขอบบน)" if action == "SELL_FADE" else "Buy Fade (ขอบล่าง)"
                narrative.append(
                    f"สภาวะตลาด Meat Grinder (4H วิ่งสะสม ${gt:.2f} / {tr:.1f}x กรอบ): "
                    f"ห้ามเล่น Breakout / Follow Trend — แต่มี Edge สำหรับกลยุทธ์ {direction} ที่ขอบกรอบ"
                )
                if fade_context:
                    narrative.append(f"คำแนะนำ Range Fade: {fade_context}")
            else:
                narrative.append(
                    f"คำเตือนพลังงาน: ตลาดอยู่ในสภาวะ Meat Grinder (รอบ 4H วิ่งสะสม ${gt:.2f} หรือ {tr:.1f}x ของกรอบ) "
                    f"ราคาอยู่กลางกรอบ (No Man's Land) — ห้ามเข้า รอดักขอบกรอบ Session ก่อน"
                )
        elif energy_lvl == "EXHAUSTED":
            ep = energy_budget.get("energy_used_pct", 0.0)
            narrative.append(f"คำเตือนพลังงาน: ราคาวิ่งใช้พลังงานไปแล้ว {ep}% ของ ADR ชนเพดานปลอดภัยของวัน ระวังการเทขายทำกำไรและ Reversal รุนแรง")
        elif london_low and current_price < london_low - 1.0:
            narrative.append(f"ราคาทุบหลุด London Low ({london_low:.2f}) ลงมา ➔ ระวัง False Breakdown หรือการสะบัดกวาด Stop Loss (Liquidity Sweep)")
        elif london_high and current_price > london_high + 1.0:
            narrative.append(f"ราคาพุ่งทะลุ London High ({london_high:.2f}) ขึ้นไป ➔ มีสิทธิ์เกิด Short Squeeze ระเบิดหรือ Bull Trap หากแท่งเทียนทิ้งไส้ยาว")
        elif asian_high and current_price >= asian_high - 1.5 and current_price <= asian_high + 2.0:
            narrative.append(f"ราคาเข้าใกล้ขอบบน Asian High ({asian_high:.2f}) ➔ เป็นโซนสภาพคล่องหนาแน่น จับตาดูอาการ Rejection หรือ Breakout Retest")
        elif asian_low and current_price <= asian_low + 1.5 and current_price >= asian_low - 2.0:
            narrative.append(f"ราคาเข้าใกล้ขอบล่าง Asian Low ({asian_low:.2f}) ➔ เป็นโซนสภาพคล่องหนาแน่นฝั่งล่าง เฝ้าระวังการเกิด Bear Trap")

        # 3. Candlestick Price Action Status
        if is_weekend:
            narrative.append("สภาวะแท่งเทียน: ตลาดปิดทำการ แท่งราคาหยุดนิ่ง รอแท่งเทียนเปิดสัปดาห์ใหม่สร้างรูปแบบราคาคอนเฟิร์ม")
        elif pattern:
            pat_clean = pattern.replace("_", " ").title()
            zones_str = " + ".join(zones_hit) if zones_hit else "Key Zone"
            # Highlight institutional zones with extra context
            zone_labels = []
            for z in zones_hit:
                if z == "ORDER_BLOCK":
                    ob = trade_setup.get("order_block") or setup_status.get("order_block")
                    if ob:
                        label = f"Demand OB [{ob['ob_low']:.2f}–{ob['ob_high']:.2f}]" if ob.get("type") == "DEMAND" else f"Supply OB [{ob['ob_low']:.2f}–{ob['ob_high']:.2f}]"
                    else:
                        label = "Order Block"
                    zone_labels.append(label)
                elif z == "FLIP_ZONE":
                    flip = trade_setup.get("flip_zone") or setup_status.get("flip_zone")
                    label = f"Flip Level [{flip:.2f}]" if flip else "S/R Flip Zone"
                    zone_labels.append(label)
                else:
                    zone_labels.append(z)
            zones_str = " + ".join(zone_labels) if zone_labels else "Key Zone"
            narrative.append(f"สัญญาณแท่งเทียน: เกิด {pat_clean} บนไทม์เฟรม {pattern_tf} บริเวณโซน {zones_str} ยืนยันแรงส่งฝั่ง {bias}")
        else:
            if state == "STEP2":
                narrative.append("สภาวะการย่อตัว: M1/M5 กำลังพักฐานลงหาแนวรับ (Discount Zone) ยังไม่มีแท่งเทียน Rejection ปิดคอนเฟิร์ม ให้นั่งทับมือรอ")
            elif state == "STEP1":
                narrative.append(f"สภาวะโมเมนตัม: H1/M15 เป็น {bias} ชัดเจน แต่แท่งราคา Overextended ห้ามกระโดด Follow Buy/Sell ที่ยอดเด็ดขาด")
            else:
                narrative.append("สภาวะราคา: แท่งเทียนไซด์เวย์อยู่ในกรอบ ไม่มีรูปแบบกลับตัวที่มีนัยสำคัญ")

        # 4. Golden Window / Tactical Execution Rule
        minute = thai_now.minute
        time_dec = hour + minute / 60.0
        if is_weekend:
            window_msg = "วันหยุดสุดสัปดาห์: ตลาดการเงินปิดทำการ ไม่มีหน้าต่างเวลาซื้อขาย พักผ่อนและเตรียมแผนเทรดสำหรับสัปดาห์ถัดไป"
        elif weekday == 0 and hour < 10:
            window_msg = "หน้าต่างเวลาเปิดสัปดาห์: Asian Open — เฝ้าระวังการเกิด Weekend Gap และการสะบัดสร้างกรอบราคาวันแรกของสัปดาห์"
        elif 14.25 <= time_dec <= 16.5:
            window_msg = "🌟 หน้าต่างเวลาทองคำ 1: London Golden Window (14:15–16:30 น.) — โฟกัส Setup คุณภาพสูงตามเทรนด์รอบบ่าย หรือ Retest Asian High/Low"
        elif 13.5 <= time_dec < 14.25:
            window_msg = "ช่วงเฝ้าระวัง Pre-London & Judas Swing (13:30–14:15 น.): ล็อคกรอบ Asian High/Low นั่งทับมือดูการสะบัดหลอก ไม่รีบเข้าก่อน 14:15 น."
        elif 20.5 <= time_dec <= 22.5:
            window_msg = "🌟 หน้าต่างเวลาทองคำ 2: Wall Street Golden Window (20:30–22:30 น.) — โฟกัสเทรดตาม Fund Flow ตลาดหุ้นสหรัฐฯ และ London/NY Overlap"
        elif 19.5 <= time_dec < 20.5:
            window_msg = "ช่วงอันตราย Pre-Wall Street & News Shakeout (19:30–20:30 น.): ข่าวสหรัฐฯ ออกและอัลกอริทึมสะบัดกิน SL สองทาง งดเข้าออเดอร์เด็ดขาด"
        elif 16.5 <= time_dec < 19.5:
            window_msg = "ช่วง London Lunch & ตลาดเปลี่ยนผ่าน (16:30–19:30 น.): โวลุ่มพักตัว สเปรดกว้าง พักผ่อนและรอรอบ Wall Street หลัง 20:30 น."
        elif 22.5 <= time_dec or time_dec < 5.0:
            window_msg = "ช่วงปิดรอบวัน (End of Day): สถาบันเริ่มปิดสมุดบัญชี เคลียร์พอร์ตว่าง ปิดจอและพักผ่อน ไม่มีออเดอร์ค้างข้ามคืน"
        else:
            window_msg = "ช่วง Asian Session (05:00–13:30 น.): ปล่อยให้ตลาดสร้างกรอบราคา ไม่เปิดออเดอร์ รอเตรียมตัวรอบบ่าย"
        narrative.append(f"กฎเวลาหน้างาน: {window_msg}")

        # 5. Golden Rule Action
        if is_weekend:
            narrative.append("คำเตือนทางวินัย: วันหยุดสุดสัปดาห์คือช่วงเวลาที่ดีที่สุดในการทบทวนบันทึกการเทรด (Trade Journal) ปิดจอและพักผ่อนเติมพลัง")
        elif energy_lvl == "CHOPPY_CHURN":
            action = trade_setup.get("action", "HOLD")
            strategy_mode = trade_setup.get("strategy_mode", "")
            if strategy_mode == "RANGE_FADE" and action in ("SELL_FADE", "BUY_FADE"):
                direction_th = "Sell Fade (ขอบบน)" if action == "SELL_FADE" else "Buy Fade (ขอบล่าง)"
                narrative.append(
                    f"กลยุทธ์ Range Fade: ห้ามเล่น Breakout/Follow Trend — "
                    f"แต่ให้ดัก {direction_th} โดยรอแท่ง M5 ยืนยัน Rejection ที่ขอบกรอบก่อน "
                    f"วาง SL สั้น ${trade_setup.get('stop_loss', '—')} TP1: {trade_setup.get('tp1', '—')} "
                    f"ห้ามย้าย SL เด็ดขาด"
                )
            else:
                narrative.append(
                    "คำเตือนทางวินัย: ราคาอยู่กลางกรอบ Meat Grinder ไม่มี Edge ชัดเจน "
                    "การนั่งทับมือรอดักขอบกรอบ คือการรักษา Capital ของมืออาชีพ"
                )
        elif energy_lvl == "EXHAUSTED":
            narrative.append("คำเตือนทางวินัย: เมื่อราคาชนเพดานพลังงาน ADR การล็อคกำไรและถือเงินสด คือการปกป้องกำไรที่ปลอดภัยที่สุด")
        elif trade_setup.get("action") in ["BUY", "SELL"]:
            narrative.append(f"กลยุทธ์เข้าทำ: รอให้ราคาเข้าโซน {trade_setup.get('entry_zone')} วาง Stop Loss ตามระบบ {trade_setup.get('stop_loss')} ห้ามเลื่อน SL หนีเด็ดขาด")
        else:
            narrative.append("คำเตือนทางวินัย: การนั่งทับมือและถือเงินสด (Cash) ในจังหวะที่แต้มต่อยังไม่ชัดเจน คือการเทรดของมืออาชีพ")

        return narrative


# ─── Singleton Factory ────────────────────────────────────────────────────────

_advisor_instance: Optional[ProfessionalAdvisor] = None


def get_professional_advisor() -> ProfessionalAdvisor:
    global _advisor_instance
    if _advisor_instance is None:
        _advisor_instance = ProfessionalAdvisor()
    return _advisor_instance
