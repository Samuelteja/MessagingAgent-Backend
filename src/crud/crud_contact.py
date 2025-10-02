# src/crud/crud_contact.py
import random
import re
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, cast, Date, case
from sqlalchemy.orm.attributes import flag_modified
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from .. import models
from ..schemas import contact_schemas

# ==============================================================================
# --- NEW: Contact CRUD Functions ---
# ==============================================================================
def get_contact_by_contact_id(db: Session, contact_id: str) -> Optional[models.Contact]:
    """Fetches a single contact by their unique contact_id string."""
    return db.query(models.Contact).filter(models.Contact.contact_id == contact_id).first()

def get_or_create_contact(db: Session, contact_id: str, pushname: Optional[str] = None) -> models.Contact:
    """
    The cornerstone of our identity system.
    Tries to find a contact by their ID. If not found, it creates one.
    Uses the pushname as the default name for new contacts.
    """
    contact = get_contact_by_contact_id(db, contact_id)
    if not contact:
        print(f"👤 New contact detected: {contact_id}. Creating entry...")
        contact = models.Contact(
            contact_id=contact_id,
            name=pushname # Use the pushname as the initial name
        )
        db.add(contact)
        db.commit()
        db.refresh(contact)
    return contact

def update_contact_name(db: Session, contact_id: str, new_name: str) -> Optional[models.Contact]:
    """Updates the name of an existing contact."""
    contact = get_contact_by_contact_id(db, contact_id)
    if contact:
        print(f"✏️ Updating name for {contact_id} to '{new_name}'.")
        contact.name = new_name
        contact.is_name_confirmed = True
        db.commit()
        db.refresh(contact)
    return contact

# ==============================================================================
# --- Conversation CRUD Functions ---
# ==============================================================================

def get_conversations(db: Session, skip: int = 0, limit: int = 100):
    """
    MODIFIED: Fetches a list of the most recent, unique conversations.
    It now correctly joins with the Contact table.
    """
    # This subquery finds the ID of the most recent message for each contact.
    subquery = (
        db.query(func.max(models.Conversation.id).label("max_id"))
        .group_by(models.Conversation.contact_db_id)
        .subquery()
    )

    # The main query then fetches the full conversation objects for those IDs.
    # We use joinedload to eagerly load the related contact to avoid extra queries.
    q = (
        db.query(models.Conversation)
        .join(subquery, models.Conversation.id == subquery.c.max_id)
        .options(joinedload(models.Conversation.contact)) # Eager load the contact info
        .order_by(models.Conversation.timestamp.desc())
        .offset(skip)
        .limit(limit)
    )
    # =========================================================================
    
    return q.all()


def get_full_chat_history(db: Session, contact_id: str):
    """
    MODIFIED: Fetches the entire conversation history for a specific contact_id string.
    It now filters by joining through the Contact table.
    """
    return (
        db.query(models.Conversation)
        .join(models.Contact)
        .filter(models.Contact.contact_id == contact_id)
        .order_by(models.Conversation.timestamp.asc())
        .all()
    )


def get_chat_history(db: Session, contact_id: str, limit: int = 10):
    """
    MODIFIED: Fetches a LIMITED, RECENT conversation history for a specific contact_id string.
    This is used to provide context to the AI.
    """
    return (
        db.query(models.Conversation)
        .join(models.Contact)
        .filter(models.Contact.contact_id == contact_id)
        .order_by(models.Conversation.timestamp.desc())
        .limit(limit)
        .all()
    )


def get_last_conversation(db: Session, contact_id: str):
    """
    MODIFIED: Fetches only the single most recent conversation entry for a contact_id string.
    """
    return (
        db.query(models.Conversation)
        .join(models.Contact)
        .filter(models.Contact.contact_id == contact_id)
        .order_by(models.Conversation.timestamp.desc())
        .first()
    )

def log_conversation(
    db: Session, 
    channel: str, 
    contact_db_id: int, 
    incoming_text: str, 
    outgoing_text: Optional[str], 
    status: str,
    outcome: str # <-- It now requires the outcome to be passed in
) -> models.Conversation:
    """
    SIMPLIFIED: Logs a full conversation exchange to the database.
    It now requires the controller to provide the correct outcome.
    """
    db_conversation = models.Conversation(
        channel=channel,
        contact_db_id=contact_db_id,
        incoming_text=incoming_text,
        outgoing_text=outgoing_text,
        status=status,
        outcome=outcome # <-- Use the outcome provided by the controller
    )
    db.add(db_conversation)
    # db.commit()
    # db.refresh(db_conversation)
    print(f"Conversation logged for contact ID {contact_db_id} with outcome '{outcome}'.")
    return db_conversation

def set_ai_pause(db: Session, contact_id: str, minutes: int = 720): # Default to 12 hours
    """Sets the AI pause for a contact for a specified duration."""
    contact = get_contact_by_contact_id(db, contact_id)
    if contact:
        contact.ai_is_paused_until = datetime.now(timezone.utc) + timedelta(minutes=minutes)
        db.commit()
        print(f"AI has been paused for contact {contact_id} until {contact.ai_is_paused_until}")
    return contact

def release_ai_pause(db: Session, contact_id: str):
    """Releases the AI pause for a contact, making the AI active again."""
    contact = get_contact_by_contact_id(db, contact_id)
    if contact:
        contact.ai_is_paused_until = None
        db.commit()
        print(f"AI pause has been released for contact {contact_id}")
    return contact

def bulk_import_contacts(db: Session, contacts_to_import: List[contact_schemas.ContactImport]) -> dict:
    """
    Processes a list of contacts, creating new ones or updating existing ones.
    Returns a summary of the operation.
    """
    created_count = 0
    updated_count = 0

    for contact_data in contacts_to_import:
        # Check if a contact with this ID already exists.
        existing_contact = get_contact_by_contact_id(db, contact_id=contact_data.contact_id)
        
        if existing_contact:
            # If the contact exists, update their name and mark it as confirmed.
            # This is useful for enriching data from a CSV where the name is more accurate.
            if existing_contact.name != contact_data.name:
                existing_contact.name = contact_data.name
                existing_contact.is_name_confirmed = True
                updated_count += 1
        else:
            # If the contact does not exist, create a new one.
            new_contact = models.Contact(
                contact_id=contact_data.contact_id,
                name=contact_data.name,
                is_name_confirmed=True # We consider imported names as confirmed.
            )
            db.add(new_contact)
            created_count += 1
            
    db.commit()
    
    return {"created": created_count, "updated": updated_count}

def get_all_contacts(db: Session, skip: int = 0, limit: int = 100):
    """Fetches a paginated list of all contacts, with their tags, ordered by most recently created."""
    return (
        db.query(models.Contact)
        .options(joinedload(models.Contact.tags))
        .order_by(models.Contact.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

def get_manager_contact(db: Session) -> Optional[models.Contact]:
    """
    Finds the designated manager contact for sending system prompts.
    For the MVP, we assume only one manager.
    """
    return db.query(models.Contact).filter(models.Contact.role == 'manager').first()

def get_conversation_state(db: Session, contact_id: str) -> dict:
    """Fetches the raw conversation_state JSON for a contact."""
    contact = get_contact_by_contact_id(db, contact_id)
    return contact.conversation_state if contact else {}

def set_conversation_state(db: Session, contact_id: str, new_state: dict) -> Optional[models.Contact]:
    """Overwrites the conversation_state for a contact for testing purposes."""
    contact = get_contact_by_contact_id(db, contact_id)
    if contact:
        contact.conversation_state = new_state
        # Crucially, flag the JSON field as modified for SQLAlchemy to detect the change
        flag_modified(contact, "conversation_state")
        db.commit()
        db.refresh(contact)
    return contact