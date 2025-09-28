# src/events/edit_service_listeners.py
import dateutil.parser
from datetime import timedelta
from .event_types import BookingUpdateEvent
from ..crud import crud_booking, crud_scheduler, crud_menu
from .. import models

def find_original_booking(event: BookingUpdateEvent):
    """
    LISTENER 1: Finds the original booking based on the service name.
    Stops the pipeline if a valid booking isn't found.
    """
    print("  [Listener]: Running find_original_booking...")
    db = event.db_session
    params = event.analysis.get("action_params", {})
    original_service_name = params.get("original_service")

    if not original_service_name:
        event.stop_processing = True
        event.stop_reason = "AI did not provide the original service name."
        event.final_reply = "I'm sorry, I'm having trouble identifying which appointment you'd like to change. Could you please clarify the service?"
        return

    booking_to_change = crud_booking.get_most_recent_booking_by_service(
        db, contact_db_id=event.contact.id, service_name=original_service_name
    )

    if not booking_to_change:
        event.stop_processing = True
        event.stop_reason = f"Could not find a booking for '{original_service_name}'."
        event.final_reply = f"I couldn't find a recent booking for a '{original_service_name}'. Would you like to make a new booking instead?"
        return
    
    event.context["booking_to_change"] = booking_to_change
    print(f"   - Found original Booking #{booking_to_change.id} to update.")

def process_booking_updates(event: BookingUpdateEvent):
    """
    LISTENER 2: The smart update handler. It applies changes to the booking
    object in the session based on the parameters provided by the AI.
    """
    if event.stop_processing: return
    print("  [Listener]: Running process_booking_updates...")
    db = event.db_session
    booking_to_update = event.context.get("booking_to_change")
    params = event.analysis.get("action_params", {})
    
    changes_made = []

    # Scenario 1: Update the Service
    new_service_name = params.get("new_service")
    if new_service_name:
        new_menu_item = db.query(models.MenuItem).filter(models.MenuItem.name == new_service_name).first()
        if new_menu_item:
            booking_to_update.service_id = new_menu_item.id
            booking_to_update.service_name_text = new_menu_item.name
            changes_made.append(f"service to '{new_service_name}'")
        else:
            event.stop_processing = True
            event.stop_reason = f"Requested new service '{new_service_name}' does not exist."
            event.final_reply = f"I'm sorry, I couldn't find '{new_service_name}' on our menu. Please choose a valid service."
            return

    # Scenario 2: Update the Date and/or Time
    new_date_str = params.get("new_date")
    new_time_str = params.get("new_time")
    if new_date_str or new_time_str:
        try:
            # Cleverly handle partial updates: use original date/time as fallback
            original_date = booking_to_update.booking_datetime.date()
            original_time = booking_to_update.booking_datetime.time()
            
            final_date_str = new_date_str or original_date.strftime('%Y-%m-%d')
            final_time_str = new_time_str or original_time.strftime('%H:%M')

            new_datetime = dateutil.parser.parse(f"{final_date_str} {final_time_str}")
            booking_to_update.booking_datetime = new_datetime
            changes_made.append(f"time to {new_datetime.strftime('%A, %B %d at %I:%M %p')}")
        except dateutil.parser.ParserError:
            event.stop_processing = True
            event.stop_reason = "AI provided an invalid date/time format."
            event.final_reply = "I'm sorry, I couldn't understand the new date or time. Could you please provide it again?"
            return

    if not changes_made:
        event.stop_processing = True
        event.stop_reason = "AI called update_booking but provided no new details."
        event.final_reply = "I see you'd like to make a change. What would you like to update?"
        return

    event.context["changes_made"] = changes_made
    event.context["updated_booking"] = booking_to_update
    print(f"   - Staged updates for Booking #{booking_to_update.id}: {', '.join(changes_made)}.")


def process_reminder_updates(event: BookingUpdateEvent):
    """
    LISTENER 3: Intelligently updates the reminder. Deletes and creates a new
    one if the time changed; only updates content if the service changed.
    """
    if event.stop_processing: return
    print("  [Listener]: Running process_reminder_updates...")
    db = event.db_session
    original_booking = event.context.get("booking_to_change")
    updated_booking = event.context.get("updated_booking")

    time_changed = original_booking.booking_datetime != updated_booking.booking_datetime

    # Find the reminder associated with the ORIGINAL booking time
    old_reminder = crud_scheduler.get_reminder_for_booking(
        db, contact_id=event.contact.contact_id, booking_datetime=original_booking.booking_datetime
    )

    if time_changed:
        if old_reminder:
            crud_scheduler.delete_scheduled_task(db, task_id=old_reminder.id)
            print(f"   - Old reminder #{old_reminder.id} marked for deletion.")
        
        # Create a new reminder for the new time
        new_reminder_time = updated_booking.booking_datetime - timedelta(hours=24)
        new_content = f"Hi {event.contact.name or 'there'}! Reminder for your {updated_booking.service_name_text} appointment tomorrow at {updated_booking.booking_datetime.strftime('%I:%M %p')}."
        crud_scheduler.create_scheduled_task(db, event.contact.contact_id, "APPOINTMENT_REMINDER", new_reminder_time, new_content)
        print("   - Created a new reminder for the updated time.")
    
    elif old_reminder: # Time did NOT change, but service might have.
        # Just update the content of the existing reminder
        new_content = f"Hi {event.contact.name or 'there'}! Reminder for your updated appointment (now a {updated_booking.service_name_text}) tomorrow at {updated_booking.booking_datetime.strftime('%I:%M %p')}."
        crud_scheduler.update_scheduled_task(db, task_id=old_reminder.id, new_scheduled_time=old_reminder.scheduled_time, new_content=new_content)
        print(f"   - Updated content for existing reminder #{old_reminder.id}.")


def generate_update_reply(event: BookingUpdateEvent):
    """
    LISTENER 4: Crafts a dynamic final reply summarizing the changes made.
    """
    if event.final_reply: return # Don't overwrite a reply set by a previous step
    print("  [Listener]: Running generate_update_reply...")
    
    changes = event.context.get("changes_made", [])
    if not changes:
        return

    # Build a natural-sounding confirmation message
    reply_prefix = "You're all set! I've successfully updated your appointment"
    changes_str = " and ".join(changes)
    
    event.final_reply = f"{reply_prefix} {changes_str}. We look forward to seeing you!"