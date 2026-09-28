# 🏆 AI Gold Scalper — Price Action Sniper Dashboard (v2.0)

> **"AI เป็นเรดาร์คัดกรองทิศทาง — คุณเป็นสไนเปอร์ Price Action"**  
> *(AI Directional Radar & Choppy Filter + Human Price Action Sniper)*

---

## 📖 สารบัญเอกสารคู่มือ (Documentation)
* 📘 **[คู่มือการใช้งานและการตีความผลฉบับสมบูรณ์ (User Manual)](USER_GUIDE_AND_INTERPRETATION.md)**: อธิบายการทำงานของระบบทุกส่วน, การอ่าน Edge Score, KER, Falling Knife Alert, และ Action Plan สำหรับ Day Trader (M1/M5 entry, H1/H4 context)
* 🛠️ **[คู่มือการติดตั้งและย้ายเครื่อง (Installation Guide)](INSTALLATION_GUIDE.md)**: แนะนำขั้นตอนการติดตั้ง Python, การตั้งค่า MT5, และการย้ายโฟลเดอร์ไปใช้งานเครื่องใหม่
* 📑 **[รายงานการวิเคราะห์โมเดลเชิงลึก (Ensemble Analysis Report)](ensemble_analysis_report.html)**: วิเคราะห์โครงสร้าง 9+ Ensemble Models และกลยุทธ์กรอง Choppy Market (สามารถเปิดดูผ่านเบราว์เซอร์ที่ `http://127.0.0.1:5000/report`)

---

## ⚡ วิธีเริ่มต้นใช้งานแบบด่วน (Quick Start)
1. เปิดโปรแกรม **MetaTrader 5 (MT5)** และล็อกอินบัญชีเทรด
2. เปิดใช้งาน **Algo Trading** ใน MT5 (`Tools` $\rightarrow$ `Options` $\rightarrow$ `Expert Advisors` $\rightarrow$ ติ๊ก `Allow Algo Trading`)
3. ดับเบิลคลิกไฟล์ **`start_dashboard.bat`**
4. เปิดเบราว์เซอร์ไปที่: **`http://127.0.0.1:5000`**
5. ตรวจสอบชื่อคู่ทองคำในช่อง **Gold Symbol** (เช่น `XAUUSD.iux`) แล้วกด **Apply**

---

## 🚀 คุณสมบัติเด่นของเวอร์ชัน 2.0 (Key Features)
1. **🛰️ AI Radar Sniper Panel:**
   * **Directional Bias:** สรุปทิศทางตลาดเอกฉันท์ (Bullish / Bearish / Neutral) โดยมีแกนหลักคือ Intraday Trend (H1 + M15)
   * **Edge Score (0 - 100):** มาตรวัดแต้มต่อทางสถิติ (High Edge $\ge 70$, Moderate $45-69$, Low/Choppy $< 45$)
   * **Kaufman Efficiency Ratio (KER):** ตรวจจับความสะอาดของเทรนด์บน H1 & M15 ($\ge 0.60$ Trending, $< 0.30$ Choppy)
   * **MTF Stack Pills:** ยืนยันทิศทาง H1, M15, M5, M1 ด้วยสายตาทันที
   * **🛑 NO TRADE ZONE Banner:** แจ้งเตือนหยุดเทรดอัตโนมัติเมื่อตลาดเข้าสู่สภาวะ Choppy
2. **🔪 Anti-Falling Knife & Anti-Rising Knife Protection:**
   * ตรวจจับโมเมนตัมเทขายหรือไล่ราคาที่รุนแรงผิดปกติ บล็อกการเปิดคำสั่งสวนเทรนด์โดยสิ้นเชิง
3. **🎯 Interactive Timeframe Selector บนการ์ด Executive Decision:**
   * ย้ายตัวเลือก Base Timeframe มาไว้ที่หัวการ์ด Executive Decision โดยตรง (`[ TF: M5 ▾ ]`) เพื่อให้สลับ Timeframe การคำนวณของ AI 9+ โมเดลได้ตรงจุด (M1, M5, M15, H1, H4, D1)
4. **🔔 Unified Smart Alert System & Sound Control:**
   * **Single Alert Rule:** แสดงผลชัดเจนในหน้าต่างเดียว ไม่เปิดซ้อนทับกัน
   * **🎯 Sniper Re-Alignment Alert:** แจ้งเตือนเมื่อ Directional Bias และ Executive Decision สอดคล้องกัน (จังหวะจบ Pullback พร้อมเข้าทำ)
   * **⚠️ Significant Pullback Alert:** แจ้งเตือนเมื่อตรวจพบการย่อตัวลึกสวนเทรนด์ใหญ่ (ห้ามไล่ราคา ให้รอรับที่ Key Support/Resistance)
   * **📊 MTF Consensus Alert:** แจ้งเตือนเมื่อ H1, M15, M5, M1 วิ่งไปในทิศทางเดียวกันพร้อมกัน
   * **🔊 Sound ON / OFF Toggle:** ปุ่มควบคุมเปิด/ปิดเสียงเตือนสังเคราะห์ (Web Audio API) พร้อมระบบจำสถานะอัตโนมัติผ่าน `localStorage`
5. **🏛️ Day Trading 3-Tier Architecture:**
   * **Tier 1 (D1/H4):** Macro Context & Key S/R Wall
   * **Tier 2 (H1/M15):** Intraday Directional Bias & KER Quality
   * **Tier 3 (M5/M1):** Price Action Execution Trigger & Pullback Entry
6. **🎯 MTF 3-Step Setup Tracker & Browser Push Notification:**
   * **State Machine Tracking:** ติดตามกระบวนการเทรดแบบเป็นขั้นตอนอัตโนมัติ (Step 1 Trend Confluence $\rightarrow$ Step 2 Pullback $\rightarrow$ Step 3 Price Action & Confluence Zone)
   * **Zone Scoring:** ให้คะแนนความแม่นยำร่วมของจุดเข้าเทรดด้วย EMA 20, Fair Value Gap (FVG), และ Swing High/Low
   * **Browser Push Notification 🔔:** ยิงแจ้งเตือนเด้งเตือนบน Desktop/เบราว์เซอร์ทันทีเมื่อเงื่อนไขครบถ้วน (Confidence $\ge 60\%$) แม้จะพับหน้าจออยู่
7. **🏛️ Professional Advice & Institutional Energy Budget (v2.5):**
   * **Top Executive Action Card:** คำนวณ Action (Buy/Sell/Hold), Tactical Setup Name, Entry Zone, SL, TP1, TP2, R:R และ Confidence พร้อมระบบ Absolute Stand-Down บล็อกการเทรดอัตโนมัติในสภาวะ Meat Grinder และ ADR Exhaustion
   * **Section 1 Price Action Narrative:** ล็อคกรอบ Session S/R (Asian/London High/Low), Smart Money Order Blocks ทิศทางถูกต้อง (Demand ต่ำกว่าราคา, Supply สูงกว่าราคา), และกฎเวลาหน้างาน Golden Windows (13:30 Pre-London, 14:15 GW1, 20:30 GW2)
   * **Section 2 Dual-Layer Rolling 4-Hour Energy Engine:** แยกเพดานถังน้ำมัน Macro Daily ADR ออกจากเครื่องยนต์รอบปัจจุบัน Active 4H Gross Travel (16 แท่ง M15) ตัดปัญหา Asian Churn Misleading ถาวร พร้อมวัด EER, KER และ Volatility Squeeze (Spring-Loaded) ก่อนเปิดตลาดรอบบ่ายและรอบค่ำ
