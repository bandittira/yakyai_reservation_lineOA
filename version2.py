from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import json
import hashlib
import hmac
import base64
from datetime import datetime, date, timedelta
import asyncio
from typing import Dict, Optional
import logging
from pydantic import BaseModel
import gspread
from google.oauth2.service_account import Credentials
import os
import requests
from googleapiclient.discovery import build
from google.oauth2 import service_account
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Webhook จองโต๊ะร้านยักษ์ใหญ่แดนใต้", version="1.0.0")

LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")
SHARE_EMAIL = os.getenv("SHARE_EMAIL")

LINE_HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
}

user_sessions: Dict[str, Dict] = {}

def get_google_sheets_client():
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_file(GOOGLE_CREDENTIALS_FILE, scopes=scope)
    return gspread.authorize(creds)

gc = get_google_sheets_client()

def move_to_drive_folder_and_share(file_id: str, folder_id: str, share_email: Optional[str] = None):
    creds = service_account.Credentials.from_service_account_file(
        GOOGLE_CREDENTIALS_FILE,
        scopes=["https://www.googleapis.com/auth/drive"]
    )
    service = build('drive', 'v3', credentials=creds)
    file = service.files().get(fileId=file_id, fields='parents').execute()
    previous_parents = ",".join(file.get('parents', []))
    service.files().update(
        fileId=file_id,
        addParents=folder_id,
        removeParents=previous_parents,
        fields='id, parents'
    ).execute()
    if share_email:
        permission = {
            'type': 'user',
            'role': 'writer',
            'emailAddress': share_email
        }
        service.permissions().create(
            fileId=file_id,
            body=permission,
            sendNotificationEmail=False
        ).execute()

class ReservationData(BaseModel):
    customer_name: str
    phone: str
    date: str
    time: str
    party_size: int
    special_requests: Optional[str] = ""
    line_display_name: str
    timestamp: datetime

class LineWebhookEvent(BaseModel):
    type: str
    message: Optional[Dict] = None
    source: Dict
    timestamp: int
    replyToken: Optional[str] = None

def verify_line_signature(body: bytes, signature: str) -> bool:
    digest = hmac.new(LINE_CHANNEL_SECRET.encode(), body, hashlib.sha256).digest()
    expected_signature = base64.b64encode(digest).decode()
    return hmac.compare_digest(expected_signature, signature)

def is_inquiry_message(text: str) -> bool:
    keywords = [
        "จองโต๊ะ", "ขอจอง", "จะจอง", "จองได้ไหม", "อยากจอง", "ขอจองโต๊ะ",
        "มีโต๊ะไหม", "มีที่นั่งไหม", "จองยังไง", "จองเลย"
    ]
    return any(keyword in text for keyword in keywords)

def is_cancel_message(text: str) -> bool:
    keywords = [
        "ยกเลิกการจอง", "ยกเลิกจอง", "ขอยกเลิก", "ไม่ไป", "ยกเลิก", 
        "cancel", "ยกเลิกการจองโต๊ะ", "ขอยกเลิกการจอง"
    ]
    return any(keyword in text for keyword in keywords)

def start_reservation_session(user_id: str):
    user_sessions[user_id] = {"step": "name", "data": {}}

def start_cancellation_session(user_id: str):
    user_sessions[user_id] = {"step": "cancel_phone", "data": {}}

def clear_reservation_session(user_id: str):
    user_sessions.pop(user_id, None)

def parse_reservation_message(message_text: str) -> Optional[Dict]:
    if not message_text.startswith("จองโต๊ะ:"):
        return None
    try:
        data = message_text[8:].strip().split(',')
        if len(data) < 5:
            return None
        return {
            'customer_name': data[0].strip(),
            'phone': data[1].strip(),
            'date': data[2].strip(),
            'time': data[3].strip(),
            'party_size': int(data[4].strip()),
            'special_requests': data[5].strip() if len(data) > 5 else ""
        }
    except:
        return None

def get_line_display_name(user_id: str) -> str:
    try:
        response = requests.get(f"https://api.line.me/v2/bot/profile/{user_id}", headers=LINE_HEADERS)
        if response.status_code == 200:
            return response.json().get("displayName", user_id)
    except:
        pass
    return user_id

def get_or_create_daily_sheet(target_date: date):
    title = f"จองโต๊ะ_{target_date.strftime('%Y-%m-%d')}"
    try:
        try:
            sheet = gc.open(title)
            move_to_drive_folder_and_share(sheet.id, GOOGLE_DRIVE_FOLDER_ID, SHARE_EMAIL)
            return sheet.sheet1
        except gspread.SpreadsheetNotFound:
            sh = gc.create(title)
            sh.sheet1.append_row([
                "เวลาจอง", "ชื่อลูกค้า", "เบอร์โทร", "วันที่", "เวลา",
                "จำนวนคน", "คำขอเพิ่มเติม", "LINE DISPLAY NAME", "สถานะ"
            ])
            move_to_drive_folder_and_share(sh.id, GOOGLE_DRIVE_FOLDER_ID, SHARE_EMAIL)
            return sh.sheet1
    except:
        return None

def reservation_exists(ws, date, time, phone):
    try:
        records = ws.get_all_records()
        for row in records:
            if row["เบอร์โทร"] == phone and row["วันที่"] == date and row["เวลา"] == time:
                return True
    except:
        pass
    return False

def find_user_reservations(phone: str, target_date: date = None):
    """ค้นหาการจองของผู้ใช้ตามเบอร์โทร"""
    reservations = []
    try:
        # ค้นหาใน 7 วันข้างหน้า
        for i in range(7):
            check_date = (target_date or datetime.today().date()) + timedelta(days=i)
            ws = get_or_create_daily_sheet(check_date)
            if ws:
                records = ws.get_all_records()
                for idx, row in enumerate(records, start=2):  # เริ่มจากแถวที่ 2 (ข้าม header)
                    if row["เบอร์โทร"] == phone and row["สถานะ"] not in ["ยกเลิก", "ยกเลิกแล้ว"]:
                        reservations.append({
                            "row_index": idx,
                            "worksheet": ws,
                            "data": row,
                            "date": check_date
                        })
    except Exception as e:
        logger.error(f"find_user_reservations error: {e}")
    return reservations

def cancel_reservation(phone: str, date_str: str, time_str: str):
    """ยกเลิกการจอง"""
    try:
        # แปลงวันที่
        day, month, year = map(int, date_str.split('-'))
        if year > 2500:
            year -= 543
        target_date = date(year, month, day)
        
        ws = get_or_create_daily_sheet(target_date)
        if not ws:
            return False, "ไม่พบข้อมูลการจอง"
        
        records = ws.get_all_records()
        for idx, row in enumerate(records, start=2):
            if (row["เบอร์โทร"] == phone and 
                row["วันที่"] == date_str and 
                row["เวลา"] == time_str and 
                row["สถานะ"] not in ["ยกเลิก", "ยกเลิกแล้ว"]):
                
                # อัพเดทสถานะเป็นยกเลิก
                ws.update_cell(idx, 9, "ยกเลิกแล้ว")  # คอลัมน์ "สถานะ"
                return True, f"ยกเลิกการจองสำเร็จ\nวันที่: {date_str} เวลา: {time_str}"
        
        return False, "ไม่พบการจองที่ต้องการยกเลิก"
    except Exception as e:
        logger.error(f"cancel_reservation error: {e}")
        return False, "เกิดข้อผิดพลาดในการยกเลิกการจอง"

def add_reservation_to_sheet(res: ReservationData):
    try:
        day, month, year = map(int, res.date.split('-'))
        year -= 543 if year > 2500 else 0
        res_date = date(year, month, day)
    except:
        return False, "รูปแบบวันที่ไม่ถูกต้อง กรุณาใส่วันที่เช่น 26-06-2567"

    if (res_date - datetime.today().date()).days > 7:
        return False, "สามารถจองล่วงหน้าได้ไม่เกิน 7 วันค่ะ"

    ws = get_or_create_daily_sheet(res_date)
    if not ws:
        return False, "เกิดข้อผิดพลาด กรุณาลองใหม่อีกครั้งค่ะ"

    if reservation_exists(ws, res.date, res.time, res.phone):
        return False, "ลูกค้าได้ทำการจองไว้แล้วค่ะ"

    try:
        ws.append_row([
            res.timestamp.strftime('%Y-%m-%d %H:%M:%S'), res.customer_name, res.phone,
            res.date, res.time, res.party_size, res.special_requests, res.line_display_name, "รอเช็ค"
        ])
        return True, "จองสำเร็จ"
    except:
        return False, "ไม่สามารถบันทึกข้อมูลได้"

def send_flex_confirmation(reply_token: str, res: ReservationData):
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
                            },
                            {
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
    requests.post("https://api.line.me/v2/bot/message/reply", headers=LINE_HEADERS, data=json.dumps(payload))

def send_date_selection_flex(reply_token: str):
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
                "label": display_date[:20],  # ป้องกัน label ยาวเกิน
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

    # แบ่งปุ่มเป็น 3 คอลัมน์
    button_boxes = []
    for i in range(0, len(buttons), 3):
        row_buttons = buttons[i:i+3]
        button_boxes.append({
            "type": "box",
            "layout": "horizontal",
            "spacing": "sm",
            "contents": row_buttons
        })

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
                        "contents": button_boxes
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
                    "text": f"การจอง #{i+1}",
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

@app.post("/webhook")
async def webhook(request: Request):
    body = await request.body()
    signature = request.headers.get("X-Line-Signature", "")
    if not verify_line_signature(body, signature):
        raise HTTPException(status_code=400, detail="Invalid signature")
    payload = json.loads(body)
    for event in payload.get("events", []):
        await process_line_event(event)
    return {"status": "ok"}

def reply_to_user(reply_token: str, message: str):
    payload = {
        "replyToken": reply_token,
        "messages": [{"type": "text", "text": message}]
    }
    try:
        requests.post("https://api.line.me/v2/bot/message/reply", headers=LINE_HEADERS, data=json.dumps(payload))
    except Exception as e:
        logger.error(f"reply_to_user error: {e}")

async def process_line_event(event_data: Dict):
    try:
        event = LineWebhookEvent(**event_data)
        if event.type != "message" or event.message.get("type") != "text":
            return

        message_text = event.message.get("text", "").strip()
        user_id = event.source.get("userId", "")
        reply_token = event.replyToken

        # ตรวจสอบคำสั่งยกเลิกการจอง
        if message_text.startswith("ยกเลิก:"):
            try:
                parts = message_text.split(":")
                if len(parts) == 3:
                    date_str = parts[1]
                    time_str = parts[2]
                    
                    # ต้องการเบอร์โทรเพื่อยืนยันการยกเลิก
                    start_cancellation_session(user_id)
                    user_sessions[user_id]["data"]["cancel_date"] = date_str
                    user_sessions[user_id]["data"]["cancel_time"] = time_str
                    reply_to_user(reply_token, f"กรุณายืนยันการยกเลิกการจอง\nวันที่: {date_str} เวลา: {time_str}\n\nกรุณาใส่เบอร์โทรที่ใช้จองค่ะ")
                    return
            except:
                reply_to_user(reply_token, "รูปแบบการยกเลิกไม่ถูกต้อง")
                return

        # ตรวจสอบข้อความขอยกเลิกการจอง
        if is_cancel_message(message_text) and user_id not in user_sessions:
            start_cancellation_session(user_id)
            reply_to_user(reply_token, "กรุณาใส่เบอร์โทรที่ใช้จองเพื่อค้นหาการจองของคุณค่ะ")
            return

        # ตรวจสอบข้อความขอจองโต๊ะ
        if is_inquiry_message(message_text) and user_id not in user_sessions:
            start_reservation_session(user_id)
            
            # ส่งข้อความรายละเอียดการจองก่อน
            reservation_info = (
                "🏮 ยินดีต้อนรับสู่ร้านยักษ์ใหญ่แดนใต้\n\n"
                "📋 รายละเอียดการจอง:\n"
                "⏰ เวลาให้บริการ: 18:30 - 21:30 น.\n"
                "📅 จองล่วงหน้าได้ไม่เกิน 7 วัน\n"
                "👥 รองรับ 1-20 คน\n"
                "❌ เมื่อเกินเวลาจองจะยกเลิกการจองทันที\n\n"
                "🔄 เริ่มขั้นตอนการจอง...\n"
                "ขอชื่อผู้จองค่ะ"
            )
            reply_to_user(reply_token, reservation_info)
            return

        # จัดการ session ต่างๆ
        if user_id in user_sessions:
            session = user_sessions[user_id]
            step = session["step"]
            data = session["data"]

            # Session สำหรับการยกเลิกจอง
            if step == "cancel_phone":
                phone = message_text.strip()
                reservations = find_user_reservations(phone)
                
                if not reservations:
                    clear_reservation_session(user_id)
                    reply_to_user(reply_token, "ไม่พบการจองของเบอร์นี้ในระบบค่ะ")
                    return
                
                # ถ้ามีการระบุวันที่และเวลาเฉพาะ (จากการกดปุ่มยกเลิก)
                if "cancel_date" in data and "cancel_time" in data:
                    success, msg = cancel_reservation(phone, data["cancel_date"], data["cancel_time"])
                    clear_reservation_session(user_id)
                    reply_to_user(reply_token, msg)
                    return
                
                # แสดงรายการการจองทั้งหมด
                clear_reservation_session(user_id)
                send_user_reservations_flex(reply_token, reservations)
                return

            # Session สำหรับการจองโต๊ะ
            elif step == "name":
                data["customer_name"] = message_text
                session["step"] = "phone"
                reply_to_user(reply_token, "ขอเบอร์โทรค่ะ 📞")
            elif step == "phone":
                data["phone"] = message_text
                session["step"] = "date"
                send_date_selection_flex(reply_token)
            elif step == "date":
                data["date"] = message_text
                session["step"] = "time"
                send_time_selection_flex(reply_token)
            elif step == "time":
                data["time"] = message_text
                session["step"] = "party_size"
                reply_to_user(reply_token, "จำนวนคนค่ะ 👥")
            elif step == "party_size":
                try:
                    party_size = int(message_text)
                    if party_size <= 0:
                        reply_to_user(reply_token, "กรุณาระบุจำนวนคนมากกว่า 0 ค่ะ")
                        return
                    if party_size > 20:
                        reply_to_user(reply_token, "จำนวนคนเกิน 20 คน กรุณาติดต่อร้านโดยตรงค่ะ")
                        return
                    data["party_size"] = party_size
                    session["step"] = "special_requests"
                    reply_to_user(reply_token, "มีคำขอเพิ่มเติมไหมคะ (เช่น โต๊ะริมหน้าต่าง, อาหารแพ้)\nถ้าไม่มี พิมพ์ - ค่ะ")
                except ValueError:
                    reply_to_user(reply_token, "กรุณาระบุจำนวนคนเป็นตัวเลขค่ะ")
            elif step == "special_requests":
                data["special_requests"] = message_text if message_text != "-" else ""
                line_name = get_line_display_name(user_id)
                reservation = ReservationData(
                    **data,
                    line_display_name=line_name,
                    timestamp=datetime.now()
                )
                success, msg = add_reservation_to_sheet(reservation)
                clear_reservation_session(user_id)

                if success:
                    send_flex_confirmation(reply_token, reservation)
                else:
                    reply_to_user(reply_token, msg)
            return

# จัดการข้อความรูปแบบเก่า (เฉพาะที่ขึ้นต้นด้วย "จองโต๊ะ:")
        parsed = parse_reservation_message(message_text)
        if parsed:
            res = ReservationData(
                **parsed,
                line_display_name=get_line_display_name(user_id),
                timestamp=datetime.now()
            )
            success, msg = add_reservation_to_sheet(res)
            if reply_token:
                if success:
                    send_flex_confirmation(reply_token, res)
                else:
                    reply_to_user(reply_token, msg)
            return

        # ตอบกลับเฉพาะข้อความที่เป็นคำถามหรือต้องการความช่วยเหลือ
        help_keywords = [
            "จอง","ขอวิธีจอง","วิธีการจอง","วิธีจอง","จองยังไง","จองได้ไหม"
        ]
        
        if any(keyword in message_text.lower() for keyword in help_keywords) and reply_token:
            # ข้อความช่วยเหลือสำหรับคำถามทั่วไป
            simple_help = (
                "สวัสดีค่ะ! 😊\n\n"
                "📝 พิมพ์ 'จองโต๊ะ' เพื่อจองโต๊ะ\n"
                "❌ พิมพ์ 'ยกเลิกการจอง' เพื่อยกเลิกการจอง\n\n"
                "🕐 เวลาให้บริการ: 18:30 - 21:30 น.\n"
                "📅 จองล่วงหน้าได้ไม่เกิน 7 วัน\n\n"
                "สอบถามรายละเอียดเพิ่มเติมได้เลยค่ะ"
            )
            reply_to_user(reply_token, simple_help)
    except Exception as e:
        logger.error(f"process_line_event error: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)