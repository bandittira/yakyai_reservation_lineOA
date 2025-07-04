import json
import requests
from datetime import datetime, date, timedelta
from config import LINE_HEADERS
from models import ReservationData
import logging
import os

logger = logging.getLogger(__name__)

def reply_to_user(reply_token: str, message: str):
    """ส่งข้อความธรรมดา"""
    payload = {
        "replyToken": reply_token,
        "messages": [{"type": "text", "text": message}]
    }
    try:
        requests.post("https://api.line.me/v2/bot/message/reply", headers=LINE_HEADERS, data=json.dumps(payload))
    except Exception as e:
        logger.error(f"reply_to_user error: {e}")

def send_flex_confirmation(reply_token: str, res: ReservationData):
    """ส่งการยืนยันการจอง"""
    flex_message = {
        "type": "flex",
        "altText": "ยืนยันการจองโต๊ะ",
        "contents": {
            "type": "bubble",
            "styles": {
                "body": {
                    "backgroundColor": "#f8f9fa"
                }
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "md",
                "contents": [
                    {
                        "type": "text",
                        "text": "✅ ยืนยันการจองโต๊ะ",
                        "weight": "bold",
                        "size": "xl",
                        "color": "#46291A",
                        "align": "center"
                    },
                    {
                        "type": "separator",
                        "margin": "md",
                        "color": "#46291A"
                    },# เพิ่ม ID การจอง
                    {
                        "type": "box",
                        "layout": "vertical",
                        "spacing": "sm",
                        "margin": "lg",
                        "paddingAll": "md",
                        "backgroundColor": "#e8f5e8",
                        "cornerRadius": "md",
                        "contents": [
                            {
                                "type": "text",
                                "text": f"🎫 ID การจอง: {res.booking_id}",
                                "weight": "bold",
                                "size": "lg",
                                "color": "#2d5016",
                                "align": "center"
                            },
                            {
                                "type": "text",
                                "text": "📝 กรุณาเก็บ ID นี้ไว้สำหรับอ้างอิง",
                                "size": "xs",
                                "color": "#666666",
                                "align": "center",
                                "margin": "sm"
                            }
                        ]
                    },{
                        "type": "box",
                        "layout": "vertical",
                        "spacing": "sm",
                        "margin": "lg",
                        "contents": [
                            {
                                "type": "box",
                                "layout": "baseline",
                                "contents": [
                                    {
                                        "type": "text",
                                        "text": "👤 ชื่อ:",
                                        "size": "md",
                                        "color": "#666666",
                                        "flex": 2
                                    },
                                    {
                                        "type": "text",
                                        "text": res.customer_name,
                                        "size": "md",
                                        "color": "#333333",
                                        "flex": 3,
                                        "weight": "bold"
                                    }
                                ]
                            },
                            {
                                "type": "box",
                                "layout": "baseline",
                                "contents": [
                                    {
                                        "type": "text",
                                        "text": "📞 เบอร์:",
                                        "size": "md",
                                        "color": "#666666",
                                        "flex": 2
                                    },
                                    {
                                        "type": "text",
                                        "text": res.phone,
                                        "size": "md",
                                        "color": "#333333",
                                        "flex": 3,
                                        "weight": "bold"
                                    }
                                ]
                            },{
                                "type": "box",
                                "layout": "baseline",
                                "contents": [
                                    {
                                        "type": "text",
                                        "text": "📅 วันที่:",
                                        "size": "md",
                                        "color": "#666666",
                                        "flex": 2
                                    },
                                    {
                                        "type": "text",
                                        "text": res.date,
                                        "size": "md",
                                        "color": "#333333",
                                        "flex": 3,
                                        "weight": "bold"
                                    }
                                ]
                            },
                            {
                                "type": "box",
                                "layout": "baseline",
                                "contents": [
                                    {
                                        "type": "text",
                                        "text": "🕐 เวลา:",
                                        "size": "md",
                                        "color": "#666666",
                                        "flex": 2
                                    },
                                    {
                                        "type": "text",
                                        "text": res.time,
                                        "size": "md",
                                        "color": "#333333",
                                        "flex": 3,
                                        "weight": "bold"
                                    }
                                ]
                            },
                            {
                                "type": "box",
                                "layout": "baseline",
                                "contents": [
                                    {
                                        "type": "text",
                                        "text": "👥 จำนวน:",
                                        "size": "md",
                                        "color": "#666666",
                                        "flex": 2
                                    },
                                    {
                                        "type": "text",
                                        "text": f"{res.party_size} คน",
                                        "size": "md",
                                        "color": "#333333",
                                        "flex": 3,
                                        "weight": "bold"
                                    }
                                ]
                            },
                            {
                                "type": "box",
                                "layout": "baseline",
                                "contents": [
                                    {
                                        "type": "text",
                                        "text": "📝 เพิ่มเติม:",
                                        "size": "md",
                                        "color": "#666666",
                                        "flex": 2
                                    },
                                    {
                                        "type": "text",
                                        "text": res.special_requests or "ไม่มี",
                                        "size": "md",
                                        "color": "#333333",
                                        "flex": 3,
                                        "wrap": True
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        "type": "separator",
                        "margin": "lg"
                    },
                    {
                        "type": "text",
                        "text": "📍 ร้านยักษ์ใหญ่แดนใต้",
                        "size": "md",
                        "color": "#46291A",
                        "align": "center",
                        "weight": "bold",
                        "margin": "md"
                    }
                ]
            }
        }
    }
    payload = {"replyToken": reply_token, "messages": [flex_message]}
    try:
        requests.post("https://api.line.me/v2/bot/message/reply", headers=LINE_HEADERS, data=json.dumps(payload))
    except Exception as e:
        logger.error(f"send_flex_confirmation error: {e}")

def send_date_selection_flex(reply_token: str):
    """ส่งการเลือกวันที่"""
    today = datetime.today().date()
    days = [(today + timedelta(days=i)) for i in range(7)]

    thai_days = ["จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์", "อาทิตย์"]
    thai_months = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
                   "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]

    buttons = []
    for d in days:
        thai_day = thai_days[d.weekday()]
        thai_month = thai_months[d.month - 1]
        thai_year = d.year + 543

        display_date = f"{d.day} {thai_month}"
        if d == today:
            display_date = f"วันนี้ ({display_date})"
        elif d == today + timedelta(days=1):
            display_date = f"พรุ่งนี้ ({display_date})"
        else:
            display_date = f"{thai_day} ({display_date})"

        return_date = d.strftime("%d-%m-") + str(thai_year)

        buttons.append({
            "type": "button",
            "action": {
                "type": "message",
                "label": display_date[:20],
                "text": return_date
            },
            "style": "primary",
            "color": "#46291A",
            "height": "sm"
        })

    # กลุ่มละ 2 ปุ่มในแถว
    button_boxes = []
    for i in range(0, len(buttons), 2):
        row = {
            "type": "box",
            "layout": "horizontal",
            "spacing": "sm",
            "contents": buttons[i:i + 2]
        }
        button_boxes.append(row)

    # เพิ่มปุ่มยกเลิกขั้นตอนการจอง (แยกจากการยกเลิกการจองที่มีอยู่แล้ว)
    cancel_button = {
        "type": "button",
        "action": {
            "type": "message",
            "label": "❌ ยกเลิกขั้นตอนการจอง",
            "text": "ยกเลิกขั้นตอนการจอง"
        },
        "style": "secondary",
        "color": "#dc3545",
        "height": "sm"
    }

    flex = {
        "type": "flex",
        "altText": "กรุณาเลือกวันที่ต้องการจอง",
        "contents": {
            "type": "bubble",
            "size": "mega",
            "styles": {
                "body": {
                    "backgroundColor": "#ffffff"
                }
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "md",
                "paddingAll": "lg",
                "contents": [
                    {
                        "type": "text",
                        "text": "📅 เลือกวันที่ที่ต้องการจอง",
                        "weight": "bold",
                        "size": "xl",
                        "color": "#46291A",
                        "align": "center"
                    },
                    {
                        "type": "separator",
                        "margin": "md",
                        "color": "#46291A"
                    },
                    {
                        "type": "text",
                        "text": "สามารถจองล่วงหน้าได้ไม่เกิน 7 วัน",
                        "size": "sm",
                        "color": "#666666",
                        "align": "center",
                        "margin": "md"
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "spacing": "sm",
                        "margin": "lg",
                        "contents": button_boxes
                    },
                    {
                        "type": "separator",
                        "margin": "lg",
                        "color": "#e0e0e0"
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "margin": "md",
                        "contents": [cancel_button]
                    }
                ]
            }
        }
    }

    payload = {
        "replyToken": reply_token,
        "messages": [flex]
    }

    try:
        requests.post("https://api.line.me/v2/bot/message/reply", headers=LINE_HEADERS, data=json.dumps(payload))
    except Exception as e:
        logger.error(f"send_date_selection_flex error: {e}")

def send_time_selection_flex(reply_token: str):
    """ส่งการเลือกเวลา"""
    start_time = datetime.strptime("18:30", "%H:%M")
    times = [(start_time + timedelta(minutes=30 * i)).strftime("%H:%M") for i in range(7)]  # 18:30 ถึง 21:30

    buttons = []
    for t in times:
        buttons.append({
            "type": "button",
            "action": {
                "type": "message",
                "label": t,
                "text": t
            },
            "style": "primary",
            "color": "#46291A",
            "height": "sm",
            "margin": "none"
        })

    # แบ่งปุ่มเป็น 2 คอลัมน์
    button_boxes = []
    for i in range(0, len(buttons), 2):
        row_buttons = buttons[i:i+2]
        button_boxes.append({
            "type": "box",
            "layout": "horizontal",
            "spacing": "md",
            "margin": "sm",
            "contents": row_buttons
        })

    # เพิ่มปุ่มสำหรับเวลาที่เหลือ (ถ้าเป็นจำนวนคี่)
    if len(times) % 2 == 1:
        last_button_box = {
            "type": "box",
            "layout": "horizontal",
            "spacing": "md",
            "margin": "sm",
            "contents": [buttons[-1]]
        }
        button_boxes[-1] = last_button_box

    # เพิ่มปุ่มยกเลิกขั้นตอนการจอง
    cancel_button = {
        "type": "button",
        "action": {
            "type": "message",
            "label": "❌ ยกเลิกขั้นตอนการจอง",
            "text": "ยกเลิกขั้นตอนการจอง"
        },
        "style": "secondary",
        "color": "#dc3545",
        "height": "sm"
    }

    flex = {
        "type": "flex",
        "altText": "กรุณาเลือกเวลาที่ต้องการจอง",
        "contents": {
            "type": "bubble",
            "size": "mega",
            "styles": {
                "body": {
                    "backgroundColor": "#ffffff"
                }
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "md",
                "paddingAll": "lg",
                "contents": [
                    {
                        "type": "text",
                        "text": "🕐 เลือกเวลาที่ต้องการจอง",
                        "weight": "bold",
                        "size": "xl",
                        "color": "#46291A",
                        "align": "center"
                    },
                    {
                        "type": "separator",
                        "margin": "md",
                        "color": "#46291A"
                    },
                    {
                        "type": "text",
                        "text": "เวลาให้บริการ 18:30 - 21:30 น.",
                        "size": "sm",
                        "color": "#666666",
                        "align": "center",
                        "margin": "md"
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "spacing": "sm",
                        "margin": "lg",
                        "paddingAll": "sm",
                        "backgroundColor": "#f8f9fa",
                        "cornerRadius": "md",
                        "contents": button_boxes
                    },
                    {
                        "type": "separator",
                        "margin": "lg",
                        "color": "#e0e0e0"
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "margin": "md",
                        "contents": [cancel_button]
                    }
                ]
            }
        }
    }

    payload = {
        "replyToken": reply_token,
        "messages": [flex]
    }
    try:
        requests.post("https://api.line.me/v2/bot/message/reply", headers=LINE_HEADERS, data=json.dumps(payload))
    except Exception as e:
        logger.error(f"send_time_selection_flex error: {e}")

def send_user_reservations_flex(reply_token: str, reservations: list):
    """ส่งรายการการจองของผู้ใช้"""
    if not reservations:
        reply_to_user(reply_token, "ไม่พบการจองของคุณในระบบ")
        return
    
    contents = []
    for i, res in enumerate(reservations[:5]):  # แสดงสูงสุด 5 รายการ
        data = res["data"]
        booking_id = data.get("ID การจอง", "ไม่ระบุ")
        contents.append({
            "type": "box",
            "layout": "vertical",
            "spacing": "sm",
            "paddingAll": "md",
            "backgroundColor": "#f8f9fa",
            "cornerRadius": "md",
            "contents": [
                {
                    "type": "text",
                    "text": f"🎫 ID: {booking_id}",
                    "weight": "bold",
                    "size": "md",
                    "color": "#2d5016"
                },
                {
                    "type": "text",
                    "text": f"📅 {data['วันที่']} ⏰ {data['เวลา']}",
                    "size": "sm",
                    "color": "#333333"
                },
                {
                    "type": "text",
                    "text": f"👥 {data['จำนวนคน']} คน",
                    "size": "sm",
                    "color": "#666666"
                },
                {
                    "type": "button",
                    "action": {
                        "type": "message",
                        "label": "ยกเลิกการจองนี้",
                        "text": f"ยกเลิก:{data['วันที่']}:{data['เวลา']}"
                    },
                    "style": "primary",
                    "color": "#dc3545",
                    "height": "sm"
                }
            ]
        })
        
        if i < len(reservations) - 1:
            contents.append({"type": "separator", "margin": "md"})
    
    flex = {
        "type": "flex",
        "altText": "รายการการจองของคุณ",
        "contents": {
            "type": "bubble",
            "size": "mega",
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "md",
                "contents": [
                    {
                        "type": "text",
                        "text": "📋 รายการการจองของคุณ",
                        "weight": "bold",
                        "size": "xl",
                        "color": "#2d5016",
                        "align": "center"
                    },
                    {
                        "type": "separator",
                        "margin": "md",
                        "color": "#2d5016"
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "spacing": "md",
                        "margin": "lg",
                        "contents": contents
                    }
                ]
            }
        }
    }
    
    payload = {
        "replyToken": reply_token,
        "messages": [flex]
    }
    try:
        requests.post("https://api.line.me/v2/bot/message/reply", headers=LINE_HEADERS, data=json.dumps(payload))
    except Exception as e:
        logger.error(f"send_user_reservations_flex error: {e}")

def send_timeout_warning_flex(user_id: str):
    """ส่งข้อความเตือน timeout พร้อมปุ่มเลือก"""
    flex_message = {
        "type": "flex",
        "altText": "ขั้นตอนการจองหมดเวลา",
        "contents": {
            "type": "bubble",
            "styles": {
                "body": {
                    "backgroundColor": "#fff3cd"
                }
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "md",
                "contents": [
                    {
                        "type": "text",
                        "text": "⏰ ขั้นตอนการจองหมดเวลา",
                        "weight": "bold",
                        "size": "xl",
                        "color": "#856404",
                        "align": "center"
                    },
                    {
                        "type": "separator",
                        "margin": "md",
                        "color": "#856404"
                    },
                    {
                        "type": "text",
                        "text": "คุณใช้เวลาในการจองนานเกินไป\nต้องการทำขั้นตอนการจองต่อหรือไม่?",
                        "size": "md",
                        "color": "#333333",
                        "align": "center",
                        "wrap": True,
                        "margin": "lg"
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "spacing": "sm",
                        "margin": "lg",
                        "contents": [
                            {
                                "type": "button",
                                "action": {
                                    "type": "message",
                                    "label": "✅ ทำต่อ",
                                    "text": "ทำต่อการจอง"
                                },
                                "style": "primary",
                                "color": "#28a745",
                                "height": "sm"
                            },
                            {
                                "type": "button",
                                "action": {
                                    "type": "message",
                                    "label": "❌ ยกเลิกขั้นตอนการจอง",
                                    "text": "ยกเลิกขั้นตอนการจอง"
                                },
                                "style": "secondary",
                                "color": "#dc3545",
                                "height": "sm",
                                "margin": "sm"
                            }
                        ]
                    },
                    {
                        "type": "text",
                        "text": "หากไม่เลือกภายใน 2 นาที\nระบบจะยกเลิกขั้นตอนการจองอัตโนมัติ",
                        "size": "xs",
                        "color": "#666666",
                        "align": "center",
                        "wrap": True,
                        "margin": "lg"
                    }
                ]
            }
        }
    }
    
    # ส่งข้อความไปยัง user โดยใช้ push message
    payload = {
        "to": user_id,
        "messages": [flex_message]
    }
    
    try:
        requests.post("https://api.line.me/v2/bot/message/push", headers=LINE_HEADERS, data=json.dumps(payload))
    except Exception as e:
        logger.error(f"send_timeout_warning_flex error: {e}")

def send_admin_notification(user_id: str, message_text: str, display_name: str):
    """ส่งข้อความแจ้งแอดมินเมื่อมีลูกค้าพิมพ์คุยระหว่างการจอง"""
    # ดึง Admin User ID หรือ Group ID จาก environment
    ADMIN_USER_ID = os.getenv("ADMIN_USER_ID")  # เพิ่มใน .env
    ADMIN_GROUP_ID = os.getenv("ADMIN_GROUP_ID")  # เพิ่มใน .env (ถ้าใช้ group)
    
    if not ADMIN_USER_ID and not ADMIN_GROUP_ID:
        # ถ้าไม่มี Admin ID ให้ log ไว้อย่างเดียว
        logger.info(f"Customer {display_name} ({user_id}) sent message during booking: {message_text}")
        return
    
    # สร้างข้อความแจ้งแอดมิน
    admin_message = {
        "type": "flex",
        "altText": f"ลูกค้า {display_name} ส่งข้อความระหว่างการจอง",
        "contents": {
            "type": "bubble",
            "styles": {
                "body": {
                    "backgroundColor": "#e3f2fd"
                }
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "md",
                "contents": [
                    {
                        "type": "text",
                        "text": "💬 ข้อความจากลูกค้า",
                        "weight": "bold",
                        "size": "lg",
                        "color": "#1565c0",
                        "align": "center"
                    },
                    {
                        "type": "separator",
                        "margin": "md",
                        "color": "#1565c0"
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "spacing": "sm",
                        "margin": "lg",
                        "contents": [
                            {
                                "type": "box",
                                "layout": "baseline",
                                "contents": [
                                    {
                                        "type": "text",
                                        "text": "👤 ชื่อ:",
                                        "size": "sm",
                                        "color": "#666666",
                                        "flex": 2
                                    },
                                    {
                                        "type": "text",
                                        "text": display_name,
                                        "size": "sm",
                                        "color": "#333333",
                                        "flex": 5,
                                        "weight": "bold"
                                    }
                                ]
                            },
                            {
                                "type": "box",
                                "layout": "baseline",
                                "contents": [
                                    {
                                        "type": "text",
                                        "text": "🆔 User ID:",
                                        "size": "sm",
                                        "color": "#666666",
                                        "flex": 2
                                    },
                                    {
                                        "type": "text",
                                        "text": user_id,
                                        "size": "xs",
                                        "color": "#333333",
                                        "flex": 5
                                    }
                                ]
                            },
                            {
                                "type": "separator",
                                "margin": "md"
                            },
                            {
                                "type": "text",
                                "text": "💬 ข้อความ:",
                                "size": "sm",
                                "color": "#666666",
                                "margin": "md"
                            },
                            {
                                "type": "text",
                                "text": message_text,
                                "size": "md",
                                "color": "#333333",
                                "wrap": True,
                                "backgroundColor": "#f5f5f5",
                                "paddingAll": "sm",
                                "cornerRadius": "md",
                                "margin": "sm"
                            }
                        ]
                    },
                    {
                        "type": "separator",
                        "margin": "lg"
                    },
                    {
                        "type": "text",
                        "text": "📋 ลูกค้าอยู่ระหว่างขั้นตอนการจองโต๊ะ",
                        "size": "xs",
                        "color": "#666666",
                        "align": "center",
                        "margin": "md"
                    }
                ]
            }
        }
    }
    
    # ตัดสินใจส่งไปยัง Admin User หรือ Group
    target_id = ADMIN_GROUP_ID if ADMIN_GROUP_ID else ADMIN_USER_ID
    
    payload = {
        "to": target_id,
        "messages": [admin_message]
    }
    
    try:
        response = requests.post("https://api.line.me/v2/bot/message/push", headers=LINE_HEADERS, data=json.dumps(payload))
        if response.status_code == 200:
            logger.info(f"Admin notification sent successfully for customer {display_name}")
        else:
            logger.error(f"Failed to send admin notification: {response.status_code}")
    except Exception as e:
        logger.error(f"send_admin_notification error: {e}")
        # Fallback เป็น log
        logger.info(f"Customer {display_name} ({user_id}) sent message during booking: {message_text}")