# src/routers/contact_router.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from ..schemas import contact_schemas, tag_schemas
from ..crud import crud_contact, crud_tag
from ..database import SessionLocal
from ..services import whatsapp_service

router = APIRouter(
    # =========================================================================
    # --- THIS IS THE KEY CHANGE (Part 1) ---
    # The prefix is now based on the 'contacts' resource.
    prefix="/api/contacts",
    # =========================================================================
    tags=["Contacts & Conversations"]
)

# --- Dependency ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- NEW PATH: /api/contacts/inbox ---
@router.get("/inbox", response_model=List[contact_schemas.Conversation], summary="Get Recent Conversations for Inbox")
def read_conversations_for_inbox(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """Retrieves the list of unique, most recent conversations for the main inbox view."""
    return crud_contact.get_conversations(db, skip=skip, limit=limit)

# --- NEW PATH: /api/contacts/{contact_id}/history ---
@router.get("/{contact_id:path}/history", response_model=List[contact_schemas.Conversation], summary="Get Full Chat History")
def read_conversation_history(contact_id: str, db: Session = Depends(get_db)):
    """Retrieves the full, ordered conversation history for a specific contact."""
    history = crud_contact.get_full_chat_history(db, contact_id=contact_id)
    if not history:
        raise HTTPException(status_code=404, detail="No history found")
    return history

# --- NEW PATH: /api/contacts/{contact_id}/tags ---
@router.post("/{contact_id:path}/tags", response_model=contact_schemas.Contact, summary="Update Tags for a Contact")
def update_contact_tags(contact_id: str, payload: contact_schemas.TagsUpdatePayload, db: Session = Depends(get_db)):
    """Assigns a list of tags directly to a contact."""
    updated_contact = crud_tag.update_tags_for_contact(db, contact_id=contact_id, tag_names=payload.tags)
    if not updated_contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    return updated_contact

# --- NEW PATHS for other contact-specific actions ---
@router.post("/{contact_id:path}/send-manual-reply", summary="Send a Manual Reply")
def send_manual_reply(contact_id: str, payload: contact_schemas.ManualReplyPayload, db: Session = Depends(get_db)):
    """
    Allows a human operator to take over a conversation and send a message directly.
    This bypasses the AI entirely.
    """
    print(f"Human Takeover: Sending manual reply to {contact_id}")
    
    # We log this manual action to the database for a complete conversation history.
    # Note: We are logging it as a message initiated by us (outgoing).
    contact = crud_contact.get_contact_by_contact_id(db, contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    crud_contact.log_conversation(
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

@router.post("/{contact_id:path}/pause-ai", summary="Pause AI for a Contact")
def pause_ai_for_contact(contact_id: str, db: Session = Depends(get_db)):
    """Pauses the AI for a specific contact for a long duration."""
    contact = crud_contact.set_ai_pause(db, contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    return {"status": "success", "message": "AI paused for this contact."}

@router.post("/{contact_id:path}/release-ai", summary="Release AI for a Contact")
def release_ai_for_contact(contact_id: str, db: Session = Depends(get_db)):
    """Releases the AI pause for a specific contact, making it active again."""
    contact = crud_contact.release_ai_pause(db, contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    return {"status": "success", "message": "AI control released for this contact."}

@router.post("/import", summary="Bulk Import Contacts")
def bulk_import_contacts_endpoint(
    payload: contact_schemas.ContactImportPayload,
    db: Session = Depends(get_db)
):
    """
    Accepts a list of contacts from a parsed CSV/Excel file and imports them.
    - Creates new contacts if they don't exist.
    - Updates the name of existing contacts if the new name is different.
    """
    if not payload.contacts:
        raise HTTPException(status_code=400, detail="No contacts provided in the payload.")

    summary = crud_contact.bulk_import_contacts(db, contacts_to_import=payload.contacts)
    
    return {
        "status": "success",
        "message": f"Import complete. Created: {summary['created']}, Updated: {summary['updated']}.",
        "summary": summary
    }

@router.get("/", response_model=List[contact_schemas.Contact], summary="Get All Contacts")
def read_all_contacts(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """Retrieves a paginated list of all contacts in the database."""
    contacts = crud_contact.get_all_contacts(db, skip=skip, limit=limit)
    return contacts