# src/crud.py
import random
import re
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, cast, Date, case
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from . import models, schemas
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

def log_conversation(db: Session, channel: str, contact_db_id: int, incoming_text: str, outgoing_text: Optional[str], status: str):
    """
    MODIFIED: Logs a full conversation exchange to the database.
    It now takes contact_db_id (the integer PK) instead of the string.
    """
    db_conversation = models.Conversation(
        channel=channel,
        contact_db_id=contact_db_id, # Use the foreign key
        incoming_text=incoming_text,
        outgoing_text=outgoing_text,
        status=status
    )
    db.add(db_conversation)
    db.commit()
    db.refresh(db_conversation)
    print(f"Conversation for contact ID {contact_db_id} logged to database.")
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

# ==============================================================================
# --- Tag CRUD Functions ---
# ==============================================================================

def get_tag_by_name(db: Session, name: str):
    return db.query(models.Tag).filter(models.Tag.name == name).first()

def get_tags(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Tag).offset(skip).limit(limit).all()

def create_tag(db: Session, tag: schemas.TagCreate):
    db_tag = models.Tag(name=tag.name)
    db.add(db_tag)
    db.commit()
    db.refresh(db_tag)
    return db_tag

def update_tags_for_contact(db: Session, contact_id: str, tag_names: List[str]):
    conversations = (
        db.query(models.Conversation)
        .join(models.Contact)
        .filter(models.Contact.contact_id == contact_id)
        .all()
    )

    if not conversations:
        return None
    
    tags_to_assign = []
    if tag_names:
        tags_to_assign = db.query(models.Tag).filter(models.Tag.name.in_(tag_names)).all()
    
    for convo in conversations:
        convo.tags.clear() # Explicitly clear old tags
        for tag in tags_to_assign:
            convo.tags.append(tag) # Append new ones
    
    db.commit() # Save the changes
    
    print(f"CRUD: Successfully updated tags for {contact_id} with: {[t.name for t in tags_to_assign]}")
    
    db.refresh(conversations[0])
    return conversations[0]

# ==============================================================================
# --- Business Knowledge & Staff CRUD Functions ---
# ==============================================================================

def get_knowledge_item_by_type_and_key(db: Session, item_type: str, item_key: str):
    return db.query(models.BusinessKnowledge).filter(
        models.BusinessKnowledge.type == item_type,
        models.BusinessKnowledge.key == item_key
    ).first()

def get_knowledge_items(db: Session, skip: int = 0, limit: int = 200):
    return db.query(models.BusinessKnowledge).offset(skip).limit(limit).all()

def create_knowledge_item(db: Session, item: schemas.BusinessKnowledgeCreate):
    db_item = models.BusinessKnowledge(**item.dict())
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item

def bulk_create_knowledge_items(db: Session, items: List[schemas.BusinessKnowledgeCreate]):
    db_items = [models.BusinessKnowledge(**item.dict()) for item in items]
    db.bulk_save_objects(db_items)
    db.commit()
    return len(db_items)

def get_staff_members(db: Session, skip: int = 0, limit: int = 50):
    return db.query(models.StaffRoster).offset(skip).limit(limit).all()

def create_staff_member(db: Session, member: schemas.StaffRosterCreate):
    db_member = models.StaffRoster(**member.dict())
    db.add(db_member)
    db.commit()
    db.refresh(db_member)
    return db_member

# ==============================================================================
# --- Business Hours & Analytics CRUD Functions --
# ==============================================================================

def get_business_hours(db: Session):
    return db.query(models.BusinessHours).order_by(models.BusinessHours.day_of_week).all()

def bulk_update_business_hours(db: Session, hours_update: schemas.BusinessHoursUpdate):
    db.query(models.BusinessHours).delete()
    for hour_data in hours_update.hours:
        db_hour = models.BusinessHours(**hour_data.dict())
        db.add(db_hour)
    db.commit()
    return get_business_hours(db)
    
# In src/crud.py

def get_analytics_summary(db: Session):
    """
    Calculates various statistics for the analytics dashboard.
    This version formats the date as a string directly in the SQL query to avoid type errors.
    """
    # 1. Core KPIs (these are simple counts and are already correct)
    total_conversations = db.query(models.Conversation).count()
    total_bookings_confirmed = db.query(models.Conversation).filter(models.Conversation.outcome == 'booking_confirmed').count()
    total_handoffs = db.query(models.Conversation).filter(models.Conversation.outcome == 'human_handoff').count()
    
    # 2. Query for conversations per day for the last 7 days
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    
    # This is the key fix: We use the database's date formatting function 
    # (strftime for SQLite) to return a string directly from the query.
    # The format '%Y-%m-%d' produces a string like '2025-09-07'.
    conversations_per_day_results = (
        db.query(
            func.strftime('%Y-%m-%d', models.Conversation.timestamp).label("date"),
            func.count(models.Conversation.id).label("count"),
        )
        .filter(models.Conversation.timestamp >= seven_days_ago)
        .group_by(func.strftime('%Y-%m-%d', models.Conversation.timestamp))
        .order_by(func.strftime('%Y-%m-%d', models.Conversation.timestamp))
        .all()
    )
    
    # 3. Query for outcomes breakdown
    outcomes_breakdown_results = (
        db.query(
            models.Conversation.outcome.label("outcome"),
            func.count(models.Conversation.id).label("count"),
        )
        .group_by(models.Conversation.outcome)
        .all()
    )

    # 4. Return the data in the format the Pydantic schema expects.
    # The `._mapping` attribute converts the SQLAlchemy result row into a dict-like object.
    return {
        "total_conversations": total_conversations,
        "total_bookings_confirmed": total_bookings_confirmed,
        "total_handoffs": total_handoffs,
        "conversations_per_day": [dict(row._mapping) for row in conversations_per_day_results],
        "outcomes_breakdown": [dict(row._mapping) for row in outcomes_breakdown_results],
    }

def get_advanced_analytics(db: Session):
    """
    Calculates advanced, revenue-focused analytics for the dashboard.
    """
    # This query joins conversations with menu items to calculate revenue.
    # It requires that the AI is correctly extracting the 'service' entity.
    
    # We need a way to link conversation text to a menu item.
    # This is a complex task. A simple approach is to look for service names
    # in the conversation text of confirmed bookings.
    
    # 1. Get all menu items to create a regex pattern
    menu_items = db.query(models.MenuItem).all()
    if not menu_items:
        return {
            "total_estimated_revenue": 0.0,
            "avg_revenue_per_booking": 0.0,
            "top_booked_services": []
        }
        
    # 2. Get all confirmed booking conversations
    confirmed_bookings = db.query(models.Conversation).filter(
        models.Conversation.outcome == 'booking_confirmed'
    ).all()
    
    service_stats = {}
    total_revenue = 0.0
    
    # 3. Process conversations in Python (more flexible than a giant SQL query)
    for convo in confirmed_bookings:
        # Check both incoming and outgoing text for service names
        full_text = f"{convo.incoming_text} {convo.outgoing_text}".lower()
        
        for item in menu_items:
            # If a menu item's name is found in the conversation text...
            if item.name.lower() in full_text:
                if item.name not in service_stats:
                    service_stats[item.name] = {"count": 0, "revenue": 0.0, "price": item.price}
                
                service_stats[item.name]["count"] += 1
                service_stats[item.name]["revenue"] += item.price
                total_revenue += item.price
                break # Count only the first service found per conversation
                
    # 4. Format the results
    top_services = sorted(
        [
            {"service_name": name, "booking_count": data["count"], "estimated_revenue": data["revenue"]}
            for name, data in service_stats.items()
        ],
        key=lambda x: x["booking_count"],
        reverse=True
    )[:5] # Return top 5
    
    avg_revenue = total_revenue / len(confirmed_bookings) if confirmed_bookings else 0.0
    
    return {
        "total_estimated_revenue": total_revenue,
        "avg_revenue_per_booking": avg_revenue,
        "top_booked_services": top_services,
    }

# ==============================================================================
# --- NEW: Campaign CRUD Functions ---
# ==============================================================================
def count_campaign_messages_sent_today(db: Session) -> int:
    """Counts how many campaign messages have the status 'sent' in the last 24 hours."""
    twenty_four_hours_ago = datetime.now(timezone.utc) - timedelta(hours=24)
    return (
        db.query(models.CampaignRecipient)
        .filter(
            models.CampaignRecipient.status == 'sent',
            models.CampaignRecipient.scheduled_time >= twenty_four_hours_ago
        )
        .count()
    )

def create_campaign(db: Session, name: str, message_template: str, expires_at: datetime) -> models.Campaign:
    """Creates a new campaign record."""
    db_campaign = models.Campaign(
        name=name, 
        message_body=message_template, 
        status="processing",
        expires_at=expires_at
    )
    db.add(db_campaign)
    db.commit()
    db.refresh(db_campaign)
    return db_campaign

def add_recipients_to_campaign(db: Session, campaign: models.Campaign, contacts: List[models.Contact], stagger_seconds: int):
    """
    Performs the safety pre-check and adds valid recipients to a campaign
    with a staggered, personalized message.
    """
    recipients_added = 0
    start_time = datetime.now(timezone.utc) + timedelta(minutes=1) # Start sending in 1 minute

    for i, contact in enumerate(contacts):
        # --- Safety Pre-Check ---
        last_convo = get_last_conversation(db, contact_id=contact.contact_id)
        safety_passed = True
        notes = ""
        
        if last_convo:
            db_timestamp = last_convo.timestamp
            
            if db_timestamp.tzinfo is None:
                db_timestamp = db_timestamp.replace(tzinfo=timezone.utc)
            time_since_last_convo = datetime.now(timezone.utc) - db_timestamp
            if time_since_last_convo < timedelta(hours=48):
                safety_passed = False
                notes = "Skipped: Recent conversation (less than 48 hours ago)."
            elif last_convo.outcome == "human_handoff":
                safety_passed = False
                notes = "Skipped: Last conversation required human handoff."
        
        # --- Personalization ---
        personalized_message = campaign.message_body.replace("{customer_name}", contact.name or "there")

        # --- Staggered Scheduling ---
        scheduled_time = start_time + timedelta(seconds=(i * stagger_seconds) + random.randint(-5, 5))

        db_recipient = models.CampaignRecipient(
            campaign_id=campaign.id,
            contact_id=contact.contact_id,
            status="scheduled",
            scheduled_time=scheduled_time,
            safety_check_passed=safety_passed,
            notes=notes,
            content=personalized_message
        )
        db.add(db_recipient)
        recipients_added += 1

    db.commit()
    return recipients_added

def find_contacts_by_tags(db: Session, tag_names: List[str]) -> List[models.Contact]:
    """Finds a unique list of contacts that have at least one of the specified tags."""
    return (
        db.query(models.Contact)
        .join(models.Contact.conversations)
        .join(models.Conversation.tags)
        .filter(models.Tag.name.in_(tag_names))
        .distinct()
        .all()
    )

def add_and_schedule_recipients(db: Session, campaign: models.Campaign, contacts: List[models.Contact], stagger_seconds: int, daily_limit: int) -> dict:
    """
    Performs safety checks, schedules recipients, and handles daily limit overflow.
    Returns a dictionary summarizing the results.
    """
    eligible_contacts = []
    ineligible_count = 0
    ineligible_reasons = {}

    # =========================================================================
    # --- THIS IS THE FIX (PART 1): Implement the safety check logic ---
    # First pass: safety checks
    for contact in contacts:
        safety_passed = True # Assume innocent until proven guilty
        notes = ""
        
        last_convo = get_last_conversation(db, contact_id=contact.contact_id)
        if last_convo:
            db_timestamp = last_convo.timestamp
            if db_timestamp.tzinfo is None:
                db_timestamp = db_timestamp.replace(tzinfo=timezone.utc)
            
            time_since_last_convo = datetime.now(timezone.utc) - db_timestamp
            
            if time_since_last_convo < timedelta(hours=48):
                safety_passed = False
                notes = "Skipped: Recent conversation (<48 hours)."
            elif last_convo.outcome == "human_handoff":
                safety_passed = False
                notes = "Skipped: Last conversation required human handoff."
        
        if safety_passed:
            eligible_contacts.append(contact)
        else:
            ineligible_count += 1
            # For better debugging, we can even count the reasons
            reason = notes.split(':')[1].strip()
            ineligible_reasons[reason] = ineligible_reasons.get(reason, 0) + 1
    # =========================================================================

    # Second pass: scheduling with daily limit
    messages_scheduled_today = 0
    messages_queued_for_tomorrow = 0
    
    start_time_today = datetime.now(timezone.utc) + timedelta(minutes=1)
    start_time_tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).replace(hour=4, minute=0, second=0) # Start at 4 AM UTC (9:30 AM IST)

    for i, contact in enumerate(eligible_contacts):
        # --- THIS IS THE FIX (PART 2): Implement personalization and DB creation ---
        personalized_message = campaign.message_body.replace("{customer_name}", contact.name or "there")
        
        if messages_scheduled_today < daily_limit:
            scheduled_time = start_time_today + timedelta(seconds=(messages_scheduled_today * stagger_seconds) + random.randint(-5, 5))
            messages_scheduled_today += 1
        else:
            scheduled_time = start_time_tomorrow + timedelta(seconds=(messages_queued_for_tomorrow * stagger_seconds) + random.randint(-5, 5))
            messages_queued_for_tomorrow += 1

        db_recipient = models.CampaignRecipient(
            campaign_id=campaign.id,
            contact_id=contact.contact_id,
            status="scheduled",
            scheduled_time=scheduled_time,
            safety_check_passed=True, # All contacts in this list have passed
            notes="Scheduled for sending.",
            content=personalized_message
        )
        db.add(db_recipient)
        
    db.commit()

    return {
        "total_targets_found": len(contacts),
        "eligible_after_safety_check": len(eligible_contacts),
        "ineligible_due_to_safety": ineligible_count,
        "daily_limit_was_applied": len(eligible_contacts) > daily_limit,
        "messages_scheduled_for_today": messages_scheduled_today,
        "messages_queued_for_tomorrow": messages_queued_for_tomorrow,
        "ineligible_reasons": ineligible_reasons
    }