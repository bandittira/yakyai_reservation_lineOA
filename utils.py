import hashlib
import hmac
import base64
import re
import requests
import logging
from typing import Dict, Optional, Any
from datetime import datetime

from config import LINE_CHANNEL_SECRET, LINE_HEADERS

logger = logging.getLogger(__name__)

def verify_line_signature(body: bytes, signature: str) -> bool:
    """ตรวจสอบ signature จาก LINE webhook"""
    try:
        if not LINE_CHANNEL_SECRET:
            logger.error("LINE_CHANNEL_SECRET not configured")
            return False
            
        hash_digest = hmac.new(
            LINE_CHANNEL_SECRET.encode('utf-8'),
            body,
            hashlib.sha256
        ).digest()
        
        expected_signature = base64.b64encode(hash_digest).decode('utf-8')
        return hmac.compare_digest(signature, expected_signature)
        
    except Exception as e:
        logger.error(f"Error verifying LINE signature: {e}")
        return False

def is_inquiry_message(message: str) -> bool:
    """ตรวจสอบว่าเป็นข้อความขอจองโต๊ะหรือไม่"""
    inquiry_keywords = [
        "จอง", "ขอจอง", "จองโต๊ะ", "book", "booking", "reserve", "reservation",
        "ขอวิธีจอง", "วิธีการจอง", "วิธีจอง", "จองยังไง", "จองได้ไหม"
    ]
    message_lower = message.lower().strip()
    return any(keyword in message_lower for keyword in inquiry_keywords)

def is_cancel_message(message: str) -> bool:
    """ตรวจสอบว่าเป็นข้อความขอยกเลิกการจองหรือไม่"""
    cancel_keywords = [
        "ยกเลิก", "ยกเลิกการจอง", "cancel", "cancellation", 
        "ลบการจอง", "ไม่เอาแล้ว", "ขอยกเลิก"
    ]
    message_lower = message.lower().strip()
    return any(keyword in message_lower for keyword in cancel_keywords)

def is_cancel_process(message: str) -> bool:
    """ตรวจสอบว่าเป็นคำสั่งยกเลิกขั้นตอนการจองหรือไม่"""
    cancel_process_keywords = [
        "ยกเลิก", "cancel", "stop", "หยุด", "ไม่เอา", "ไม่จอง"
    ]
    message_lower = message.lower().strip()
    return message_lower in cancel_process_keywords

def parse_reservation_message(message: str) -> Optional[Dict[str, Any]]:
    """แปลงข้อความเป็นข้อมูลการจอง (รูปแบบเก่า)"""
    try:
        # รูปแบบ: "ชื่อ เบอร์ วันที่ เวลา จำนวนคน [ความต้องการพิเศษ]"
        # ตัวอย่าง: "สมชาย 0812345678 15-12-2567 19:00 4 โต๊ะริมหน้าต่าง"
        
        parts = message.strip().split()
        if len(parts) < 5:
            return None
        
        name = parts[0]
        phone = parts[1]
        date = parts[2]
        time = parts[3]
        
        try:
            party_size = int(parts[4])
        except ValueError:
            return None
        
        special_requests = ' '.join(parts[5:]) if len(parts) > 5 else ""
        
        # ตรวจสอบรูปแบบเบอร์โทร
        if not re.match(r'^0\d{9}$', phone.replace('-', '').replace(' ', '')):
            return None
        
        # ตรวจสอบรูปแบบวันที่
        if not re.match(r'^\d{1,2}-\d{1,2}-\d{4}$', date):
            return None
        
        # ตรวจสอบรูปแบบเวลา
        if not re.match(r'^\d{1,2}:\d{2}$', time):
            return None
        
        return {
            'customer_name': name,
            'phone': phone.replace('-', '').replace(' ', ''),
            'date': date,
            'time': time,
            'party_size': party_size,
            'special_requests': special_requests if special_requests else None
        }
        
    except Exception as e:
        logger.error(f"Error parsing reservation message: {e}")
        return None

def get_line_display_name(user_id: str) -> str:
    """ดึงชื่อแสดงของผู้ใช้จาก LINE API"""
    try:
        if not user_id:
            return "Unknown User"
        
        response = requests.get(
            f"https://api.line.me/v2/bot/profile/{user_id}",
            headers=LINE_HEADERS,
            timeout=10
        )
        
        if response.status_code == 200:
            profile = response.json()
            display_name = profile.get('displayName', 'Unknown User')
            logger.info(f"Retrieved display name for {user_id}: {display_name}")
            return display_name
        else:
            logger.warning(f"Failed to get user profile for {user_id}: {response.status_code}")
            return f"User_{user_id[:8]}"
            
    except requests.exceptions.Timeout:
        logger.warning(f"Timeout getting user profile for {user_id}")
        return f"User_{user_id[:8]}"
    except Exception as e:
        logger.error(f"Error getting user display name for {user_id}: {e}")
        return f"User_{user_id[:8]}"

def validate_phone_number(phone: str) -> bool:
    """ตรวจสอบความถูกต้องของเบอร์โทรศัพท์"""
    # ลบอักขระพิเศษ
    clean_phone = phone.replace('-', '').replace(' ', '').replace('(', '').replace(')', '')
    
    # ตรวจสอบรูปแบบเบอร์โทรไทย (10 หลัก เริ่มต้นด้วย 0)
    return bool(re.match(r'^0\d{9}$', clean_phone))

def validate_date_format(date_str: str) -> bool:
    """ตรวจสอบรูปแบบวันที่ (dd-mm-yyyy)"""
    try:
        if not re.match(r'^\d{1,2}-\d{1,2}-\d{4}$', date_str):
            return False
        
        day, month, year = date_str.split('-')
        
        # ตรวจสอบช่วงค่า
        if not (1 <= int(day) <= 31):
            return False
        if not (1 <= int(month) <= 12):
            return False
        if not (2500 <= int(year) <= 2600):  # พ.ศ.
            return False
        
        return True
    except ValueError:
        return False

def validate_time_format(time_str: str) -> bool:
    """ตรวจสอบรูปแบบเวลา (HH:MM)"""
    try:
        if not re.match(r'^\d{1,2}:\d{2}$', time_str):
            return False
        
        hour, minute = time_str.split(':')
        
        # ตรวจสอบช่วงค่า
        if not (0 <= int(hour) <= 23):
            return False
        if not (0 <= int(minute) <= 59):
            return False
        
        return True
    except ValueError:
        return False

def format_thai_date(date_str: str) -> str:
    """แปลงวันที่เป็นรูปแบบไทย"""
    try:
        day, month, year = date_str.split('-')
        thai_months = [
            "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
            "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"
        ]
        
        thai_month = thai_months[int(month) - 1]
        return f"{int(day)} {thai_month} {year}"
    except (ValueError, IndexError):
        return date_str

def clean_message_text(text: str) -> str:
    """ทำความสะอาดข้อความ"""
    if not text:
        return ""
    
    # ลบช่องว่างเกิน
    cleaned = ' '.join(text.split())
    
    # ลบอักขระพิเศษที่ไม่ต้องการ
    cleaned = re.sub(r'[^\w\s\-:/.@]', '', cleaned, flags=re.UNICODE)
    
    return cleaned.strip()

def is_business_hours(time_str: str) -> bool:
    """ตรวจสอบว่าอยู่ในเวลาทำการหรือไม่"""
    try:
        time_obj = datetime.strptime(time_str, "%H:%M").time()
        start_time = datetime.strptime("18:30", "%H:%M").time()
        end_time = datetime.strptime("21:30", "%H:%M").time()
        
        return start_time <= time_obj <= end_time
    except ValueError:
        return False

def generate_booking_id() -> str:
    """สร้าง booking ID แบบสุ่ม"""
    import uuid
    import time
    
    # ใช้ timestamp + uuid สำหรับความไม่ซ้ำ
    timestamp = str(int(time.time()))[-6:]  # 6 หลักท้าย
    unique_id = str(uuid.uuid4())[:8].upper()  # 8 ตัวแรกของ UUID
    
    return f"BK{timestamp}{unique_id}"

def sanitize_for_sheets(text: str) -> str:
    """ทำความสะอาดข้อความสำหรับบันทึกใน Google Sheets"""
    if not text:
        return ""
    
    # ลบอักขระที่อาจทำให้ Google Sheets ผิดพลาด
    sanitized = re.sub(r'[=+\-@]', '', str(text))  # ลบอักขระที่เป็น formula
    sanitized = sanitized.replace('\n', ' ').replace('\r', ' ')  # ลบ newline
    sanitized = ' '.join(sanitized.split())  # ลบช่องว่างเกิน
    
    return sanitized[:500]  # จำกัดความยาว

def log_api_call(endpoint: str, method: str, status_code: int, response_time: float):
    """บันทึก log การเรียก API"""
    logger.info(
        f"API_CALL | {method} {endpoint} | Status: {status_code} | "
        f"Response Time: {response_time:.3f}s"
    )

def mask_sensitive_data(data: str, mask_char: str = "*", visible_chars: int = 4) -> str:
    """ซ่อนข้อมูลที่อ่อนไหว"""
    if not data or len(data) <= visible_chars:
        return mask_char * len(data) if data else ""
    
    return data[:visible_chars] + mask_char * (len(data) - visible_chars)

# Constants สำหรับ validation
VALID_PARTY_SIZE_RANGE = (1, 20)
MAX_ADVANCE_BOOKING_DAYS = 7
MAX_SPECIAL_REQUEST_LENGTH = 200
MAX_NAME_LENGTH = 50