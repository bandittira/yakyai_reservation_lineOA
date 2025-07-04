# 🏮 ร้านยักษ์ใหญ่แดนใต้ - Restaurant Booking System

ระบบจองโต๊ะร้านอาหารผ่าน LINE Bot พร้อมระบบ ID การจองและ Google Sheets Integration

## 📁 Project Structure

```
restaurant-booking/
├── main.py                 # Main FastAPI application
├── config.py              # Configuration settings
├── models.py              # Pydantic data models
├── utils.py               # Utility functions
├── google_sheets.py       # Google Sheets integration
├── flex_messages.py       # LINE Flex Message templates
├── session_manager.py     # Session management
├── requirements.txt       # Python dependencies
├── .env                   # Environment variables (create this)
└── README.md             # This file
```

## 🚀 Features

### ✨ Main Features
- **ID การจอง**: ระบบสร้าง ID แบบ `YGxxxx` อัตโนมัติ
- **Google Sheets**: บันทึกข้อมูลแยกตามวัน
- **LINE Flex Messages**: UI สวยงามสำหรับการจอง
- **Session Management**: จัดการขั้นตอนการจองแบบ Step-by-Step
- **การยกเลิกการจอง**: ค้นหาและยกเลิกได้ง่าย

### 📊 Google Sheets Structure
```
ID การจอง | เวลาจอง | ชื่อลูกค้า | เบอร์โทร | วันที่ | เวลา | จำนวนคน | คำขอเพิ่มเติม | LINE DISPLAY NAME | สถานะ
```

## 🛠 Installation

### 1. Clone Repository
```bash
git clone <repository-url>
cd restaurant-booking
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Environment Variables
สร้างไฟล์ `.env`:
```env
LINE_CHANNEL_SECRET=your_line_channel_secret
LINE_CHANNEL_ACCESS_TOKEN=your_line_access_token
GOOGLE_CREDENTIALS_FILE=credentials.json
GOOGLE_DRIVE_FOLDER_ID=your_drive_folder_id
SHARE_EMAIL=email@example.com
```

### 4. Google Credentials
- สร้าง Service Account ใน Google Cloud Console
- Download `credentials.json` ใส่ในโฟลเดอร์โปรเจค
- เปิดใช้ Google Sheets API และ Google Drive API

### 5. Run Application
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## 📱 Usage

### การจองโต๊ะ
1. ส่งข้อความ "จองโต๊ะ" ใน LINE
2. ระบุชื่อผู้จอง
3. ระบุเบอร์โทร
4. เลือกวันที่จาก Flex Message
5. เลือกเวลาจาก Flex Message
6. ระบุจำนวนคน
7. ระบุคำขอเพิ่มเติม (ถ้ามี)
8. ได้รับ ID การจองพร้อมการยืนยัน

### การยกเลิกการจอง
1. ส่งข้อความ "ยกเลิกการจอง"
2. ระบุเบอร์โทรที่ใช้จอง
3. เลือกการจองที่ต้องการยกเลิก

## 🎯 API Endpoints

### POST /webhook
รับ webhook จาก LINE Bot
