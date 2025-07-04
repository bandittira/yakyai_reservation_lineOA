import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple, List
import re

from config import log_booking_event, log_error_with_context
from flex_messages import (
    reply_to_user, 
    send_date_selection_flex, 
    send_time_selection_flex,
    send_flex_confirmation,
    send_user_reservations_flex
)
from models import ReservationData
from google_sheets import (
    add_reservation_to_sheet, 
    find_user_reservations, 
    cancel_reservation
)
from session_manager import (
    get_user_session, 
    update_user_session, 
    clear_reservation_session,
    start_reservation_session,
    start_cancellation_session,
    reset_timeout_task
)
from utils import get_line_display_name

logger = logging.getLogger(__name__)

async def handle_booking_process(reply_token: str, user_id: str, message: str, display_name: str = None) -> bool:
    """
    จัดการกระบวนการจองโต๊ะ (ใช้กับระบบ session management)
    
    Returns:
        bool: True ถ้าข้อความเป็นส่วนหนึ่งของกระบวนการจอง, False ถ้าไม่ใช่
    """
    try:
        if not display_name:
            display_name = get_line_display_name(user_id)
        
        # ตรวจสอบคำสั่งพิเศษก่อน
        if message in ['จองโต๊ะ', 'จอง', 'booking']:
            await start_booking_process(reply_token, user_id, display_name)
            return True
            
        elif message in ['ดูการจอง', 'รายการจอง', 'my reservations']:
            await show_user_reservations(reply_token, user_id, display_name)
            return True
            
        elif message in ['ยกเลิกการจอง', 'cancel booking']:
            await start_cancellation_process(reply_token, user_id, display_name)
            return True
            
        elif message in ['ยกเลิก', 'cancel', 'ยกเลิกขั้นตอนการจอง']:
            await cancel_booking_process(reply_token, user_id, display_name)
            return True
            
        elif message.startswith('ยกเลิก:'):
            await handle_specific_cancellation(reply_token, user_id, message, display_name)
            return True
        
        # ตรวจสอบว่าผู้ใช้อยู่ในระหว่างกระบวนการจองหรือไม่
        session = get_user_session(user_id)
        if not session:
            return False
        
        # รีเซ็ต timeout เมื่อมีการตอบสนอง
        reset_timeout_task(user_id)
        
        # จัดการตามขั้นตอนปัจจุบัน
        step = session.get('step', '')
        
        if step == 'name':
            return await handle_name_input(reply_token, user_id, message, display_name)
        elif step == 'phone':
            return await handle_phone_input(reply_token, user_id, message, display_name)
        elif step == 'date':
            return await handle_date_selection(reply_token, user_id, message, display_name)
        elif step == 'time':
            return await handle_time_selection(reply_token, user_id, message, display_name)
        elif step == 'party_size':
            return await handle_party_size_input(reply_token, user_id, message, display_name)
        elif step == 'special_requests':
            return await handle_special_requests_input(reply_token, user_id, message, display_name)
        elif step == 'cancel_phone':
            return await handle_cancellation_phone_input(reply_token, user_id, message, display_name)
        
        return False
        
    except Exception as e:
        log_error_with_context(
            error=e,
            context="handle_booking_process",
            user_id=user_id,
            additional_data={
                "message": message,
                "display_name": display_name
            }
        )
        
        # ล้างสถานะและแจ้งผู้ใช้
        clear_reservation_session(user_id)
        reply_to_user(reply_token, "เกิดข้อผิดพลาดในระบบ กรุณาเริ่มการจองใหม่อีกครั้ง\nพิมพ์ 'จองโต๊ะ' เพื่อเริ่มต้น")
        return True

async def start_booking_process(reply_token: str, user_id: str, display_name: str):
    """เริ่มกระบวนการจอง"""
    try:
        log_booking_event(
            event_type="BOOKING_PROCESS_STARTED",
            user_id=user_id,
            user_name=display_name
        )
        
        # เริ่ม session ใหม่
        start_reservation_session(user_id)
        
        reservation_info = (
            "🏮 ยินดีต้อนรับสู่ร้านยักษ์ใหญ่แดนใต้\n\n"
            "📋 รายละเอียดการจอง:\n"
            "⏰ เวลาให้บริการ: 18:30 - 21:30 น.\n"
            "📅 จองล่วงหน้าได้ไม่เกิน 7 วัน\n"
            "👥 รองรับ 1-20 คน\n"
            "🎫 ระบบจะสร้าง ID การจองให้อัตโนมัติ\n\n"
            "🔄 เริ่มขั้นตอนการจอง...\n"
            "ขอชื่อผู้จองค่ะ"
        )
        reply_to_user(reply_token, reservation_info)
        
    except Exception as e:
        log_error_with_context(error=e, context="start_booking_process", user_id=user_id)
        reply_to_user(reply_token, "เกิดข้อผิดพลาดในการเริ่มจอง กรุณาลองใหม่อีกครั้ง")

async def handle_name_input(reply_token: str, user_id: str, name_text: str, display_name: str) -> bool:
    """จัดการการใส่ชื่อ"""
    try:
        name = name_text.strip()
        
        # ตรวจสอบความยาวชื่อ
        if len(name) < 2:
            reply_to_user(reply_token, "กรุณาระบุชื่อที่มีความยาวอย่างน้อย 2 ตัวอักษร")
            return True
            
        if len(name) > 50:
            reply_to_user(reply_token, "ชื่อยาวเกินไป กรุณาระบุชื่อที่สั้นกว่า 50 ตัวอักษร")
            return True
        
        # อัพเดท session
        update_user_session(user_id, step="phone", data={"customer_name": name})
        
        log_booking_event(
            event_type="NAME_ENTERED",
            user_id=user_id,
            user_name=display_name,
            details={"customer_name": name}
        )
        
        reply_to_user(reply_token, "ขอเบอร์โทรค่ะ 📞\n\n(หากต้องการยกเลิก พิมพ์ 'ยกเลิก')")
        return True
        
    except Exception as e:
        log_error_with_context(error=e, context="handle_name_input", user_id=user_id)
        reply_to_user(reply_token, "เกิดข้อผิดพลาดในการระบุชื่อ กรุณาลองใหม่")
        return True

async def handle_phone_input(reply_token: str, user_id: str, phone_text: str, display_name: str) -> bool:
    """จัดการการใส่เบอร์โทร"""
    try:
        phone = phone_text.strip().replace('-', '').replace(' ', '')
        
        # ตรวจสอบรูปแบบเบอร์โทร (10 หลัก, เริ่มต้นด้วย 0)
        phone_pattern = r'^0\d{9}$'
        if not re.match(phone_pattern, phone):
            reply_to_user(reply_token, "กรุณาระบุเบอร์โทรศัพท์ที่ถูกต้อง (10 หลัก เริ่มต้นด้วย 0)")
            return True
        
        # อัพเดท session
        update_user_session(user_id, step="date", data={"phone": phone})
        
        log_booking_event(
            event_type="PHONE_ENTERED",
            user_id=user_id,
            user_name=display_name,
            details={"phone": phone}
        )
        
        # ส่งการเลือกวันที่
        send_date_selection_flex(reply_token)
        return True
        
    except Exception as e:
        log_error_with_context(error=e, context="handle_phone_input", user_id=user_id)
        reply_to_user(reply_token, "เกิดข้อผิดพลาดในการระบุเบอร์โทร กรุณาลองใหม่")
        return True

async def handle_date_selection(reply_token: str, user_id: str, date_text: str, display_name: str) -> bool:
    """จัดการการเลือกวันที่"""
    try:
        # ตรวจสอบรูปแบบวันที่ (dd-mm-yyyy)
        date_pattern = r'^\d{1,2}-\d{1,2}-\d{4}$'
        if not re.match(date_pattern, date_text):
            reply_to_user(reply_token, "กรุณาเลือกวันที่จากปุ่มที่กำหนดให้")
            return True
        
        # แปลงและตรวจสอบวันที่
        try:
            day, month, thai_year = date_text.split('-')
            year = int(thai_year) - 543  # แปลงจาก พ.ศ. เป็น ค.ศ.
            selected_date = datetime(year, int(month), int(day)).date()
            
            # ตรวจสอบว่าเป็นวันที่ในอนาคต
            today = datetime.now().date()
            if selected_date < today:
                reply_to_user(reply_token, "ไม่สามารถจองย้อนหลังได้ กรุณาเลือกวันที่ใหม่")
                return True
                
            # ตรวจสอบว่าไม่เกิน 7 วัน
            if (selected_date - today).days > 7:
                reply_to_user(reply_token, "สามารถจองล่วงหน้าได้สูงสุด 7 วัน กรุณาเลือกวันที่ใหม่")
                return True
                
        except ValueError:
            reply_to_user(reply_token, "รูปแบบวันที่ไม่ถูกต้อง กรุณาเลือกใหม่")
            return True
        
        # อัพเดท session
        update_user_session(user_id, step="time", data={"date": date_text})
        
        log_booking_event(
            event_type="DATE_SELECTED",
            user_id=user_id,
            user_name=display_name,
            details={"selected_date": date_text}
        )
        
        # ส่งการเลือกเวลา
        send_time_selection_flex(reply_token)
        return True
        
    except Exception as e:
        log_error_with_context(error=e, context="handle_date_selection", user_id=user_id)
        reply_to_user(reply_token, "เกิดข้อผิดพลาดในการเลือกวันที่ กรุณาลองใหม่")
        return True

async def handle_time_selection(reply_token: str, user_id: str, time_text: str, display_name: str) -> bool:
    """จัดการการเลือกเวลา"""
    try:
        # ตรวจสอบรูปแบบเวลา (HH:MM)
        time_pattern = r'^\d{2}:\d{2}$'
        if not re.match(time_pattern, time_text):
            reply_to_user(reply_token, "กรุณาเลือกเวลาจากปุ่มที่กำหนดให้")
            return True
        
        # ตรวจสอบช่วงเวลาที่ให้บริการ
        try:
            selected_time = datetime.strptime(time_text, "%H:%M").time()
            start_time = datetime.strptime("18:30", "%H:%M").time()
            end_time = datetime.strptime("21:30", "%H:%M").time()
            
            if not (start_time <= selected_time <= end_time):
                reply_to_user(reply_token, "เวลาที่เลือกไม่ถูกต้อง กรุณาเลือกเวลา 18:30 - 21:30 น.")
                return True
                
        except ValueError:
            reply_to_user(reply_token, "รูปแบบเวลาไม่ถูกต้อง กรุณาเลือกใหม่")
            return True
        
        # อัพเดท session
        update_user_session(user_id, step="party_size", data={"time": time_text})
        
        log_booking_event(
            event_type="TIME_SELECTED",
            user_id=user_id,
            user_name=display_name,
            details={"selected_time": time_text}
        )
        
        reply_to_user(reply_token, "จำนวนคนค่ะ 👥\n\n(หากต้องการยกเลิก พิมพ์ 'ยกเลิก')")
        return True
        
    except Exception as e:
        log_error_with_context(error=e, context="handle_time_selection", user_id=user_id)
        reply_to_user(reply_token, "เกิดข้อผิดพลาดในการเลือกเวลา กรุณาลองใหม่")
        return True

async def handle_party_size_input(reply_token: str, user_id: str, party_size_text: str, display_name: str) -> bool:
    """จัดการการใส่จำนวนคน"""
    try:
        # ตรวจสอบว่าเป็นตัวเลข
        try:
            party_size = int(party_size_text.strip())
        except ValueError:
            reply_to_user(reply_token, "กรุณาระบุจำนวนเป็นตัวเลขเท่านั้น (1-20)")
            return True
        
        # ตรวจสอบช่วงจำนวนคน
        if party_size <= 0:
            reply_to_user(reply_token, "กรุณาระบุจำนวนคนมากกว่า 0")
            return True
            
        if party_size > 20:
            reply_to_user(reply_token, "จำนวนคนเกิน 20 คน กรุณาติดต่อร้านโดยตรงค่ะ")
            return True
        
        # อัพเดท session
        update_user_session(user_id, step="special_requests", data={"party_size": party_size})
        
        log_booking_event(
            event_type="PARTY_SIZE_ENTERED",
            user_id=user_id,
            user_name=display_name,
            details={"party_size": party_size}
        )
        
        reply_to_user(reply_token, "มีคำขอเพิ่มเติมไหมคะ (เช่น โต๊ะริมหน้าต่าง, อาหารแพ้)\nถ้าไม่มี พิมพ์ - ค่ะ\n\n(หากต้องการยกเลิก พิมพ์ 'ยกเลิก')")
        return True
        
    except Exception as e:
        log_error_with_context(error=e, context="handle_party_size_input", user_id=user_id)
        reply_to_user(reply_token, "เกิดข้อผิดพลาดในการระบุจำนวนคน กรุณาลองใหม่")
        return True

async def handle_special_requests_input(reply_token: str, user_id: str, requests_text: str, display_name: str) -> bool:
    """จัดการการใส่ความต้องการพิเศษและทำการจองให้สมบูรณ์"""
    try:
        special_requests = requests_text.strip() if requests_text.strip() != "-" else ""
        
        if len(special_requests) > 200:
            reply_to_user(reply_token, "ความต้องการพิเศษยาวเกินไป กรุณาระบุให้สั้นกว่า 200 ตัวอักษร")
            return True
        
        log_booking_event(
            event_type="SPECIAL_REQUESTS_ENTERED",
            user_id=user_id,
            user_name=display_name,
            details={"special_requests": special_requests or "ไม่มี"}
        )
        
        # ดึงข้อมูลจาก session
        session = get_user_session(user_id)
        if not session:
            reply_to_user(reply_token, "เซสชันหมดอายุ กรุณาเริ่มจองใหม่")
            return True
        
        session_data = session.get('data', {})
        session_data['special_requests'] = special_requests
        
        # สร้าง reservation object
        reservation = ReservationData(
            customer_name=session_data.get('customer_name', ''),
            phone=session_data.get('phone', ''),
            date=session_data.get('date', ''),
            time=session_data.get('time', ''),
            party_size=session_data.get('party_size', 0),
            special_requests=special_requests,
            line_display_name=display_name,
            timestamp=datetime.now(),
            user_id=user_id
        )
        
        # บันทึกลง Google Sheets
        success, msg, booking_id = add_reservation_to_sheet(reservation)
        
        # ล้าง session
        clear_reservation_session(user_id)
        
        if success:
            reservation.booking_id = booking_id
            
            log_booking_event(
                event_type="BOOKING_COMPLETED",
                user_id=user_id,
                user_name=display_name,
                details={
                    "booking_id": booking_id,
                    "date": session_data.get('date', ''),
                    "time": session_data.get('time', ''),
                    "party_size": session_data.get('party_size', 0)
                }
            )
            
            send_flex_confirmation(reply_token, reservation)
        else:
            log_booking_event(
                event_type="BOOKING_FAILED",
                user_id=user_id,
                user_name=display_name,
                details={"error_message": msg}
            )
            
            reply_to_user(reply_token, msg)
        
        return True
        
    except Exception as e:
        log_error_with_context(error=e, context="handle_special_requests_input", user_id=user_id)
        reply_to_user(reply_token, "เกิดข้อผิดพลาดในการทำรายการจอง กรุณาลองใหม่อีกครั้ง")
        clear_reservation_session(user_id)
        return True

async def show_user_reservations(reply_token: str, user_id: str, display_name: str):
    """แสดงรายการจองของผู้ใช้"""
    try:
        log_booking_event(
            event_type="VIEW_RESERVATIONS_REQUESTED",
            user_id=user_id,
            user_name=display_name
        )
        
        # เริ่ม session สำหรับการยกเลิก
        start_cancellation_session(user_id)
        reply_to_user(reply_token, "กรุณาใส่เบอร์โทรที่ใช้จองเพื่อค้นหาการจองของคุณค่ะ")
        
    except Exception as e:
        log_error_with_context(error=e, context="show_user_reservations", user_id=user_id)
        reply_to_user(reply_token, "เกิดข้อผิดพลาดในการดูรายการจอง กรุณาลองใหม่")

async def start_cancellation_process(reply_token: str, user_id: str, display_name: str):
    """เริ่มกระบวนการยกเลิกการจอง"""
    try:
        log_booking_event(
            event_type="CANCELLATION_PROCESS_STARTED",
            user_id=user_id,
            user_name=display_name
        )
        
        start_cancellation_session(user_id)
        reply_to_user(reply_token, "กรุณาใส่เบอร์โทรที่ใช้จองเพื่อค้นหาการจองของคุณค่ะ")
        
    except Exception as e:
        log_error_with_context(error=e, context="start_cancellation_process", user_id=user_id)
        reply_to_user(reply_token, "เกิดข้อผิดพลาดในการเริ่มกระบวนการยกเลิก กรุณาลองใหม่")

async def handle_cancellation_phone_input(reply_token: str, user_id: str, phone_text: str, display_name: str) -> bool:
    """จัดการเบอร์โทรสำหรับการยกเลิก"""
    try:
        phone = phone_text.strip()
        
        log_booking_event(
            event_type="CANCELLATION_PHONE_ENTERED",
            user_id=user_id,
            user_name=display_name,
            details={"phone": phone}
        )
        
        # ค้นหาการจอง
        reservations = find_user_reservations(phone)
        
        # ตรวจสอบว่ามีข้อมูลการยกเลิกเฉพาะจาก session
        session = get_user_session(user_id)
        session_data = session.get('data', {}) if session else {}
        
        if "cancel_date" in session_data and "cancel_time" in session_data:
            # ยกเลิกการจองเฉพาะ
            success, msg = cancel_reservation(phone, session_data["cancel_date"], session_data["cancel_time"])
            clear_reservation_session(user_id)
            
            if success:
                log_booking_event(
                    event_type="CANCELLATION_SUCCESS",
                    user_id=user_id,
                    user_name=display_name,
                    details={
                        "phone": phone,
                        "date": session_data["cancel_date"],
                        "time": session_data["cancel_time"]
                    }
                )
            else:
                log_booking_event(
                    event_type="CANCELLATION_FAILED",
                    user_id=user_id,
                    user_name=display_name,
                    details={
                        "phone": phone,
                        "date": session_data["cancel_date"],
                        "time": session_data["cancel_time"],
                        "reason": msg
                    }
                )
            
            reply_to_user(reply_token, msg)
        else:
            # แสดงรายการการจองทั้งหมด
            clear_reservation_session(user_id)
            
            if reservations:
                send_user_reservations_flex(reply_token, reservations)
            else:
                reply_to_user(reply_token, "ไม่พบการจองของเบอร์นี้ในระบบค่ะ")
        
        return True
        
    except Exception as e:
        log_error_with_context(error=e, context="handle_cancellation_phone_input", user_id=user_id)
        reply_to_user(reply_token, "เกิดข้อผิดพลาดในการค้นหาการจอง กรุณาลองใหม่")
        clear_reservation_session(user_id)
        return True

async def handle_specific_cancellation(reply_token: str, user_id: str, cancel_message: str, display_name: str):
    """จัดการการยกเลิกการจองเฉพาะ"""
    try:
        # แยกข้อมูลจากข้อความ: "ยกเลิก:dd-mm-yyyy:HH:MM"
        parts = cancel_message.split(':')
        if len(parts) != 3:
            reply_to_user(reply_token, "รูปแบบการยกเลิกไม่ถูกต้อง")
            return
        
        _, date_part, time_part = parts
        
        log_booking_event(
            event_type="SPECIFIC_CANCELLATION_REQUESTED",
            user_id=user_id,
            user_name=display_name,
            details={"date": date_part, "time": time_part}
        )
        
        # เริ่ม session สำหรับการยกเลิกเฉพาะ
        start_cancellation_session(user_id)
        update_user_session(user_id, data={
            "cancel_date": date_part,
            "cancel_time": time_part
        })
        
        reply_to_user(reply_token, f"กรุณายืนยันการยกเลิกการจอง\nวันที่: {date_part} เวลา: {time_part}\n\nกรุณาใส่เบอร์โทรที่ใช้จองค่ะ")
        
    except Exception as e:
        log_error_with_context(error=e, context="handle_specific_cancellation", user_id=user_id)
        reply_to_user(reply_token, "เกิดข้อผิดพลาดในการยกเลิกการจอง กรุณาลองใหม่")

async def cancel_booking_process(reply_token: str, user_id: str, display_name: str):
    """ยกเลิกขั้นตอนการจอง"""
    try:
        session = get_user_session(user_id)
        
        if session:
            clear_reservation_session(user_id)
            
            log_booking_event(
                event_type="BOOKING_PROCESS_CANCELLED",
                user_id=user_id,
                user_name=display_name
            )
            
            reply_to_user(reply_token, "ยกเลิกขั้นตอนการจองเรียบร้อยแล้ว 😊\nหากต้องการจองใหม่ สามารถพิมพ์ 'จองโต๊ะ' ได้เลยค่ะ")
        else:
            reply_to_user(reply_token, "ไม่พบขั้นตอนการจองที่ต้องยกเลิก")
            
    except Exception as e:
        log_error_with_context(error=e, context="cancel_booking_process", user_id=user_id)
        reply_to_user(reply_token, "เกิดข้อผิดพลาดในการยกเลิกขั้นตอน")

# Utility functions สำหรับการตรวจสอบสถานะ
def get_active_booking_sessions() -> List[str]:
    """ดึงรายชื่อ user_id ที่มี session การจองที่ active"""
    # ฟังก์ชันนี้ต้องใช้ร่วมกับ session_manager
    from session_manager import get_all_active_sessions
    try:
        active_sessions = get_all_active_sessions()
        return [session['user_id'] for session in active_sessions if session.get('step') != 'cancel_phone']
    except Exception as e:
        logger.error(f"Error getting active booking sessions: {e}")
        return []

def get_booking_session_info(user_id: str) -> Optional[Dict[str, Any]]:
    """ดึงข้อมูล session การจองของผู้ใช้"""
    try:
        session = get_user_session(user_id)
        if not session:
            return None
        
        return {
            'user_id': user_id,
            'step': session.get('step', ''),
            'data': session.get('data', {}),
            'created_at': session.get('created_at'),
            'updated_at': session.get('updated_at')
        }
    except Exception as e:
        logger.error(f"Error getting booking session info for {user_id}: {e}")
        return None

def cleanup_expired_sessions():
    """ล้าง session ที่หมดอายุ (เรียกจาก scheduled job)"""
    try:
        from session_manager import cleanup_expired_sessions as cleanup
        cleanup()
        logger.info("Expired sessions cleaned up successfully")
    except Exception as e:
        logger.error(f"Error cleaning up expired sessions: {e}")

def is_user_in_booking_process(user_id: str) -> bool:
    """ตรวจสอบว่าผู้ใช้อยู่ในกระบวนการจองหรือไม่"""
    try:
        session = get_user_session(user_id)
        return session is not None and session.get('step') in [
            'name', 'phone', 'date', 'time', 'party_size', 'special_requests'
        ]
    except Exception as e:
        logger.error(f"Error checking booking process for {user_id}: {e}")
        return False

def get_booking_progress(user_id: str) -> Dict[str, Any]:
    """ดึงความคืบหน้าการจองของผู้ใช้"""
    try:
        session = get_user_session(user_id)
        if not session:
            return {'progress': 0, 'step': 'none', 'data': {}}
        
        step_progress = {
            'name': 1,
            'phone': 2,
            'date': 3,
            'time': 4,
            'party_size': 5,
            'special_requests': 6
        }
        
        current_step = session.get('step', 'none')
        progress = step_progress.get(current_step, 0)
        
        return {
            'progress': progress,
            'total_steps': 6,
            'step': current_step,
            'data': session.get('data', {}),
            'progress_percentage': int((progress / 6) * 100)
        }
    except Exception as e:
        logger.error(f"Error getting booking progress for {user_id}: {e}")
        return {'progress': 0, 'step': 'error', 'data': {}}

# ฟังก์ชันสำหรับ admin
def get_all_bookings_in_progress() -> List[Dict[str, Any]]:
    """ดึงการจองทั้งหมดที่อยู่ระหว่างดำเนินการ (สำหรับ admin)"""
    try:
        active_users = get_active_booking_sessions()
        bookings = []
        
        for user_id in active_users:
            progress = get_booking_progress(user_id)
            if progress['progress'] > 0:
                display_name = get_line_display_name(user_id)
                bookings.append({
                    'user_id': user_id,
                    'display_name': display_name,
                    'progress': progress,
                    'started_at': get_user_session(user_id).get('created_at')
                })
        
        return bookings
    except Exception as e:
        logger.error(f"Error getting all bookings in progress: {e}")
        return []

# ฟังก์ชันสำหรับ timeout handling
async def handle_booking_timeout(user_id: str):
    """จัดการเมื่อการจองหมดเวลา"""
    try:
        from flex_messages import send_timeout_warning_flex
        
        log_booking_event(
            event_type="BOOKING_TIMEOUT",
            user_id=user_id,
            user_name=get_line_display_name(user_id)
        )
        
        # ส่งข้อความเตือน
        send_timeout_warning_flex(user_id)
        
        # อาจจะลบ session หรือทำ action อื่นๆ ตามต้องการ
        # clear_reservation_session(user_id)
        
    except Exception as e:
        log_error_with_context(
            error=e,
            context="handle_booking_timeout",
            user_id=user_id
        )