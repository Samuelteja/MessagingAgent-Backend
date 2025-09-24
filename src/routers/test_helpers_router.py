# src/routers/test_helpers_router.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional

from ..database import SessionLocal
from ..services import whatsapp_service
from ..crud import crud_contact
from ..controllers import message_controller
from ..schemas.webhook_schemas import NormalizedMessage

# --- Pydantic Schemas for our Test Payloads ---

class SendMessagePayload(BaseModel):
    contact_id: str = Field(..., example="919876543210@c.us")
    message: str = Field(..., example="Hi there!")

class LastMessageResponse(BaseModel):
    outgoing_text: Optional[str] = None
    timestamp: Optional[str] = None
    outcome: Optional[str] = None


# --- Router Setup ---

router = APIRouter(
    prefix="/api/test-helpers",
    tags=["Testing Utilities"]
)

# --- Dependency ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --- API Endpoints ---

@router.post("/send-message", summary="Simulate a User Sending a WhatsApp Message")
def simulate_send_message(payload: SendMessagePayload):
    """
    Allows a test script to send a message from a test number.
    NOTE: This uses the WPPConnect API, which requires the 'from' number
    to be the same as the one the WPPConnect server is logged in with.
    This simulates the BOT sending a message TO the contact_id.
    To simulate a true user message, the test suite will need more direct control,
    but this is a good starting point for triggering bot replies.
    For the purpose of the test, we will assume this is triggering the webhook manually.
    """
    print(f"TEST HELPER: Simulating message send to {payload.contact_id}")
    try:
        # In a real test suite, you'd likely trigger your own webhook here.
        # For now, this endpoint is a placeholder for that interaction library.
        # The primary use for the tester is the GET endpoint below.
        # Let's make this endpoint more useful by having it send a message from the bot.
        whatsapp_service.send_reply(payload.contact_id, payload.message)
        return {"status": "success", "message": f"Message sent to {payload.contact_id}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/get-last-message/{contact_id:path}", response_model=LastMessageResponse, summary="Get the Bot's Last Reply to a User")
def get_last_message(contact_id: str, db: Session = Depends(get_db)):
    """
    Retrieves the last outgoing message from the bot to a specific contact.
    This is the primary endpoint the test suite will use to assert the bot's responses.
    """
    print(f"TEST HELPER: Fetching last message for {contact_id}")
    last_conversation = crud_contact.get_last_conversation(db, contact_id=contact_id)
    
    if not last_conversation:
        return LastMessageResponse(outgoing_text=None, timestamp=None, outcome=None)
        
    return LastMessageResponse(
        outgoing_text=last_conversation.outgoing_text,
        timestamp=str(last_conversation.timestamp),
        outcome=last_conversation.outcome
    )

@router.post("/simulate-incoming-message")
async def simulate_incoming_message(payload: SendMessagePayload, db: Session = Depends(get_db)):
    """
    Receives a simulated message payload and injects it directly into the
    message processing pipeline, bypassing the need for a live WPPConnect webhook.
    """
    print("<<<<< SIMULATING INCOMING MESSAGE via Test Helper >>>>>")
    # Set a default event type if not provided, as this is what the controller expects
    normalized_message = NormalizedMessage(
        channel="WhatsApp",
        contact_id=payload.contact_id,
        pushname="Test User", # A sensible default for a test
        body=payload.message
    )
    
    # The core logic is to simply call the same controller function the real webhook would
    await message_controller.process_incoming_message(normalized_message, db)
    
    return {"status": "ok", "message": "Simulated message injected into the pipeline."}