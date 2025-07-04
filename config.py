import os
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime

# Environment Variables
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
GOOGLE_SHEETS_CREDENTIALS = os.getenv("GOOGLE_SHEETS_CREDENTIALS")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
ADMIN_USER_ID = os.getenv("ADMIN_USER_ID")
ADMIN_GROUP_ID = os.getenv("ADMIN_GROUP_ID")

# App Configuration
APP_TITLE = os.getenv("APP_TITLE", "LINE Bot Restaurant Booking")
APP_VERSION = os.getenv("APP_VERSION", "1.0.0")

# LINE Headers
LINE_HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
}

# ======================= LOGGING CONFIGURATION =======================

def setup_logging():
    """ตั้งค่า logging สำหรับระบบ"""
    
    # สร้างโฟลเดอร์ logs ถ้าไม่มี
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # กำหนดระดับ log จาก environment variable (default: INFO)
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    
    # สร้าง logger หลัก
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, log_level, logging.INFO))
    
    # ลบ handlers เดิมทั้งหมด (ป้องกันการซ้ำ)
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # === Format สำหรับ log ===
    formatter = logging.Formatter(
        '%(asctime)s | %(name)s | %(levelname)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # === 1. Console Handler (แสดงบน terminal) ===
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # === 2. General Log File (ทุกอย่าง) ===
    general_handler = RotatingFileHandler(
        filename=f"{log_dir}/app.log",
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,  # เก็บไฟล์ย้อนหลัง 5 ไฟล์
        encoding='utf-8'
    )
    general_handler.setLevel(logging.DEBUG)
    general_handler.setFormatter(formatter)
    logger.addHandler(general_handler)
    
    # === 3. Error Log File (เฉพาะ Error) ===
    error_handler = RotatingFileHandler(
        filename=f"{log_dir}/error.log",
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    logger.addHandler(error_handler)
    
    # === 4. Booking Log File (เฉพาะการจอง) ===
    booking_handler = RotatingFileHandler(
        filename=f"{log_dir}/booking.log",
        maxBytes=5*1024*1024,  # 5MB
        backupCount=10,
        encoding='utf-8'
    )
    booking_handler.setLevel(logging.INFO)
    booking_formatter = logging.Formatter(
        '%(asctime)s | BOOKING | %(levelname)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    booking_handler.setFormatter(booking_formatter)
    
    # สร้าง logger เฉพาะสำหรับ booking
    booking_logger = logging.getLogger('booking')
    booking_logger.setLevel(logging.INFO)
    booking_logger.addHandler(booking_handler)
    booking_logger.propagate = False  # ไม่ให้ส่งต่อไป parent logger
    
    # === 5. Webhook Log File (เฉพาะ webhook requests) ===
    webhook_handler = RotatingFileHandler(
        filename=f"{log_dir}/webhook.log",
        maxBytes=10*1024*1024,  # 10MB
        backupCount=3,
        encoding='utf-8'
    )
    webhook_handler.setLevel(logging.INFO)
    webhook_formatter = logging.Formatter(
        '%(asctime)s | WEBHOOK | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    webhook_handler.setFormatter(webhook_formatter)
    
    # สร้าง logger เฉพาะสำหรับ webhook
    webhook_logger = logging.getLogger('webhook')
    webhook_logger.setLevel(logging.INFO)
    webhook_logger.addHandler(webhook_handler)
    webhook_logger.propagate = False
    
    print(f"✅ Logging setup completed - Level: {log_level}")
    print(f"📁 Log directory: {os.path.abspath(log_dir)}")
    
    return logger

# === Custom Log Functions ===
def log_booking_event(event_type: str, user_id: str, user_name: str, details: dict = None):
    """บันทึก log เฉพาะเหตุการณ์การจอง"""
    booking_logger = logging.getLogger('booking')
    
    log_data = {
        "event": event_type,
        "user_id": user_id,
        "user_name": user_name,
        "timestamp": datetime.now().isoformat()
    }
    
    if details:
        log_data.update(details)
    
    # แปลงเป็น string ที่อ่านง่าย
    log_message = f"{event_type} | User: {user_name} ({user_id})"
    if details:
        detail_str = " | ".join([f"{k}: {v}" for k, v in details.items()])
        log_message += f" | {detail_str}"
    
    booking_logger.info(log_message)

def log_webhook_request(method: str, headers: dict, body: dict, response_status: int = None):
    """บันทึก log เฉพาะ webhook requests"""
    webhook_logger = logging.getLogger('webhook')
    
    # ซ่อนข้อมูลสำคัญ
    safe_headers = {k: v for k, v in headers.items() if k.lower() not in ['authorization', 'x-line-signature']}
    if 'authorization' in headers:
        safe_headers['authorization'] = 'Bearer ***HIDDEN***'
    if 'x-line-signature' in headers:
        safe_headers['x-line-signature'] = '***HIDDEN***'
    
    log_message = f"{method} Request"
    if response_status:
        log_message += f" | Status: {response_status}"
    
    webhook_logger.info(f"{log_message} | Headers: {safe_headers}")
    webhook_logger.info(f"Body: {body}")

def log_error_with_context(error: Exception, context: str, user_id: str = None, additional_data: dict = None):
    """บันทึก error พร้อม context"""
    logger = logging.getLogger(__name__)
    
    error_details = {
        "error_type": type(error).__name__,
        "error_message": str(error),
        "context": context
    }
    
    if user_id:
        error_details["user_id"] = user_id
    
    if additional_data:
        error_details.update(additional_data)
    
    logger.error(f"ERROR in {context}: {error_details}", exc_info=True)

# เรียกใช้ setup logging เมื่อ import module นี้
setup_logging()