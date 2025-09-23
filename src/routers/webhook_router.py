# src/routers/webhook_router.py
from fastapi import APIRouter, Depends, Query, HTTPException, Response, Request, Body
from sqlalchemy.orm import Session
from ..database import SessionLocal
from ..schemas import webhook_schemas
from ..controllers import message_controller
from dotenv import load_dotenv
from typing import Dict, Any
import os

# Load environment variables
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
load_dotenv(dotenv_path=dotenv_path)

# Configure the Gemini API client
INSTAGRAM_VERIFY_TOKEN = os.getenv("INSTAGRAM_VERIFY_TOKEN")
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
    
@router.post("/instagram", summary="Receive Instagram Messages")
async def receive_instagram_webhook(
    payload: Dict[str, Any] = Body(...), # Receive the JSON payload directly
    db: Session = Depends(get_db)
):
    """
    This endpoint receives all real-time message events from Instagram DMs.
    It now contains the full logic to parse the payload and normalize it.
    """
    print("--- Received Instagram Webhook Payload ---")
    print(payload)
    print("----------------------------------------")

    # According to Meta's documentation, the payload object will be 'instagram'
    if payload.get("object") == "instagram":
        # The payload can contain multiple entries (e.g., if multiple events happen quickly)
        for entry in payload.get("entry", []):
            # Each entry can contain multiple messaging events
            for event in entry.get("messaging", []):
                
                # We only care about actual messages sent by a user
                if event.get("message") and event.get("sender"):
                    
                    # --- THIS IS THE CORE NORMALIZATION LOGIC ---
                    sender_id = event["sender"]["id"]
                    message_text = event["message"].get("text")

                    # Ignore messages that are not simple text (e.g., likes, attachments)
                    if not message_text:
                        print(f"   - Ignoring non-text message from {sender_id}")
                        continue

                    print(f"   -> Found text message from IG User ID: {sender_id}")
                    
                    # Create our standardized internal message object
                    normalized_message = webhook_schemas.NormalizedMessage(
                        channel="Instagram",
                        contact_id=sender_id, # For Instagram, this is the Page-Scoped User ID (PSID)
                        pushname=f"IG User {sender_id}", # Instagram doesn't provide a pushname in the webhook
                        body=message_text
                    )

                    # Pass the normalized message to our central controller.
                    # From this point on, the system doesn't care that it came from Instagram.
                    await message_controller.process_incoming_message(normalized_message, db)
    
    return {"status": "ok"}