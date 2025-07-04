import logging
from typing import Dict, Any
from config import log_booking_event, log_error_with_context
from flex_messages import reply_to_user, send_admin_notification
from booking_logic import handle_booking_process
from utils import get_line_display_name

logger = logging.getLogger(__name__)

async def handle_webhook_request(body: dict, headers: dict) -> bool:
    """จัดการ webhook request จาก LINE"""
    try:
        events = body.get('events', [])
        
        for event in events:
            event_type = event.get('type')
            
            if event_type == 'message':
                await handle_message_event(event)
            elif event_type == 'follow':
                await handle_follow_event(event)
            elif event_type == 'unfollow':
                await handle_unfollow_event(event)
            else:
                logger.info(f"Unhandled event type: {event_type}")
        
        return True
        
    except Exception as e:
        log_error_with_context(
            error=e,
            context="handle_webhook_request",
            additional_data={"body": body}
        )
        return False

async def handle_message_event(event: dict):
    """จัดการ message event"""
    try:
        # ดึงข้อมูลพื้นฐาน
        reply_token = event['replyToken']
        user_id = event['source']['userId']
        message = event['message']
        message_type = message['type']
        
        # ดึงชื่อผู้ใช้ (จะใช้ใน log)
        display_name = get_user_display_name(user_id)
        
        if message_type == 'text':
            message_text = message['text']
            
            # บันทึก log การรับข้อความ
            log_booking_event(
                event_type="MESSAGE_RECEIVED",
                user_id=user_id,
                user_name=display_name,
                details={"message": message_text}
            )
            
            # จัดการข้อความ
            await handle_text_message(reply_token, user_id, message_text, display_name)
            
        else:
            logger.info(f"Received non-text message: {message_type} from {display_name}")
            reply_to_user(reply_token, "ขออภัย ระบบรองรับเฉพาะข้อความตัวอักษรเท่านั้น")
            
    except Exception as e:
        log_error_with_context(
            error=e,
            context="handle_message_event",
            user_id=event.get('source', {}).get('userId'),
            additional_data={"event": event}
        )

async def handle_text_message(reply_token: str, user_id: str, message_text: str, display_name: str):
    """จัดการข้อความตัวอักษร"""
    try:
        # คำสั่งพื้นฐาน
        if message_text.lower() in ['สวัสดี', 'hello', 'hi', 'start']:
            log_booking_event(
                event_type="GREETING",
                user_id=user_id,
                user_name=display_name
            )
            reply_to_user(reply_token, "สวัสดีครับ! ยินดีต้อนรับสู่ร้านยักษ์ใหญ่แดนใต้\n\nพิมพ์ 'จองโต๊ะ' เพื่อเริ่มจองโต๊ะ\nพิมพ์ 'ดูการจอง' เพื่อดูรายการจองของคุณ")
            
        elif message_text in ['จองโต๊ะ', 'จอง']:
            log_booking_event(
                event_type="BOOKING_STARTED",
                user_id=user_id,
                user_name=display_name
            )
            await handle_booking_process(reply_token, user_id, 'start_booking', display_name)
            
        elif message_text in ['ดูการจอง', 'รายการจอง']:
            log_booking_event(
                event_type="VIEW_RESERVATIONS",
                user_id=user_id,
                user_name=display_name
            )
            await handle_booking_process(reply_token, user_id, 'view_reservations', display_name)
            
        elif message_text.startswith('ยกเลิก:'):
            # การยกเลิกการจองเฉพาะ
            log_booking_event(
                event_type="CANCEL_SPECIFIC_BOOKING",
                user_id=user_id,
                user_name=display_name,
                details={"cancel_request": message_text}
            )
            await handle_booking_process(reply_token, user_id, message_text, display_name)
            
        elif message_text in ['ยกเลิกขั้นตอนการจอง']:
            log_booking_event(
                event_type="CANCEL_BOOKING_PROCESS",
                user_id=user_id,
                user_name=display_name
            )
            await handle_booking_process(reply_token, user_id, 'cancel_process', display_name)
            
        else:
            # ข้อความอื่นๆ ระหว่างกระบวนการจอง
            booking_result = await handle_booking_process(reply_token, user_id, message_text, display_name)
            
            if not booking_result:
                # ถ้าไม่ใช่กระบวนการจอง อาจเป็นการสอบถาม
                log_booking_event(
                    event_type="CUSTOMER_INQUIRY",
                    user_id=user_id,
                    user_name=display_name,
                    details={"inquiry": message_text}
                )
                
                # ส่งแจ้งแอดมิน
                send_admin_notification(user_id, message_text, display_name)
                
                # ตอบลูกค้า
                reply_to_user(
                    reply_token, 
                    "ขอบคุณสำหรับข้อความของคุณ ทางเราได้รับเรื่องแล้ว และจะติดต่อกลับไปเร็วๆ นี้\n\nหากต้องการจองโต๊ะ กรุณาพิมพ์ 'จองโต๊ะ'"
                )
                
    except Exception as e:
        log_error_with_context(
            error=e,
            context="handle_text_message",
            user_id=user_id,
            additional_data={
                "message_text": message_text,
                "display_name": display_name
            }
        )

async def handle_follow_event(event: dict):
    """จัดการเมื่อมีคนเพิ่มเป็นเพื่อน"""
    try:
        user_id = event['source']['userId']
        reply_token = event['replyToken']
        display_name = get_user_display_name(user_id)
        
        log_booking_event(
            event_type="USER_FOLLOWED",
            user_id=user_id,
            user_name=display_name
        )
        
        welcome_message = """🎉 ยินดีต้อนรับสู่ร้านยักษ์ใหญ่แดนใต้!

📱 คำสั่งที่ใช้ได้:
• พิมพ์ 'จองโต๊ะ' - เริ่มจองโต๊ะ
• พิมพ์ 'ดูการจอง' - ดูรายการจองของคุณ

🕐 เวลาให้บริการ: 18:30 - 21:30 น.
📍 สามารถจองล่วงหน้าได้ไม่เกิน 7 วัน

ขอบคุณที่เลือกใช้บริการของเรา! 🙏"""
        
        reply_to_user(reply_token, welcome_message)
        
    except Exception as e:
        log_error_with_context(
            error=e,
            context="handle_follow_event",
            user_id=event.get('source', {}).get('userId'),
            additional_data={"event": event}
        )

async def handle_unfollow_event(event: dict):
    """จัดการเมื่อมีคนยกเลิกการเป็นเพื่อน"""
    try:
        user_id = event['source']['userId']
        
        log_booking_event(
            event_type="USER_UNFOLLOWED",
            user_id=user_id,
            user_name="Unknown (unfollowed)"
        )
        
        logger.info(f"User {user_id} unfollowed the bot")
        
    except Exception as e:
        log_error_with_context(
            error=e,
            context="handle_unfollow_event",
            additional_data={"event": event}
        )

def get_user_display_name(user_id: str) -> str:
    """ดึงชื่อแสดงของผู้ใช้"""
    try:
        # ใช้ LINE API เพื่อดึงข้อมูลผู้ใช้
        import requests
        from config import LINE_HEADERS
        
        response = requests.get(
            f"https://api.line.me/v2/bot/profile/{user_id}",
            headers=LINE_HEADERS
        )
        
        if response.status_code == 200:
            profile = response.json()
            return profile.get('displayName', 'Unknown User')
        else:
            logger.warning(f"Failed to get user profile: {response.status_code}")
            return f"User_{user_id[:8]}"
            
    except Exception as e:
        logger.error(f"Error getting user display name: {e}")
        return f"User_{user_id[:8]}"