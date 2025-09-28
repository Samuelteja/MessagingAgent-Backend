# In src/events/booking_listeners.py

from .event_types import BookingCreationEvent
from ..crud import crud_booking, crud_scheduler, crud_tag
import dateutil.parser
from datetime import timedelta
from ..database import SessionLocal
from .. import models

def validate_booking_conflict(event: BookingCreationEvent):
    """
    LISTENER 1: Checks for duplicate bookings. If found, it stops the
    pipeline and sets the final reply.
    """
    print("  [Listener]: Running validate_booking_conflict...")
    entities = event.analysis.get("entities", {})
    service = entities.get("service")
    date_str = entities.get("date")
    time_str = entities.get("time")

    if not (service and date_str and time_str):
        return # Not enough info to validate

    try:
        booking_datetime = dateutil.parser.parse(f"{date_str} {time_str}")
        existing_booking = crud_booking.get_conflicting_customer_booking(event.db_session, event.contact.id, service, booking_datetime)
        
        if existing_booking:
            event.stop_processing = True
            event.stop_reason = "Duplicate booking detected"
            event.final_reply = (
                f"It looks like you already have a booking for a '{existing_booking.service_name}' "
                f"scheduled for {existing_booking.booking_datetime.strftime('%A at %I:%M %p')}. "
                f"Were you looking to reschedule?"
            )
    except dateutil.parser.ParserError:
        return

def create_booking_record(event: BookingCreationEvent):
    """LISTENER 2: Creates the booking record in the database."""
    if event.stop_processing: return
    print("  [Listener]: Running create_booking_record...")
    
    # db = SessionLocal()
    try:
        entities = event.analysis.get("action_params", {})
        service = entities.get("service")
        date_str = entities.get("date")
        time_str = entities.get("time")

        if service and date_str and time_str:
            booking_datetime = dateutil.parser.parse(f"{date_str} {time_str}")
            
            # Use the new, local db session
            new_booking = crud_booking.create_booking(event.db_session, event.contact.id, service, booking_datetime)
            
            print(f"   - Booking #{new_booking.id} committed to DB by listener.")
    finally:
        pass
        # db.close()

def schedule_booking_reminder(event: BookingCreationEvent):
    """LISTENER 3: Schedules the 24-hour reminder."""
    if event.stop_processing: return
    print("  [Listener]: Running schedule_booking_reminder...")
    try:
        entities = event.analysis.get("action_params", {})
        service = entities.get("service")
        date_str = entities.get("date")
        time_str = entities.get("time")

        if service and date_str and time_str:
            booking_datetime = dateutil.parser.parse(f"{date_str} {time_str}")
            existing_reminder = crud_scheduler.get_existing_reminder(event.db_session, event.contact.contact_id, booking_datetime)
            if not existing_reminder:
                reminder_time = booking_datetime - timedelta(hours=24)
                content = f"Hi {event.contact.name or 'there'}! Reminder for your {service} appointment tomorrow at {booking_datetime.strftime('%I:%M %p')}."
                
                new_reminder = crud_scheduler.create_scheduled_task(event.db_session, event.contact.contact_id, "APPOINTMENT_REMINDER", reminder_time, content)
                print(f"   - Reminder Task #{new_reminder.id} committed to DB by listener.")
            else:
                print("   - A reminder already exists for this booking. Skipping.")
    finally:
        pass

def apply_booking_tags(event: BookingCreationEvent):
    """LISTENER 4: Applies any AI-suggested tags."""
    if event.stop_processing: return
    print("  [Listener]: Running apply_booking_tags...")
    
    db = SessionLocal()
    try:
        # We need to get the managed Contact object from this new session
        contact_in_session = db.query(models.Contact).filter(models.Contact.id == event.contact.id).first()
        if not contact_in_session: return
        tag_names = event.analysis.get("tags", [])
        if tag_names:
            crud_tag.update_tags_for_contact(db, event.contact.contact_id, tag_names)
            db.commit()
            print("   - Tag updates committed to DB by listener.")
    finally:
        db.close()

def generate_booking_reply(event: BookingCreationEvent):
    """LISTENER 5: Sets the final reply if one hasn't been set by a previous step."""
    if event.final_reply is None:
        print("  [Listener]: Generating final success reply...")
        # If we got this far without the pipeline stopping, it must be a success.
        event.final_reply = event.analysis.get("reply", "Your booking is confirmed!")