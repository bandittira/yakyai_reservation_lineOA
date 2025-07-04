import logging
import json
from datetime import datetime
from typing import List, Dict, Any, Tuple, Optional
import gspread
from google.oauth2.service_account import Credentials

from config import GOOGLE_SHEETS_CREDENTIALS, SPREADSHEET_ID
from models import ReservationData
from utils import generate_booking_id, sanitize_for_sheets

logger = logging.getLogger(__name__)

# Google Sheets API scopes
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

# Column headers สำหรับ Google Sheets
HEADERS = [
    'ID การจอง',
    'วันที่จอง',
    'ชื่อผู้จอง',
    'เบอร์โทร',
    'วันที่',
    'เวลา',
    'จำนวนคน',
    'ความต้องการพิเศษ',
    'ชื่อ LINE',
    'User ID',
    'สถานะ',
    'หมายเหตุ'
]

def get_google_sheets_client():
    """สร้าง Google Sheets client"""
    try:
        if not GOOGLE_SHEETS_CREDENTIALS:
            raise ValueError("GOOGLE_SHEETS_CREDENTIALS not configured")
        
        # แปลง credentials จาก string เป็น dict
        if isinstance(GOOGLE_SHEETS_CREDENTIALS, str):
            creds_dict = json.loads(GOOGLE_SHEETS_CREDENTIALS)
        else:
            creds_dict = GOOGLE_SHEETS_CREDENTIALS
        
        # สร้าง credentials object
        credentials = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        
        # สร้าง client
        client = gspread.authorize(credentials)
        
        return client
        
    except Exception as e:
        logger.error(f"Error creating Google Sheets client: {e}")
        return None

def get_worksheet(sheet_name: str = "การจอง"):
    """ดึง worksheet จาก Google Sheets"""
    try:
        client = get_google_sheets_client()
        if not client:
            return None
        
        if not SPREADSHEET_ID:
            raise ValueError("SPREADSHEET_ID not configured")
        
        # เปิด spreadsheet
        spreadsheet = client.open_by_key(SPREADSHEET_ID)
        
        # ลองเปิด worksheet ที่มีอยู่
        try:
            worksheet = spreadsheet.worksheet(sheet_name)
        except gspread.WorksheetNotFound:
            # สร้าง worksheet ใหม่ถ้าไม่มี
            logger.info(f"Creating new worksheet: {sheet_name}")
            worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=20)
            
            # เพิ่ม headers
            worksheet.append_row(HEADERS)
            
            # จัดรูปแบบ header
            worksheet.format('A1:L1', {
                'backgroundColor': {'red': 0.8, 'green': 0.8, 'blue': 0.8},
                'textFormat': {'bold': True}
            })
        
        return worksheet
        
    except Exception as e:
        logger.error(f"Error getting worksheet '{sheet_name}': {e}")
        return None

def add_reservation_to_sheet(reservation: ReservationData) -> Tuple[bool, str, Optional[str]]:
    """เพิ่มการจองลง Google Sheets"""
    try:
        worksheet = get_worksheet()
        if not worksheet:
            return False, "ไม่สามารถเชื่อมต่อ Google Sheets ได้", None
        
        # สร้าง booking ID ถ้ายังไม่มี
        if not reservation.booking_id:
            reservation.booking_id = generate_booking_id()
        
        # เตรียมข้อมูลสำหรับบันทึก
        booking_date = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        row_data = [
            reservation.booking_id,
            booking_date,
            sanitize_for_sheets(reservation.customer_name),
            reservation.phone,
            reservation.date,
            reservation.time,
            reservation.party_size,
            sanitize_for_sheets(reservation.special_requests or ""),
            sanitize_for_sheets(reservation.line_display_name or ""),
            reservation.user_id or "",
            "ยืนยันแล้ว",
            ""  # หมายเหตุ
        ]
        
        # เพิ่มข้อมูลลง sheet
        worksheet.append_row(row_data)
        
        logger.info(f"Added reservation to sheet: {reservation.booking_id}")
        return True, "จองสำเร็จ! ขอบคุณค่ะ", reservation.booking_id
        
    except Exception as e:
        logger.error(f"Error adding reservation to sheet: {e}")
        return False, "เกิดข้อผิดพลาดในการบันทึกข้อมูล กรุณาลองใหม่อีกครั้ง", None

def find_user_reservations(phone: str) -> List[Dict[str, Any]]:
    """ค้นหาการจองของผู้ใช้จากเบอร์โทร"""
    try:
        worksheet = get_worksheet()
        if not worksheet:
            return []
        
        # ดึงข้อมูลทั้งหมด
        records = worksheet.get_all_records()
        
        for i, record in enumerate(records):
            if record.get('ID การจอง') == booking_id:
                row_number = i + 2  # +2 เพราะ header และ 0-based index
                
                # อัพเดทสถานะ
                worksheet.update_cell(row_number, 11, new_status)  # คอลัมน์สถานะ
                
                # อัพเดทหมายเหตุ
                if note:
                    current_note = record.get('หมายเหตุ', '')
                    timestamp = datetime.now().strftime("%d/%m/%Y %H:%M")
                    new_note = f"{current_note}\n[{timestamp}] {note}".strip()
                    worksheet.update_cell(row_number, 12, new_note)  # คอลัมน์หมายเหตุ
                
                logger.info(f"Updated reservation {booking_id} status to {new_status}")
                return True
        
        logger.warning(f"Reservation {booking_id} not found for status update")
        return False
        
    except Exception as e:
        logger.error(f"Error updating reservation status for {booking_id}: {e}")
        return False

def get_today_reservations() -> List[Dict[str, Any]]:
    """ดึงการจองของวันนี้"""
    try:
        worksheet = get_worksheet()
        if not worksheet:
            return []
        
        today = datetime.now().strftime("%d-%m-%Y")
        records = worksheet.get_all_records()
        
        today_reservations = []
        for record in records:
            # แปลงรูปแบบวันที่ให้ตรงกัน (อาจต้องปรับตามรูปแบบที่ใช้)
            reservation_date = record.get('วันที่', '')
            if reservation_date == today and record.get('สถานะ') not in ['ยกเลิกแล้ว']:
                today_reservations.append(record)
        
        # เรียงตามเวลา
        today_reservations.sort(key=lambda x: x.get('เวลา', ''))
        
        logger.info(f"Found {len(today_reservations)} reservations for today")
        return today_reservations
        
    except Exception as e:
        logger.error(f"Error getting today's reservations: {e}")
        return []

def get_reservations_by_date(date: str) -> List[Dict[str, Any]]:
    """ดึงการจองตามวันที่ที่ระบุ"""
    try:
        worksheet = get_worksheet()
        if not worksheet:
            return []
        
        records = worksheet.get_all_records()
        
        date_reservations = []
        for record in records:
            if (record.get('วันที่') == date and 
                record.get('สถานะ') not in ['ยกเลิกแล้ว']):
                date_reservations.append(record)
        
        # เรียงตามเวลา
        date_reservations.sort(key=lambda x: x.get('เวลา', ''))
        
        return date_reservations
        
    except Exception as e:
        logger.error(f"Error getting reservations for date {date}: {e}")
        return []

def get_reservation_statistics(days: int = 7) -> Dict[str, Any]:
    """ดึงสถิติการจองย้อนหลัง x วัน"""
    try:
        worksheet = get_worksheet()
        if not worksheet:
            return {}
        
        records = worksheet.get_all_records()
        
        # นับสถิติ
        total_reservations = len(records)
        confirmed_count = len([r for r in records if r.get('สถานะ') == 'ยืนยันแล้ว'])
        cancelled_count = len([r for r in records if r.get('สถานะ') == 'ยกเลิกแล้ว'])
        completed_count = len([r for r in records if r.get('สถานะ') == 'เสร็จสิ้น'])
        
        # สถิติตามวัน
        date_stats = {}
        for record in records:
            date = record.get('วันที่', '')
            if date:
                if date not in date_stats:
                    date_stats[date] = {'total': 0, 'confirmed': 0, 'cancelled': 0}
                date_stats[date]['total'] += 1
                if record.get('สถานะ') == 'ยืนยันแล้ว':
                    date_stats[date]['confirmed'] += 1
                elif record.get('สถานะ') == 'ยกเลิกแล้ว':
                    date_stats[date]['cancelled'] += 1
        
        # สถิติตามเวลา
        time_stats = {}
        for record in records:
            time = record.get('เวลา', '')
            if time and record.get('สถานะ') == 'ยืนยันแล้ว':
                time_stats[time] = time_stats.get(time, 0) + 1
        
        return {
            'total_reservations': total_reservations,
            'confirmed_reservations': confirmed_count,
            'cancelled_reservations': cancelled_count,
            'completed_reservations': completed_count,
            'cancellation_rate': round((cancelled_count / total_reservations * 100) if total_reservations > 0 else 0, 2),
            'date_statistics': date_stats,
            'popular_times': dict(sorted(time_stats.items(), key=lambda x: x[1], reverse=True)[:5])
        }
        
    except Exception as e:
        logger.error(f"Error getting reservation statistics: {e}")
        return {}

def backup_reservations() -> bool:
    """สำรองข้อมูลการจอง"""
    try:
        worksheet = get_worksheet()
        if not worksheet:
            return False
        
        # สร้าง worksheet สำรอง
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_sheet_name = f"สำรอง_{timestamp}"
        
        client = get_google_sheets_client()
        spreadsheet = client.open_by_key(SPREADSHEET_ID)
        
        # Copy ข้อมูลไปยัง worksheet ใหม่
        backup_worksheet = spreadsheet.add_worksheet(title=backup_sheet_name, rows=1000, cols=20)
        
        # Copy headers
        backup_worksheet.append_row(HEADERS)
        
        # Copy ข้อมูล
        records = worksheet.get_all_records()
        for record in records:
            row_data = [record.get(header, '') for header in HEADERS]
            backup_worksheet.append_row(row_data)
        
        logger.info(f"Created backup worksheet: {backup_sheet_name}")
        return True
        
    except Exception as e:
        logger.error(f"Error creating backup: {e}")
        return False

def validate_sheet_structure() -> bool:
    """ตรวจสอบโครงสร้าง Google Sheets"""
    try:
        worksheet = get_worksheet()
        if not worksheet:
            return False
        
        # ตรวจสอบ headers
        current_headers = worksheet.row_values(1)
        
        if current_headers != HEADERS:
            logger.warning("Sheet headers do not match expected structure")
            # อัพเดท headers ให้ถูกต้อง
            worksheet.delete_rows(1)
            worksheet.insert_row(HEADERS, 1)
            
            # จัดรูปแบบ header
            worksheet.format('A1:L1', {
                'backgroundColor': {'red': 0.8, 'green': 0.8, 'blue': 0.8},
                'textFormat': {'bold': True}
            })
            
            logger.info("Updated sheet headers")
        
        return True
        
    except Exception as e:
        logger.error(f"Error validating sheet structure: {e}")
        return False

def search_reservations(query: str, search_type: str = "all") -> List[Dict[str, Any]]:
    """ค้นหาการจองตามเงื่อนไขต่างๆ"""
    try:
        worksheet = get_worksheet()
        if not worksheet:
            return []
        
        records = worksheet.get_all_records()
        results = []
        
        for record in records:
            match = False
            
            if search_type == "name" or search_type == "all":
                if query.lower() in record.get('ชื่อผู้จอง', '').lower():
                    match = True
            
            if search_type == "phone" or search_type == "all":
                if query in record.get('เบอร์โทร', ''):
                    match = True
            
            if search_type == "booking_id" or search_type == "all":
                if query.upper() in record.get('ID การจอง', '').upper():
                    match = True
            
            if search_type == "date" or search_type == "all":
                if query in record.get('วันที่', ''):
                    match = True
            
            if match:
                results.append(record)
        
        logger.info(f"Search query '{query}' returned {len(results)} results")
        return results
        
    except Exception as e:
        logger.error(f"Error searching reservations: {e}")
        return []

def get_sheet_info() -> Dict[str, Any]:
    """ดึงข้อมูลเกี่ยวกับ Google Sheets"""
    try:
        client = get_google_sheets_client()
        if not client:
            return {}
        
        spreadsheet = client.open_by_key(SPREADSHEET_ID)
        
        worksheets = spreadsheet.worksheets()
        worksheet_info = []
        
        for ws in worksheets:
            worksheet_info.append({
                'title': ws.title,
                'id': ws.id,
                'row_count': ws.row_count,
                'col_count': ws.col_count,
                'updated': ws.updated
            })
        
        return {
            'spreadsheet_title': spreadsheet.title,
            'spreadsheet_id': spreadsheet.id,
            'spreadsheet_url': spreadsheet.url,
            'worksheets': worksheet_info,
            'last_updated': max([ws['updated'] for ws in worksheet_info]) if worksheet_info else None
        }
        
    except Exception as e:
        logger.error(f"Error getting sheet info: {e}")
        return {}

# Utility functions
def is_sheets_connected() -> bool:
    """ตรวจสอบการเชื่อมต่อ Google Sheets"""
    try:
        worksheet = get_worksheet()
        return worksheet is not None
    except Exception:
        return False

def get_available_time_slots(date: str) -> List[str]:
    """ดึงช่วงเวลาที่ว่างในวันที่ระบุ"""
    try:
        # เวลาที่เปิดให้บริการ
        all_times = ["18:30", "19:00", "19:30", "20:00", "20:30", "21:00", "21:30"]
        
        # ดึงการจองในวันนั้น
        reservations = get_reservations_by_date(date)
        booked_times = [r.get('เวลา') for r in reservations]
        
        # หาเวลาที่ว่าง
        available_times = [time for time in all_times if time not in booked_times]
        
        return available_times
        
    except Exception as e:
        logger.error(f"Error getting available time slots for {date}: {e}")
        return []
        
        # กรองเฉพาะของเบอร์โทรที่ระบุ และยังไม่ถูกยกเลิก
        user_reservations = []
        for record in records:
            if (record.get('เบอร์โทร') == phone and 
                record.get('สถานะ') not in ['ยกเลิกแล้ว', 'ไม่มาใช้บริการ']):
                
                # แปลงเป็นรูปแบบที่ flex message ต้องการ
                reservation_data = {
                    'data': {
                        'ID การจอง': record.get('ID การจอง', ''),
                        'ชื่อผู้จอง': record.get('ชื่อผู้จอง', ''),
                        'เบอร์โทร': record.get('เบอร์โทร', ''),
                        'วันที่': record.get('วันที่', ''),
                        'เวลา': record.get('เวลา', ''),
                        'จำนวนคน': record.get('จำนวนคน', ''),
                        'ความต้องการพิเศษ': record.get('ความต้องการพิเศษ', ''),
                        'สถานะ': record.get('สถานะ', '')
                    },
                    'row_number': records.index(record) + 2  # +2 เพราะ header และ 0-based index
                }
                user_reservations.append(reservation_data)
        
        logger.info(f"Found {len(user_reservations)} reservations for phone {phone}")
        return user_reservations
        
    except Exception as e:
        logger.error(f"Error finding user reservations for {phone}: {e}")
        return []

def cancel_reservation(phone: str, date: str, time: str) -> Tuple[bool, str]:
    """ยกเลิกการจองเฉพาะ"""
    try:
        worksheet = get_worksheet()
        if not worksheet:
            return False, "ไม่สามารถเชื่อมต่อ Google Sheets ได้"
        
        # ค้นหาการจองที่ตรงกัน
        records = worksheet.get_all_records()
        
        for i, record in enumerate(records):
            if (record.get('เบอร์โทร') == phone and 
                record.get('วันที่') == date and 
                record.get('เวลา') == time and
                record.get('สถานะ') not in ['ยกเลิกแล้ว', 'ไม่มาใช้บริการ']):
                
                # อัพเดทสถานะเป็นยกเลิก
                row_number = i + 2  # +2 เพราะ header และ 0-based index
                worksheet.update_cell(row_number, 11, 'ยกเลิกแล้ว')  # คอลัมน์สถานะ
                worksheet.update_cell(row_number, 12, f'ยกเลิกเมื่อ {datetime.now().strftime("%d/%m/%Y %H:%M:%S")}')  # หมายเหตุ
                
                booking_id = record.get('ID การจอง', '')
                logger.info(f"Cancelled reservation {booking_id} for phone {phone}")
                
                return True, f"ยกเลิกการจองเรียบร้อยแล้ว\nID การจอง: {booking_id}\nวันที่: {date} เวลา: {time}"
        
        return False, "ไม่พบการจองที่ตรงกับข้อมูลที่ระบุ"
        
    except Exception as e:
        logger.error(f"Error cancelling reservation: {e}")
        return False, "เกิดข้อผิดพลาดในการยกเลิกการจอง กรุณาลองใหม่อีกครั้ง"

def get_reservation_by_id(booking_id: str) -> Optional[Dict[str, Any]]:
    """ค้นหาการจองจาก ID"""
    try:
        worksheet = get_worksheet()
        if not worksheet:
            return None
        
        records = worksheet.get_all_records()
        
        for record in records:
            if record.get('ID การจอง') == booking_id:
                return record
        
        return None
        
    except Exception as e:
        logger.error(f"Error getting reservation by ID {booking_id}: {e}")
        return None

def update_reservation_status(booking_id: str, new_status: str, note: str = "") -> bool:
    """อัพเดทสถานะการจอง"""
    try:
        worksheet = get_worksheet()
        if not worksheet:
            return False

        records = worksheet.get_all_records()

        for i, record in enumerate(records):
            if record.get('ID การจอง') == booking_id:
                row_number = i + 2  # +2 เพราะ header และ 0-based index

                # อัพเดทสถานะ
                worksheet.update_cell(row_number, 11, new_status)  # คอลัมน์สถานะ

                # อัพเดทหมายเหตุ
                if note:
                    current_note = record.get('หมายเหตุ', '')
                    timestamp = datetime.now().strftime("%d/%m/%Y %H:%M")
                    new_note = f"{current_note}\n[{timestamp}] {note}".strip()
                    worksheet.update_cell(row_number, 12, new_note)  # คอลัมน์หมายเหตุ

                logger.info(f"Updated reservation {booking_id} status to {new_status}")
                return True

        logger.warning(f"Reservation {booking_id} not found for status update")
        return False

    except Exception as e:
        logger.error(f"Error updating reservation status for {booking_id}: {e}")
        return False