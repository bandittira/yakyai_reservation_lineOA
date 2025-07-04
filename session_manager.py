import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import asyncio
from threading import Timer

logger = logging.getLogger(__name__)

# In-memory storage สำหรับ sessions (ใน production ควรใช้ Redis)
user_sessions: Dict[str, Dict[str, Any]] = {}
timeout_tasks: Dict[str, Timer] = {}

# Session timeout (นาที)
SESSION_TIMEOUT_MINUTES = 10
WARNING_TIMEOUT_MINUTES = 8

def start_reservation_session(user_id: str):
    """เริ่ม session สำหรับการจอง"""
    try:
        # ล้าง session เก่า (ถ้ามี)
        clear_reservation_session(user_id)
        
        user_sessions[user_id] = {
            'type': 'reservation',
            'step': 'name',
            'data': {},
            'created_at': datetime.now(),
            'updated_at': datetime.now(),
            'expires_at': datetime.now() + timedelta(minutes=SESSION_TIMEOUT_MINUTES)
        }
        
        # เริ่ม timeout task
        start_timeout_task(user_id)
        
        logger.info(f"Started reservation session for user {user_id}")
        
    except Exception as e:
        logger.error(f"Error starting reservation session for {user_id}: {e}")

def start_cancellation_session(user_id: str):
    """เริ่ม session สำหรับการยกเลิกการจอง"""
    try:
        # ล้าง session เก่า (ถ้ามี)
        clear_reservation_session(user_id)
        
        user_sessions[user_id] = {
            'type': 'cancellation',
            'step': 'cancel_phone',
            'data': {},
            'created_at': datetime.now(),
            'updated_at': datetime.now(),
            'expires_at': datetime.now() + timedelta(minutes=SESSION_TIMEOUT_MINUTES)
        }
        
        # เริ่ม timeout task
        start_timeout_task(user_id)
        
        logger.info(f"Started cancellation session for user {user_id}")
        
    except Exception as e:
        logger.error(f"Error starting cancellation session for {user_id}: {e}")

def get_user_session(user_id: str) -> Optional[Dict[str, Any]]:
    """ดึงข้อมูล session ของผู้ใช้"""
    try:
        session = user_sessions.get(user_id)
        
        if not session:
            return None
        
        # ตรวจสอบว่า session หมดอายุหรือไม่
        if datetime.now() > session.get('expires_at', datetime.now()):
            logger.info(f"Session expired for user {user_id}")
            clear_reservation_session(user_id)
            return None
        
        return session
        
    except Exception as e:
        logger.error(f"Error getting session for {user_id}: {e}")
        return None

def update_user_session(user_id: str, step: str = None, data: Dict[str, Any] = None):
    """อัพเดท session ของผู้ใช้"""
    try:
        session = get_user_session(user_id)
        if not session:
            logger.warning(f"No session found for user {user_id} to update")
            return False
        
        # อัพเดท step
        if step:
            session['step'] = step
        
        # อัพเดท data
        if data:
            session['data'].update(data)
        
        # อัพเดทเวลา
        session['updated_at'] = datetime.now()
        session['expires_at'] = datetime.now() + timedelta(minutes=SESSION_TIMEOUT_MINUTES)
        
        # รีเซ็ต timeout task
        reset_timeout_task(user_id)
        
        logger.debug(f"Updated session for user {user_id}: step={step}")
        return True
        
    except Exception as e:
        logger.error(f"Error updating session for {user_id}: {e}")
        return False

def update_last_activity(user_id: str):
    """อัพเดทเวลาการใช้งานล่าสุด"""
    try:
        session = get_user_session(user_id)
        if session:
            session['updated_at'] = datetime.now()
            session['expires_at'] = datetime.now() + timedelta(minutes=SESSION_TIMEOUT_MINUTES)
            reset_timeout_task(user_id)
            
    except Exception as e:
        logger.error(f"Error updating last activity for {user_id}: {e}")

def clear_reservation_session(user_id: str):
    """ล้าง session ของผู้ใช้"""
    try:
        # ล้าง session data
        if user_id in user_sessions:
            del user_sessions[user_id]
            logger.info(f"Cleared session for user {user_id}")
        
        # ยกเลิก timeout task
        cancel_timeout_task(user_id)
        
    except Exception as e:
        logger.error(f"Error clearing session for {user_id}: {e}")

def get_all_active_sessions() -> List[Dict[str, Any]]:
    """ดึง session ทั้งหมดที่ active"""
    try:
        active_sessions = []
        current_time = datetime.now()
        
        for user_id, session in user_sessions.items():
            if current_time <= session.get('expires_at', current_time):
                session_info = session.copy()
                session_info['user_id'] = user_id
                active_sessions.append(session_info)
        
        return active_sessions
        
    except Exception as e:
        logger.error(f"Error getting all active sessions: {e}")
        return []

def cleanup_expired_sessions():
    """ล้าง session ที่หมดอายุ"""
    try:
        current_time = datetime.now()
        expired_users = []
        
        for user_id, session in user_sessions.items():
            if current_time > session.get('expires_at', current_time):
                expired_users.append(user_id)
        
        for user_id in expired_users:
            clear_reservation_session(user_id)
            logger.info(f"Cleaned up expired session for user {user_id}")
        
        return len(expired_users)
        
    except Exception as e:
        logger.error(f"Error cleaning up expired sessions: {e}")
        return 0

# Timeout Management
def start_timeout_task(user_id: str):
    """เริ่ม timeout task สำหรับผู้ใช้"""
    try:
        # ยกเลิก task เก่า (ถ้ามี)
        cancel_timeout_task(user_id)
        
        # สร้าง warning task (เตือนก่อนหมดเวลา)
        warning_timer = Timer(
            WARNING_TIMEOUT_MINUTES * 60,
            _send_timeout_warning,
            args=[user_id]
        )
        warning_timer.start()
        
        # สร้าง timeout task (ล้าง session เมื่อหมดเวลา)
        timeout_timer = Timer(
            SESSION_TIMEOUT_MINUTES * 60,
            _handle_session_timeout,
            args=[user_id]
        )
        timeout_timer.start()
        
        timeout_tasks[user_id] = {
            'warning': warning_timer,
            'timeout': timeout_timer
        }
        
        logger.debug(f"Started timeout tasks for user {user_id}")
        
    except Exception as e:
        logger.error(f"Error starting timeout task for {user_id}: {e}")

def reset_timeout_task(user_id: str):
    """รีเซ็ต timeout task (เมื่อมีการตอบสนองจากผู้ใช้)"""
    try:
        # ยกเลิก task เก่า
        cancel_timeout_task(user_id)
        
        # เริ่ม task ใหม่
        start_timeout_task(user_id)
        
        logger.debug(f"Reset timeout tasks for user {user_id}")
        
    except Exception as e:
        logger.error(f"Error resetting timeout task for {user_id}: {e}")

def cancel_timeout_task(user_id: str):
    """ยกเลิก timeout task"""
    try:
        if user_id in timeout_tasks:
            tasks = timeout_tasks[user_id]
            
            if 'warning' in tasks and tasks['warning'].is_alive():
                tasks['warning'].cancel()
            
            if 'timeout' in tasks and tasks['timeout'].is_alive():
                tasks['timeout'].cancel()
            
            del timeout_tasks[user_id]
            logger.debug(f"Cancelled timeout tasks for user {user_id}")
        
    except Exception as e:
        logger.error(f"Error cancelling timeout task for {user_id}: {e}")

def _send_timeout_warning(user_id: str):
    """ส่งข้อความเตือนก่อนหมดเวลา (internal function)"""
    try:
        session = get_user_session(user_id)
        if session:
            from booking_logic import handle_booking_timeout
            asyncio.create_task(handle_booking_timeout(user_id))
            logger.info(f"Sent timeout warning to user {user_id}")
        
    except Exception as e:
        logger.error(f"Error sending timeout warning to {user_id}: {e}")

def _handle_session_timeout(user_id: str):
    """จัดการเมื่อ session หมดเวลา (internal function)"""
    try:
        session = get_user_session(user_id)
        if session:
            from config import log_booking_event
            from utils import get_line_display_name
            
            log_booking_event(
                event_type="SESSION_TIMEOUT",
                user_id=user_id,
                user_name=get_line_display_name(user_id)
            )
            
            clear_reservation_session(user_id)
            logger.info(f"Session timeout handled for user {user_id}")
        
    except Exception as e:
        logger.error(f"Error handling session timeout for {user_id}: {e}")

# Statistics และ Monitoring
def get_session_statistics() -> Dict[str, Any]:
    """ดึงสถิติการใช้งาน session"""
    try:
        active_sessions = get_all_active_sessions()
        
        reservation_count = len([s for s in active_sessions if s.get('type') == 'reservation'])
        cancellation_count = len([s for s in active_sessions if s.get('type') == 'cancellation'])
        
        step_distribution = {}
        for session in active_sessions:
            step = session.get('step', 'unknown')
            step_distribution[step] = step_distribution.get(step, 0) + 1
        
        return {
            'total_active_sessions': len(active_sessions),
            'reservation_sessions': reservation_count,
            'cancellation_sessions': cancellation_count,
            'step_distribution': step_distribution,
            'timeout_tasks_count': len(timeout_tasks)
        }
        
    except Exception as e:
        logger.error(f"Error getting session statistics: {e}")
        return {}

def is_session_healthy() -> bool:
    """ตรวจสอบสถานะความปกติของ session system"""
    try:
        # ตรวจสอบจำนวน session ที่มากเกินไป
        active_count = len(get_all_active_sessions())
        if active_count > 100:  # threshold
            logger.warning(f"Too many active sessions: {active_count}")
            return False
        
        # ตรวจสอบ memory usage
        timeout_count = len(timeout_tasks)
        if timeout_count > active_count * 2:  # แต่ละ session ควรมี timeout task 2 ตัว
            logger.warning(f"Timeout tasks mismatch: {timeout_count} tasks for {active_count} sessions")
            return False
        
        return True
        
    except Exception as e:
        logger.error(f"Error checking session health: {e}")
        return False