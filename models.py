from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any, List
from datetime import datetime
from utils import generate_booking_id

class LineMessage(BaseModel):
    """LINE Message model"""
    id: str
    type: str
    text: Optional[str] = None

class LineSource(BaseModel):
    """LINE Source model"""
    type: str
    userId: Optional[str] = None
    groupId: Optional[str] = None
    roomId: Optional[str] = None

class LineWebhookEvent(BaseModel):
    """LINE Webhook Event model"""
    type: str
    mode: Optional[str] = None
    timestamp: Optional[int] = None
    source: Optional[Dict[str, Any]] = None
    webhookEventId: Optional[str] = None
    deliveryContext: Optional[Dict[str, Any]] = None
    message: Optional[Dict[str, Any]] = None
    replyToken: Optional[str] = None
    
    class Config:
        extra = "allow"  # อนุญาตให้มี field เพิ่มเติม

class ReservationData(BaseModel):
    """ข้อมูลการจอง"""
    customer_name: str = Field(..., min_length=2, max_length=50, description="ชื่อผู้จอง")
    phone: str = Field(..., pattern=r'^0\d{9}$', description="เบอร์โทรศัพท์ 10 หลัก")
    date: str = Field(..., pattern=r'^\d{1,2}-\d{1,2}-\d{4}$', description="วันที่ รูปแบบ dd-mm-yyyy")
    time: str = Field(..., pattern=r'^\d{1,2}:\d{2}$', description="เวลา รูปแบบ HH:MM")
    party_size: int = Field(..., ge=1, le=20, description="จำนวนคน 1-20")
    special_requests: Optional[str] = Field(None, max_length=200, description="ความต้องการพิเศษ")
    booking_id: Optional[str] = Field(default_factory=generate_booking_id, description="รหัสการจอง")
    user_id: Optional[str] = Field(None, description="LINE User ID")
    line_display_name: Optional[str] = Field(None, description="ชื่อ LINE Display")
    timestamp: Optional[datetime] = Field(default_factory=datetime.now, description="เวลาที่จอง")
    status: str = Field(default="confirmed", description="สถานะการจอง")
    
    @validator('phone')
    def validate_phone(cls, v):
        """ตรวจสอบเบอร์โทรศัพท์"""
        clean_phone = v.replace('-', '').replace(' ', '')
        if not clean_phone.startswith('0') or len(clean_phone) != 10:
            raise ValueError('เบอร์โทรศัพท์ต้องเป็น 10 หลัก เริ่มต้นด้วย 0')
        return clean_phone
    
    @validator('date')
    def validate_date(cls, v):
        """ตรวจสอบรูปแบบวันที่"""
        try:
            parts = v.split('-')
            if len(parts) != 3:
                raise ValueError('รูปแบบวันที่ไม่ถูกต้อง')
            
            day, month, year = map(int, parts)
            
            if not (1 <= day <= 31):
                raise ValueError('วันที่ไม่ถูกต้อง')
            if not (1 <= month <= 12):
                raise ValueError('เดือนไม่ถูกต้อง')
            if not (2500 <= year <= 2600):  # พ.ศ.
                raise ValueError('ปีไม่ถูกต้อง')
                
            return v
        except (ValueError, AttributeError):
            raise ValueError('รูปแบบวันที่ไม่ถูกต้อง (dd-mm-yyyy)')
    
    @validator('time')
    def validate_time(cls, v):
        """ตรวจสอบรูปแบบเวลา"""
        try:
            hour, minute = map(int, v.split(':'))
            if not (0 <= hour <= 23):
                raise ValueError('ชั่วโมงไม่ถูกต้อง')
            if not (0 <= minute <= 59):
                raise ValueError('นาทีไม่ถูกต้อง')
            
            # ตรวจสอบเวลาทำการ (18:30 - 21:30)
            time_minutes = hour * 60 + minute
            start_minutes = 18 * 60 + 30  # 18:30
            end_minutes = 21 * 60 + 30    # 21:30
            
            if not (start_minutes <= time_minutes <= end_minutes):
                raise ValueError('เวลาต้องอยู่ระหว่าง 18:30 - 21:30 น.')
                
            return v
        except (ValueError, AttributeError):
            raise ValueError('รูปแบบเวลาไม่ถูกต้อง (HH:MM)')

class BookingSession(BaseModel):
    """Session ข้อมูลการจอง"""
    user_id: str
    step: str
    data: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None

class BookingResponse(BaseModel):
    """Response สำหรับการจอง"""
    success: bool
    message: str
    booking_id: Optional[str] = None
    data: Optional[ReservationData] = None

class CancellationRequest(BaseModel):
    """คำขอยกเลิกการจอง"""
    phone: str = Field(..., pattern=r'^0\d{9}$')
    date: Optional[str] = Field(None, pattern=r'^\d{1,2}-\d{1,2}-\d{4}$')
    time: Optional[str] = Field(None, pattern=r'^\d{1,2}:\d{2}$')
    booking_id: Optional[str] = None

class CancellationResponse(BaseModel):
    """Response สำหรับการยกเลิกการจอง"""
    success: bool
    message: str
    cancelled_reservations: Optional[List[Dict[str, Any]]] = None

class UserReservation(BaseModel):
    """ข้อมูลการจองของผู้ใช้"""
    booking_id: str
    customer_name: str
    phone: str
    date: str
    time: str
    party_size: int
    special_requests: Optional[str] = None
    status: str = "confirmed"
    created_at: datetime

class AdminNotification(BaseModel):
    """การแจ้งเตือนแอดมิน"""
    user_id: str
    display_name: str
    message_text: str
    event_type: str
    timestamp: datetime = Field(default_factory=datetime.now)

class APIResponse(BaseModel):
    """Standard API Response"""
    success: bool
    message: str
    data: Optional[Any] = None
    error_code: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)

class HealthCheckResponse(BaseModel):
    """Health Check Response"""
    status: str = "OK"
    timestamp: datetime = Field(default_factory=datetime.now)
    version: str
    uptime: Optional[float] = None
    services: Optional[Dict[str, str]] = None

class WebhookValidation(BaseModel):
    """Webhook signature validation"""
    body: bytes
    signature: str
    
    class Config:
        arbitrary_types_allowed = True

# Enums สำหรับสถานะต่างๆ
class BookingStatus:
    """สถานะการจอง"""
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    NO_SHOW = "no_show"

class SessionStep:
    """ขั้นตอนในการจอง"""
    NAME = "name"
    PHONE = "phone"
    DATE = "date"
    TIME = "time"
    PARTY_SIZE = "party_size"
    SPECIAL_REQUESTS = "special_requests"
    CANCEL_PHONE = "cancel_phone"
    CONFIRMATION = "confirmation"

class EventType:
    """ประเภทของ event"""
    BOOKING_STARTED = "booking_started"
    BOOKING_COMPLETED = "booking_completed"
    BOOKING_CANCELLED = "booking_cancelled"
    BOOKING_FAILED = "booking_failed"
    USER_INQUIRY = "user_inquiry"
    ADMIN_NOTIFICATION = "admin_notification"