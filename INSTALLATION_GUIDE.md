# 🛠️ คู่มือการติดตั้งและย้ายเครื่อง: AI Gold Scalper Web Dashboard
*(AI Gold Scalper Web Dashboard — Installation & Deployment Guide)*

เอกสารนี้อธิบายขั้นตอนการติดตั้ง การตั้งค่าระบบ และการย้ายโฟลเดอร์ Web Dashboard ไปใช้งานบนเครื่องคอมพิวเตอร์เครื่องใหม่ (Portable Deployment) อย่างเป็นขั้นเป็นตอน

---

## 📋 1. ความต้องการของระบบ (System Requirements)

ก่อนเริ่มใช้งาน ตรวจสอบว่าเครื่องคอมพิวเตอร์ (Windows 10 หรือ 11) มีสิ่งเหล่านี้พร้อม:

| รายการ | รายละเอียดที่ต้องการ |
| :--- | :--- |
| **ระบบปฏิบัติการ** | Windows 10 หรือ Windows 11 (64-bit) |
| **Python** | เวอร์ชัน **3.10 ขึ้นไป** (แนะนำ 3.11 หรือ 3.12 หรือ 3.13) |
| **MetaTrader 5 (MT5)** | ติดตั้งโปรแกรม MT5 ของโบรกเกอร์ใดก็ได้ (เช่น IUX Markets, Exness, XM ฯลฯ) |
| **บัญชีเทรด** | บัญชี Demo หรือ Real ที่ Login ใน MT5 เรียบร้อยแล้ว |
| **อินเทอร์เน็ต** | เชื่อมต่ออินเทอร์เน็ตสำหรับดึงข้อมูลราคา Real-time |

> [!IMPORTANT]
> **สำคัญมากตอนติดตั้ง Python:**  
> ในหน้าต่างแรกของตัวติดตั้ง Python ให้ติ๊กเครื่องหมายถูกที่ช่อง **☑ Add python.exe to PATH** ก่อนกด Install Now เสมอ หากไม่ได้ติ๊ก คำสั่ง `python` ใน Command Prompt จะไม่ทำงาน

---

## ⚙️ 2. การตั้งค่าบนโปรแกรม MetaTrader 5 (MT5)

เพื่อให้สคริปต์ Python สามารถเชื่อมต่อและดึงข้อมูลราคาจาก MT5 ได้อย่างสมบูรณ์ ให้ตั้งค่าดังนี้:

1. **เปิดโปรแกรม MetaTrader 5** และ Login บัญชีเทรด
2. **เปิดสิทธิ์ Algo Trading:**
   * ไปที่เมนูบาร์ด้านบน: `Tools` $\rightarrow$ `Options` (หรือกด `Ctrl + O`)
   * คลิกที่แท็บ **Expert Advisors**
   * ติ๊กเครื่องหมายถูกที่ช่อง **☑ Allow Algo Trading**
   * ติ๊กเครื่องหมายถูกที่ช่อง **☑ Allow DLL imports**
   * กดปุ่ม **OK**
3. **เปิดแสดงคู่เงินทองคำใน Market Watch:**
   * กด `Ctrl + M` เพื่อเปิดหน้าต่าง **Market Watch**
   * ตรวจสอบว่ามีคู่ทองคำเปิดแสดงอยู่ เช่น `XAUUSD.iux`, `XAUUSD`, `GOLD`, หรือ `XAUUSDm` (หากยังไม่มี ให้พิมพ์ค้นหาในช่อง `+ click to add...` แล้วกด Enter)

---

## 🚀 3. ขั้นตอนการติดตั้งบนเครื่องใหม่ (First-Time Setup)

โฟลเดอร์นี้ถูกออกแบบให้เป็น **Self-Contained & Portable** (ไม่ยึดติดกับ Drive หรือ Path ใดๆ สามารถวางบน Desktop หรือไดรฟ์ C:, D: ได้ทันที)

### ขั้นตอนที่ 1: ก๊อปปี้โฟลเดอร์
ก๊อปปี้ทั้งโฟลเดอร์ `AI-Gold-Scalper-Dashboard` ไปวางในตำแหน่งที่ต้องการบนเครื่องใหม่ เช่น:
* `C:\web-apps\AI-Gold-Scalper-Dashboard\` หรือ
* `D:\AI-Gold-Scalper-Dashboard\` หรือ
* วางไว้บนหน้าจอ `Desktop`

### ขั้นตอนที่ 2: ติดตั้ง Python Libraries (ทำเฉพาะครั้งแรก)
1. เข้าไปในโฟลเดอร์ `AI-Gold-Scalper-Dashboard`
2. ดับเบิลคลิกไฟล์ **`install_requirements.bat`**
3. ระบบจะทำการติดตั้งแพ็กเกจที่จำเป็นอัตโนมัติ ได้แก่:
   * `MetaTrader5` (API เชื่อมต่อ MT5)
   * `Flask` (Web Framework)
   * `pandas` & `numpy` (การคำนวณสถิติและข้อมูลราคา)
   * `scikit-learn` (โมเดล Machine Learning 9 อัลกอริทึม)
4. เมื่อติดตั้งเสร็จสิ้น จะมีข้อความแจ้งว่า *"Installation Complete!"* ให้กดปุ่มใดก็ได้เพื่อปิดหน้าต่าง

### ขั้นตอนที่ 3: เปิดใช้งาน Web Dashboard
1. ตรวจสอบว่าโปรแกรม **MT5 กำลังเปิดทำงานอยู่**
2. ดับเบิลคลิกไฟล์ **`start_dashboard.bat`**
3. หน้าต่าง Command Prompt สีดำจะเริ่มทำงาน และเปิดหน้าต่าง Web Browser ไปที่:
   $$\mathbf{http://127.0.0.1:5000}$$
4. หน้าจอ Dashboard จะเชื่อมต่อ MT5 ดึงข้อมูล และแสดงผลการวิเคราะห์ให้ทันที

---

## 📁 4. โครงสร้างไฟล์ในโฟลเดอร์ (Folder Structure)

```text
AI-Gold-Scalper-Dashboard/
│
├── core/                               # เครื่องมือหลักของระบบ
│   ├── mt5_fetcher.py                  # เชื่อมต่อ MT5, คำนวณ Timezone และบันทึก CSV
│   ├── ai_engine.py                    # ตรวจจับ Market Regime & รันโมเดล ML 9 ตัว
│   └── scheduler.py                    # ตัวจัดการรอบเวลาอัตโนมัติตามเข็มนาฬิกา
│
├── exportedpricedata/                  # โฟลเดอร์เก็บไฟล์ราคา CSV (Overwrite อัตโนมัติ)
│   ├── XAUUSD_D1.csv
│   ├── XAUUSD_H4.csv
│   ├── XAUUSD_H1.csv
│   ├── XAUUSD_M15.csv
│   ├── XAUUSD_M5.csv
│   └── XAUUSD_M1.csv
│
├── static/                             # ไฟล์ส่วนหน้าของ Web Dashboard
│   ├── css/style.css                   # ดีไซน์ Dark Gold & Cyan Glassmorphism
│   └── js/app.js                       # จัดการ Real-time Polling และปุ่มกด
│
├── templates/
│   └── index.html                      # โครงสร้างหน้าเว็บ Dashboard
│
├── config.json                         # ค่าการตั้งค่าที่จำไว้ (Symbol, Interval, Auto-update)
├── requirements.txt                    # รายการไลบรารี Python
├── install_requirements.bat            # สคริปต์คลิกเดียวติดตั้งไลบรารี
├── start_dashboard.bat                 # สคริปต์คลิกเดียวเปิด Web Dashboard
├── INSTALLATION_GUIDE.md               # คู่มือการติดตั้งและย้ายเครื่อง (เอกสารนี้)
└── USER_GUIDE_AND_INTERPRETATION.md    # คู่มือการใช้งานและตีความผลลัพธ์
```

---

## ❓ 5. การแก้ไขปัญหาที่พบบ่อย (Troubleshooting)

### Q1: ดับเบิลคลิก `start_dashboard.bat` แล้วหน้าต่างปิดตัวเองทันที หรือขึ้นว่า `'python' is not recognized`
* **สาเหตุ:** ไม่ได้ติ๊ก Add Python to PATH ตอนติดตั้ง Python
* **วิธีแก้:** ดาวน์โหลดตัวติดตั้ง Python มาใหม่ กด Install แล้วติ๊กถูกที่ช่อง **☑ Add python.exe to PATH** จากนั้น Restart เครื่อง 1 ครั้ง

### Q2: หน้าเว็บขึ้นแถบเตือนสีแดง "MT5 initialize failed"
* **สาเหตุ:** MT5 ยังไม่ได้เปิด หรือยังไม่ได้ Login บัญชีเทรด
* **วิธีแก้:** เปิดโปรแกรม MT5 เข้าสู่ระบบบัญชีเทรดให้เรียบร้อยก่อน แล้วกดปุ่ม **⚡ Fetch & Analyze Now** บนหน้าเว็บใหม่อีกครั้ง

### Q3: หน้าเว็บขึ้นเตือน "Symbol XAUUSD... not found in Market Watch"
* **สาเหตุ:** แต่ละโบรกเกอร์ใช้ชื่อคู่ทองคำแตกต่างกัน (เช่น IUX ใช้ `XAUUSD.iux`, Exness ใช้ `XAUUSDm`)
* **วิธีแก้:** ดูชื่อทองคำในหน้าต่าง Market Watch ของ MT5 จากนั้นนำชื่อนั้นมาพิมพ์ลงในช่อง **Gold Symbol** บนหน้าเว็บ แล้วกดปุ่ม **Apply**

### Q4: พอร์ต 5000 ถูกใช้งานอยู่แล้ว (Port 5000 in use)
* **สาเหตุ:** มีหน้าต่าง Dashboard เก่าเปิดค้างอยู่
* **วิธีแก้:** ปิดหน้าต่าง Command Prompt เดิมที่เปิดอยู่ทั้งหมด หากยังไม่หาย ให้เปิด Task Manager (Ctrl + Shift + Esc) ค้นหา `python.exe` แล้วกด End Task จากนั้นรัน `start_dashboard.bat` ใหม่อีกครั้ง
