from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import json
import logging

# Import config ที่มี logging setup
from config import log_booking_event, log_webhook_request, log_error_with_context, APP_TITLE, APP_VERSION
from webhook_handler import handle_webhook_request
from utils import verify_line_signature

app = FastAPI(title=APP_TITLE, version=APP_VERSION)
logger = logging.getLogger(__name__)

@app.get("/")
async def health_check():
    """Health check endpoint"""
    logger.info("Health check requested")
    return {"status": "OK", "message": "Bot is running"}

@app.post("/webhook")
async def webhook(request: Request):
    """Webhook endpoint สำหรับรับข้อความจาก LINE"""
    try:
        # ดึงข้อมูลจาก request
        body = await request.body()
        headers = dict(request.headers)
        
        # ตรวจสอบ signature
        signature = headers.get("x-line-signature", "")
        if not verify_line_signature(body, signature):
            logger.warning("Invalid LINE signature")
            raise HTTPException(status_code=400, detail="Invalid signature")
        
        # แปลง body เป็น JSON
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            logger.warning("Invalid JSON body")
            raise HTTPException(status_code=400, detail="Invalid JSON")
        
        # บันทึก webhook request
        log_webhook_request(
            method="POST",
            headers=headers,
            body=payload,
            response_status=None
        )
        
        # ตรวจสอบ Content-Type
        content_type = headers.get("content-type", "")
        if "application/json" not in content_type:
            logger.warning(f"Invalid content type: {content_type}")
            raise HTTPException(status_code=400, detail="Invalid content type")
        
        if not payload:
            logger.warning("Empty request body")
            raise HTTPException(status_code=400, detail="Empty body")
        
        logger.info(f"Received webhook: {json.dumps(payload, ensure_ascii=False)}")
        
        # ส่งต่อไปยัง handler
        result = await handle_webhook_request(payload, headers)
        
        # บันทึก response status
        status_code = 200 if result else 500
        log_webhook_request(
            method="POST",
            headers=headers,
            body=payload,
            response_status=status_code
        )
        
        if result:
            logger.info("Webhook processed successfully")
            return {"status": "ok"}
        else:
            logger.error("Webhook processing failed")
            raise HTTPException(status_code=500, detail="Webhook processing failed")
            
    except HTTPException:
        raise
    except Exception as e:
        log_error_with_context(
            error=e,
            context="webhook_endpoint",
            additional_data={"request_body": str(body) if 'body' in locals() else None}
        )
        raise HTTPException(status_code=500, detail="Internal server error")

@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    logger.warning(f"404 Not Found: {request.url}")
    return JSONResponse(
        status_code=404,
        content={"error": "Not Found", "path": str(request.url)}
    )

@app.exception_handler(500)
async def internal_error_handler(request: Request, exc):
    logger.error(f"500 Internal Server Error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal Server Error"}
    )

@app.get("/health")
async def health_detail():
    """Detailed health check endpoint"""
    import time
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "version": APP_VERSION,
        "service": "LINE Bot Restaurant Booking"
    }

if __name__ == "__main__":
    import uvicorn
    
    logger.info("🚀 Starting FastAPI application...")
    logger.info("📱 LINE Bot is ready to receive messages")
    
    # สำหรับ development
    uvicorn.run(
        "main:app", 
        host="0.0.0.0", 
        port=8000, 
        reload=True,
        log_level="info"
    )
    
    # สำหรับ production ใช้คำสั่ง:
    # uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4