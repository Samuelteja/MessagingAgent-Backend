# src/crud/crud_campaign.py
import random
import re
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, cast, Date, case
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from .. import models
from .crud_contact import get_last_conversation

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
    """
    MODIFIED: Finds a unique list of contacts that have at least one of the specified tags.
    This query is now simpler and more efficient.
    """
    return (
        db.query(models.Contact)
        .join(models.Contact.tags) # Join directly from Contact to Tag
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