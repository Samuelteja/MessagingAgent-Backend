# In src/events/abandoned_listeners.py

from .event_types import BookingAbandonedEvent
from ..crud import crud_scheduler
from datetime import datetime, timezone, timedelta
from .. import models

def schedule_abandoned_cart_followup(event: BookingAbandonedEvent):
    """
    LISTENER 1: Schedules a specific, targeted follow-up for a high-intent user
    who was about to book.
    """
    print("  [Listener]: Running schedule_abandoned_cart_followup...")
    
    # Check if a follow-up already exists to prevent duplicates
    existing_followup = event.db_session.query(models.ScheduledTask).filter(
        models.ScheduledTask.contact_id == event.contact.contact_id,
        models.ScheduledTask.task_type == "ABANDONED_CART_FOLLOWUP",
        models.ScheduledTask.status == "pending"
    ).first()

    if not existing_followup:
        entities = event.analysis.get("action_params", {})
        service = entities.get("service", "your appointment")
        
        follow_up_time = datetime.now(timezone.utc) + timedelta(hours=24) # Or a shorter time, like 1 hour
        
        follow_up_content = (
            f"Hi {event.contact.name or 'there'}, we noticed you were about to book a {service} with us. "
            "Did you have any other questions before confirming? We'd be happy to help!"
        )
        
        crud_scheduler.create_scheduled_task(
            db=event.db_session,
            contact_id=event.contact.contact_id,
            task_type="ABANDONED_CART_FOLLOWUP",
            scheduled_time=follow_up_time,
            content=follow_up_content
        )
    else:
        print(f"   - An abandoned cart follow-up already exists. Skipping.")


def generate_abandoned_reply(event: BookingAbandonedEvent):
    """
    LISTENER 2: Sets the immediate, polite reply to the user.
    """
    print("  [Listener]: Running generate_abandoned_reply...")
    # We can just use the reply suggested by the AI, as our prompt guides it well.
    event.final_reply = event.analysis.get("spoken_reply_suggestion", "No problem! Let me know if I can help with anything else.")