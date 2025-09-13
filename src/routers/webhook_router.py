from fastapi import APIRouter, Depends, Query, HTTPException, Response
from sqlalchemy.orm import Session
from ..database import SessionLocal
from ..schemas import webhook_schemas
from ..controllers import message_controller
from dotenv import load_dotenv
import os

# Load environment variables
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
load_dotenv(dotenv_path=dotenv_path)

# Configure the Gemini API client
ig_api_key = os.getenv("INSTAGRAM_VERIFY_TOKEN")
# --- This can be a simpler prefix, as the main /api is handled in main.py ---
router = APIRouter(
    prefix="/webhook",
    tags=["Webhook"]
)

# --- Dependency ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# The path is now just "/whatsapp" because of the prefix="/webhook"
@router.post("/whatsapp", summary="Receive WhatsApp Messages")
async def receive_whatsapp_webhook(payload: webhook_schemas.WebhookPayload, db: Session = Depends(get_db)):
    print(f"Received webhook for event: '{payload.event}'")
    if payload.event == 'onmessage' and payload.body and payload.sender and payload.from_number:
        normalized_message = webhook_schemas.NormalizedMessage(
            channel="WhatsApp",
            contact_id=payload.from_number,
            pushname=payload.sender.pushname or "Customer",
            body=payload.body
        )
        await message_controller.process_incoming_message(normalized_message, db)
    
    return {"status": "ok"}

@router.get("/instagram")
def verify_instagram_webhook(
    mode: str = Query(..., alias="hub.mode"),
    token: str = Query(..., alias="hub.verify_token"),
    challenge: str = Query(..., alias="hub.challenge"),
):
    if mode == "subscribe" and token == INSTAGRAM_VERIFY_TOKEN:
        print("✅ Webhook verified successfully!")
        return Response(content=challenge, media_type="text/plain")
    else:
        raise HTTPException(status_code=403, detail="Verification token mismatch")