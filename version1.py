from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import json
import hashlib
import hmac
import base64
from datetime import datetime, date
import asyncio
from typing import Dict, Optional
import logging
from pydantic import BaseModel
import gspread
from google.oauth2.service_account import Credentials
import os
from pathlib import Path
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

def get_google_sheets_client():
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    try:
        creds = Credentials.from_service_account_file(GOOGLE_CREDENTIALS_FILE, scopes=scope)
        return gspread.authorize(creds)
    except Exception as e:
        logger.error(f"Google Sheets client error: {e}")
        return None

gc = get_google_sheets_client()

def move_to_drive_folder_and_share(file_id: str, folder_id: str, share_email: Optional[str] = None):
    try:
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
    except Exception as e:
        logger.error(f"Move/Share error: {e}")

class ReservationData(BaseModel):
    customer_name: str
    display_name: str
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
    if not LINE_CHANNEL_SECRET:
        logger.warning("LINE_CHANNEL_SECRET ไม่ถูกตั้งค่า")
        return False
    digest = hmac.new(LINE_CHANNEL_SECRET.encode(), body, hashlib.sha256).digest()
    expected_signature = base64.b64encode(digest).decode()
    return hmac.compare_digest(expected_signature, signature)

def parse_reservation_message(message_text: str) -> Optional[Dict]:
    if not message_text.startswith("จองโต๊ะ:"):
        return None
    try:
        data = message_text[8:].strip().split(',')
        if len(data) < 6:
            return None
        return {
            'customer_name': data[0].strip(),
            'display_name': data[1].strip(),
            'phone': data[2].strip(),
            'date': data[3].strip(),
            'time': data[4].strip(),
            'party_size': int(data[5].strip()),
            'special_requests': data[6].strip() if len(data) > 6 else ""
        }
    except Exception as e:
        logger.error(f"Parse error: {e}")
        return None

def get_line_display_name(user_id: str) -> str:
    try:
        response = requests.get(
            f"https://api.line.me/v2/bot/profile/{user_id}",
            headers=LINE_HEADERS
        )
        if response.status_code == 200:
            return response.json().get("displayName", user_id)
        else:
            logger.warning(f"Failed to get LINE profile: {response.status_code}")
    except Exception as e:
        logger.error(f"get_line_display_name error: {e}")
    return user_id

def get_or_create_daily_sheet(target_date: date):
    title = f"จองโต๊ะ_{target_date.strftime('%Y-%m-%d')}"
    try:
        try:
            sheet = gc.open(title)
            if GOOGLE_DRIVE_FOLDER_ID:
                move_to_drive_folder_and_share(sheet.id, GOOGLE_DRIVE_FOLDER_ID, SHARE_EMAIL)
            return sheet.sheet1
        except gspread.SpreadsheetNotFound:
            sh = gc.create(title)
            sh.sheet1.append_row([
                "เวลาจอง", "ชื่อลูกค้า", "ชื่อสำหรับเรียกหน้าร้าน", "เบอร์โทร", "วันที่", "เวลา",
                "จำนวนคน", "คำขอเพิ่มเติม", "LINE DISPLAY NAME", "สถานะ"
            ])
            if GOOGLE_DRIVE_FOLDER_ID:
                move_to_drive_folder_and_share(sh.id, GOOGLE_DRIVE_FOLDER_ID, SHARE_EMAIL)
            return sh.sheet1
    except Exception as e:
        logger.error(f"Sheet error: {e}")
        return None

def reservation_exists(ws, date, time, phone):
    try:
        records = ws.get_all_records()
        for row in records:
            if row["เบอร์โทร"] == phone and row["วันที่"] == date and row["เวลา"] == time:
                return True
    except Exception as e:
        logger.error(f"Check duplicate error: {e}")
    return False

def add_reservation_to_sheet(res: ReservationData):
    try:
        res_date = datetime.strptime(res.date, '%Y-%m-%d').date()
    except ValueError:
        return False, "รูปแบบวันที่ไม่ถูกต้อง กรุณาใส่วันที่ตามตัวอย่าง 1-1-2568"

    if (res_date - datetime.today().date()).days > 7:
        return False, "ทางร้านขอสงวนสิทธิ์ สามารถจองล่วงหน้าได้ไม่เกิน 7 วันค่ะ"

    ws = get_or_create_daily_sheet(res_date)
    if not ws:
        return False, "ไม่สามารถจองได้ ทาเราจะติดต่อกลับอย่างเร็วที่สุดค่ะ"

    if reservation_exists(ws, res.date, res.time, res.phone):
        return False, "ลูกค้าได้ทำการจองไว้แล้วค่ะ"

    try:
        ws.append_row([
            res.timestamp.strftime('%Y-%m-%d %H:%M:%S'), res.customer_name, res.display_name, res.phone,
            res.date, res.time, res.party_size, res.special_requests, res.line_display_name, "รอเช็ค"
        ])
        return True, "จองสำเร็จ"
    except Exception as e:
        logger.error(f"Append error: {e}")
        return False, "บันทึกข้อมูลล้มเหลว"

def send_flex_confirmation(reply_token: str, res: ReservationData):
    flex_message = {
        "type": "flex",
        "altText": "ยืนยันการจองโต๊ะ",
        "contents": {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {"type": "text", "text": "📌 ยืนยันการจองโต๊ะ", "weight": "bold", "size": "lg"},
                    {"type": "separator", "margin": "md"},
                    {"type": "text", "text": f"ชื่อ: {res.customer_name}"},
                    {"type": "text", "text": f"ชื่อเรียก: {res.display_name}"},
                    {"type": "text", "text": f"เบอร์: {res.phone}"},
                    {"type": "text", "text": f"วันที่: {res.date} เวลา: {res.time}"},
                    {"type": "text", "text": f"จำนวน: {res.party_size} คน"},
                    {"type": "text", "text": f"เพิ่มเติม: {res.special_requests or '-'}"},
                ]
            }
        }
    }
    payload = {
        "replyToken": reply_token,
        "messages": [flex_message]
    }
    try:
        requests.post("https://api.line.me/v2/bot/message/reply", headers=LINE_HEADERS, data=json.dumps(payload))
    except Exception as e:
        logger.error(f"Flex reply error: {e}")

@app.post("/webhook")
async def webhook(request: Request):
    body = await request.body()
    signature = request.headers.get("X-Line-Signature", "")
    if not verify_line_signature(body, signature):
        raise HTTPException(status_code=400, detail="ลายเซ็นไม่ถูกต้อง")
    try:
        payload = json.loads(body)
        for event in payload.get("events", []):
            await process_line_event(event)
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        raise HTTPException(status_code=500, detail="Webhook error")

async def process_line_event(event_data: Dict):
    try:
        event = LineWebhookEvent(**event_data)
        if event.type != "message" or event.message.get("type") != "text":
            return

        message_text = event.message.get("text", "")
        parsed = parse_reservation_message(message_text)
        if not parsed:
            if event.replyToken:
                reply_to_user(event.replyToken, "พิมพ์ตามนี้นะครับ: จองโต๊ะ: ชื่อจริง, ชื่อเรียก, เบอร์โทร, วันที่, เวลา, จำนวนคน, เพิ่มเติม")
            return

        user_id = event.source.get("userId", "")
        display_name_from_line = get_line_display_name(user_id)

        res = ReservationData(
            **parsed,
            line_display_name=display_name_from_line,
            timestamp=datetime.now()
        )

        success, message = add_reservation_to_sheet(res)
        if event.replyToken:
            if success:
                send_flex_confirmation(event.replyToken, res)
            else:
                reply_to_user(event.replyToken, message)

    except Exception as e:
        logger.error(f"process_line_event error: {e}")

def reply_to_user(reply_token: str, message: str):
    payload = {
        "replyToken": reply_token,
        "messages": [{"type": "text", "text": message}]
    }
    try:
        requests.post("https://api.line.me/v2/bot/message/reply", headers=LINE_HEADERS, data=json.dumps(payload))
    except Exception as e:
        logger.error(f"Reply error: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)