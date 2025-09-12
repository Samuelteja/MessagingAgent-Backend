# src/main.py.

from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel, Field
from . import models, schemas, crud, analytics_schemas, menu_router
from .database import engine, SessionLocal
from .controllers import message_controller
from .services import scheduler_service
from .services.websocket_manager import manager
import random
from .services import whatsapp_service

models.Base.metadata.create_all(bind=engine)
scheduler_service.initialize_scheduler()

class TagsUpdatePayload(BaseModel):
    tags: List[str]

class CampaignCreatePayload(BaseModel):
    name: str = Field(..., example="July Discount Offer")
    message_template: str = Field(..., example="Hi {customer_name}! Get 15% off this week.")
    target_tags: List[str] = Field(..., example=["interest:hair-coloring", "VIP"])
    expires_at: datetime

class ManualReplyPayload(BaseModel):
    message: str = Field(..., min_length=1)

# --- CONFIGURATION for Safety ---
MAX_BROADCASTS_PER_DAY = 100
MIN_STAGGER_SECONDS = 45
MAX_STAGGER_SECONDS = 120

app = FastAPI(
    title="AI Messaging Assistant API",
    version="0.2.0",
)
app.include_router(menu_router.router)

origins = [
    "http://localhost:5173", # The default Vite dev server port
    "http://localhost:3000", # A common port for Create React App
    "http://localhost",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"], # Allows all methods
    allow_headers=["*"], # Allows all headers
)

# --- Dependency ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.websocket("/ws/inbox-updates")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# --- Webhook Endpoint ---
@app.post("/webhook/whatsapp", tags=["Webhook"])
async def receive_whatsapp_webhook(payload: schemas.WebhookPayload, db: Session = Depends(get_db)):
    print(f"Received webhook for event: '{payload.event}'")
    if payload.event == 'onmessage' and payload.body and payload.sender and payload.from_number:
        normalized_message = schemas.NormalizedMessage(
            channel="WhatsApp",
            contact_id=payload.from_number,
            pushname=payload.sender.pushname or "Customer", # Use a default if pushname is missing
            body=payload.body
        )
        
        await message_controller.process_incoming_message(normalized_message, db)
    
    return {"status": "ok"}

# Tags Endpoints
@app.post("/api/tags/", response_model=schemas.Tag, tags=["Tags"])
def create_new_tag(tag: schemas.TagCreate, db: Session = Depends(get_db)):
    db_tag = crud.get_tag_by_name(db, name=tag.name)
    if db_tag:
        raise HTTPException(status_code=400, detail="Tag with this name already exists")
    return crud.create_tag(db=db, tag=tag)

@app.get("/api/tags/", response_model=List[schemas.Tag], tags=["Tags"])
def read_tags(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    tags = crud.get_tags(db, skip=skip, limit=limit)
    return tags


# Knowledge Endpoints
@app.post("/api/knowledge/", response_model=schemas.BusinessKnowledge, tags=["Business Knowledge"])
def create_knowledge(item: schemas.BusinessKnowledgeCreate, db: Session = Depends(get_db)):
    # Use our new function to check for the composite key
    db_item = crud.get_knowledge_item_by_type_and_key(db, item_type=item.type, item_key=item.key)
    if db_item:
        raise HTTPException(status_code=400, detail=f"A '{item.type}' item with the key '{item.key}' already exists.")
    return crud.create_knowledge_item(db=db, item=item)

@app.get("/api/knowledge/", response_model=List[schemas.BusinessKnowledge], tags=["Business Knowledge"])
def read_knowledge(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.get_knowledge_items(db, skip=skip, limit=limit)

# Staff Endpoints
@app.post("/api/staff/", response_model=schemas.StaffRoster, tags=["Staff Roster"])
def create_staff(member: schemas.StaffRosterCreate, db: Session = Depends(get_db)):
    return crud.create_staff_member(db=db, member=member)

@app.get("/api/staff/", response_model=List[schemas.StaffRoster], tags=["Staff Roster"])
def read_staff(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.get_staff_members(db, skip=skip, limit=limit)

# Business Hours Endpoints
@app.post("/api/hours/", response_model=List[schemas.BusinessHours], tags=["Business Hours"])
def update_hours(hours_update: schemas.BusinessHoursUpdate, db: Session = Depends(get_db)):
    return crud.bulk_update_business_hours(db=db, hours_update=hours_update)

@app.get("/api/hours/", response_model=List[schemas.BusinessHours], tags=["Business Hours"])
def read_hours(db: Session = Depends(get_db)):
    return crud.get_business_hours(db)

# Conversation Endpoints

@app.get("/api/conversations/", response_model=List[schemas.Conversation], tags=["Conversations"])
def read_conversations(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """
    Retrieves a list of unique, recent conversations.
    """
    conversations = crud.get_conversations(db, skip=skip, limit=limit)
    return conversations

@app.get("/api/conversations/{contact_id:path}", response_model=List[schemas.Conversation], tags=["Conversations"])
def read_conversation_history(contact_id: str, db: Session = Depends(get_db)):
    """
    Retrieves the full conversation history for a specific contact_id.
    """
    history = crud.get_full_chat_history(db, contact_id=contact_id)
    if not history:
        raise HTTPException(status_code=404, detail="No conversation history found for this contact")
    return history

@app.post("/api/conversations/{contact_id:path}/tags", response_model=schemas.Conversation, tags=["Conversations"])
def update_conversation_tags(contact_id: str, payload: TagsUpdatePayload, db: Session = Depends(get_db)):
    updated_convo = crud.update_tags_for_contact(db, contact_id=contact_id, tag_names=payload.tags)
    if not updated_convo:
        raise HTTPException(status_code=404, detail="Contact not found")
    return updated_convo

@app.post("/api/conversations/{contact_id:path}/send-manual-reply", tags=["Conversations"], summary="Send a Manual Reply")
def send_manual_reply(contact_id: str, payload: ManualReplyPayload, db: Session = Depends(get_db)):
    """
    Allows a human operator to take over a conversation and send a message directly.
    This bypasses the AI entirely.
    """
    print(f"Human Takeover: Sending manual reply to {contact_id}")
    
    # We log this manual action to the database for a complete conversation history.
    # Note: We are logging it as a message initiated by us (outgoing).
    contact = crud.get_contact_by_contact_id(db, contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
        
    crud.log_conversation(
        db=db,
        channel="WhatsApp", # Or get from contact if you store it there
        contact_db_id=contact.id,
        incoming_text=f"--- Manual Reply Sent by Operator ---",
        outgoing_text=payload.message,
        status="replied_manual" # A new status for clarity
    )

    # We assume only WhatsApp for now. This will become a multi-channel service later.
    whatsapp_service.send_reply(phone_number=contact_id, message=payload.message)
    
    # We don't need to send a WebSocket update here, because the frontend
    # will handle updating its own state after a successful API call.
    
    return {"status": "success", "message": "Manual reply sent."}

@app.post("/api/conversations/{contact_id:path}/pause-ai", tags=["Conversations"], summary="Pause AI for a Contact")
def pause_ai_for_contact(contact_id: str, db: Session = Depends(get_db)):
    """Pauses the AI for a specific contact for a long duration."""
    contact = crud.set_ai_pause(db, contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    return {"status": "success", "message": "AI paused for this contact."}

@app.post("/api/conversations/{contact_id:path}/release-ai", tags=["Conversations"], summary="Release AI for a Contact")
def release_ai_for_contact(contact_id: str, db: Session = Depends(get_db)):
    """Releases the AI pause for a specific contact, making it active again."""
    contact = crud.release_ai_pause(db, contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    return {"status": "success", "message": "AI control released for this contact."}

# --- Root and Health Check ---
@app.get("/", tags=["System"])
def read_root():
    return {"status": "ok", "message": "Welcome to the AI Messaging Assistant API!"}

@app.get("/ping", tags=["System"])
def health_check():
    return {"status": "ok", "message": "pong"}

@app.post("/api/knowledge/bulk-upload", tags=["Business Knowledge"])
def create_knowledge_bulk(items: List[schemas.BusinessKnowledgeCreate], db: Session = Depends(get_db)):
    """
    Handles bulk creation of knowledge items.
    It now intelligently handles different types (MENU, QA) based on the payload.
    """
    # Basic validation: ensure all items in a single upload are of the same type.
    if not items:
        raise HTTPException(status_code=400, detail="No items provided for upload.")
    
    item_type = items[0].type
    if not all(item.type == item_type for item in items):
        raise HTTPException(status_code=400, detail="All items in a bulk upload must be of the same type.")

    if item_type not in ['MENU', 'QA']:
        raise HTTPException(status_code=400, detail=f"Bulk upload for type '{item_type}' is not supported.")

    # We can reuse the existing crud function as it's already flexible enough.
    count = crud.bulk_create_knowledge_items(db=db, items=items)
    
    print(f"✅ Successfully bulk-inserted {count} items of type '{item_type}'.")
    return {"status": "success", "items_created": count}

@app.get("/api/analytics/summary", response_model=analytics_schemas.AnalyticsSummary, tags=["Analytics"])
def get_analytics(db: Session = Depends(get_db)):
    summary_data = crud.get_analytics_summary(db)
    return summary_data

@app.get("/api/analytics/advanced", response_model=analytics_schemas.AdvancedAnalytics, tags=["Analytics"], summary="Get Advanced ROI Analytics")
def get_advanced_analytics_data(db: Session = Depends(get_db)):
    """
    Provides advanced, revenue-focused metrics like total estimated revenue
    and top-performing services booked by the AI.
    """
    return crud.get_advanced_analytics(db)

# ==============================================================================
# --- NEW: Campaign Endpoints ---
# ==============================================================================
@app.post("/api/campaigns/broadcast", tags=["Campaigns"])
def launch_smart_campaign(payload: CampaignCreatePayload, db: Session = Depends(get_db)):
    """
    Launches a new, time-bound, and safety-first broadcast campaign
    using the 'Smart Launch' approach.
    """
    print(f"Received request to launch campaign: '{payload.name}'")

    # 1. Daily Limit Check
    sent_today = crud.count_campaign_messages_sent_today(db)
    remaining_sends = MAX_BROADCASTS_PER_DAY - sent_today
    if remaining_sends <= 0:
        raise HTTPException(status_code=429, detail=f"Daily broadcast limit of {MAX_BROADCASTS_PER_DAY} has been reached.")

    # 2. Find Target Contacts
    target_contacts = crud.find_contacts_by_tags(db, payload.target_tags) # We'll need to create this new CRUD function
    if not target_contacts:
        raise HTTPException(status_code=404, detail="No customers found matching the selected tags.")
    
    # 3. Create the Campaign record in the database
    campaign = crud.create_campaign(db, name=payload.name, message_template=payload.message_template, expires_at=payload.expires_at)
    
    # 4. Perform Safety Checks and Schedule Recipients
    # This function will now also need to handle queuing for the next day.
    scheduling_result = crud.add_and_schedule_recipients(
        db,
        campaign=campaign,
        contacts=target_contacts,
        stagger_seconds=random.randint(MIN_STAGGER_SECONDS, MAX_STAGGER_SECONDS),
        daily_limit=remaining_sends
    )

    # 5. Return the Intelligent Summary Response
    return {
        "status": "success",
        "message": f"Campaign '{campaign.name}' has been successfully scheduled.",
        "summary": scheduling_result
    }