# In src/events/booking_listeners.py

from .event_types import BookingCreationEvent
from ..crud import crud_booking, crud_scheduler, crud_tag, crud_knowledge
import dateutil.parser
from datetime import datetime, timedelta, timezone, time as time_obj
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
                f"It looks like you already have a booking for a '{existing_booking.service_name_text}' "
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
            
            event.context["booking_datetime"] = booking_datetime
            new_booking = crud_booking.create_booking(event.db_session, event.contact.id, service, booking_datetime)
            # event.db_session.commit()
            print(f"   - Booking #{new_booking.id} committed to DB by listener.")
    except Exception as e:
        print(f"   - ❌ ERROR in create_booking_record listener: {e}")
        event.stop_processing = True
        event.stop_reason = "Failed to stage booking record in session."

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
                # event.db_session.commit()
                print(f"   - Reminder Task #{new_reminder.id} committed to DB by listener.")
            else:
                print("   - A reminder already exists for this booking. Skipping.")
    except Exception as e:
        print(f"   - ❌ ERROR in schedule_booking_reminder listener: {e}")

def apply_booking_tags(event: BookingCreationEvent):
    """LISTENER 4: Applies any AI-suggested tags."""
    if event.stop_processing: return
    print("  [Listener]: Running apply_booking_tags...")
    
    try:
        db = event.db_session 
        action_params = event.analysis.get("action_params", {})
        updated_state = action_params.get("updated_state", {})
        context = updated_state.get("context", {})
        tags_to_apply = set(context.get("tags", []))
        
        if tags_to_apply:
            crud_tag.update_tags_for_contact(db, event.contact.contact_id, list(tags_to_apply))
            print("   - Tag updates staged in session by listener.")
    except Exception as e:
        print(f"   - ❌ ERROR in apply_booking_tags listener: {e}")

def generate_booking_reply(event: BookingCreationEvent):
    """LISTENER 5: Sets the final reply if one hasn't been set by a previous step."""
    if event.final_reply is None:
        print("  [Listener]: Generating final success reply...")
        # If we got this far without the pipeline stopping, it must be a success.
        event.final_reply = event.analysis.get("reply", "Your booking is confirmed!")

def _is_time_in_quiet_hours(quiet_start: time_obj, quiet_end: time_obj, time_to_check: time_obj) -> bool:
    """Helper function to check if a time falls within the quiet hours range."""
    if not quiet_start or not quiet_end:
        return False # No quiet hours configured

    if quiet_start <= quiet_end:
        return quiet_start <= time_to_check < quiet_end
    else: # Overnight range
        return time_to_check >= quiet_start or time_to_check < quiet_end

def schedule_short_term_reminder(event: BookingCreationEvent):
    """
    LISTENER: Schedules an additional 6-hour reminder for a booking, but only
    if the send time does not fall within the business's configured quiet hours.
    """
    if event.stop_processing: return
    
    print("  [Listener]: Running schedule_short_term_reminder...")
    
    try:
        entities = event.analysis.get("action_params", {})
        service_name = entities.get("service")
        
        # Get the booking datetime from the event's context, which was set by a previous listener.
        # This is more reliable than re-parsing from the AI analysis.
        booking_datetime = event.context.get("booking_datetime")
        if not (service_name and booking_datetime):
            print("   - ⚠️ Could not find service or booking_datetime in event context. Skipping.")
            return

        # 1. Calculate the proposed 6-hour reminder time
        proposed_reminder_time = booking_datetime - timedelta(hours=6)

        # 2. Fetch the business hours for the day the reminder would be sent
        business_hours_list = crud_knowledge.get_business_hours(event.db_session)
        hours_map = {h.day_of_week: h for h in business_hours_list}
        
        reminder_day_of_week = proposed_reminder_time.weekday() # Monday=0, Sunday=6
        todays_hours = hours_map.get(reminder_day_of_week)

        # 3. Perform the "Quiet Hours" check
        if todays_hours and _is_time_in_quiet_hours(todays_hours.quiet_hours_start, todays_hours.quiet_hours_end, proposed_reminder_time.time()):
            print(f"   - ❌ Proposed 6-hour reminder time ({proposed_reminder_time.strftime('%I:%M %p')}) falls within quiet hours. Skipping.")
            return
        
        # 4. If the check passes, schedule the task
        reminder_content = f"Hi {event.contact.name or 'there'}! This is a quick reminder about your {service_name} appointment with us in about 6 hours, at {booking_datetime.strftime('%I:%M %p')}. See you soon! 😊"
        
        crud_scheduler.create_scheduled_task(
            db=event.db_session,
            contact_id=event.contact.contact_id,
            task_type="SHORT_TERM_APPOINTMENT_REMINDER", # Use a distinct type
            scheduled_time=proposed_reminder_time,
            content=reminder_content
        )
        print(f"   - ✅ Successfully scheduled a 6-hour reminder for {proposed_reminder_time}.")

    except Exception as e:
        print(f"   - ❌ ERROR in schedule_short_term_reminder listener: {e}")