# # In src/events/reschedule_listeners.py

# from .event_types import BookingRescheduleEvent
# from ..crud import crud_booking, crud_scheduler
# import dateutil.parser
# from datetime import timedelta
# from ..database import SessionLocal

# def find_and_validate_original_booking(event: BookingRescheduleEvent):
#     """LISTENER 1: Finds the original booking and validates the request."""
#     print("  [Listener]: Running find_and_validate_original_booking...")
#     db = event.db_session
#     booking_to_change = crud_booking.get_most_recent_booking(db, contact_db_id=event.contact.id)

#     if not booking_to_change:
#         event.stop_processing = True
#         event.stop_reason = "Original booking not found."
#         event.final_reply = "I'm sorry, I couldn't find that specific appointment to reschedule. Could you please clarify the service and original time?"
#         return
    
#     # Attach the found booking to the event object for the next listeners to use
#     event.context["booking_to_change"] = booking_to_change

# def update_booking_record(event: BookingRescheduleEvent):
#     """LISTENER 2: Updates the booking with the new date and time."""
#     if event.stop_processing: return
#     print("  [Listener]: Running update_booking_record...")
#     db = event.db_session
#     booking_to_change = event.context.get("booking_to_change")
#     params = event.analysis.get("action_params", {})
#     new_date = params.get("new_date")
#     new_time = params.get("new_time")

#     if booking_to_change and new_date and new_time:
#         new_datetime = dateutil.parser.parse(f"{new_date} {new_time}")
        
#         # We can reuse the existing update CRUD function
#         updated_booking = crud_booking.update_booking_time(db, booking_to_change.id, new_datetime)
#         event.context["updated_booking"] = updated_booking

# def reschedule_reminder_task(event: BookingRescheduleEvent):
#     """LISTENER 3: Deletes the old reminder and creates a new one."""
#     if event.stop_processing: return
#     print("  [Listener]: Running reschedule_reminder_task...")

#     booking_to_change = event.context.get("booking_to_change") # The original booking
#     updated_booking = event.context.get("updated_booking")   # The updated booking
    
#     if not booking_to_change or not updated_booking:
#         return
    
#     # db = SessionLocal()

#     try:

#         old_reminder = crud_scheduler.get_reminder_for_booking(event.db_session, event.contact.contact_id, booking_to_change.booking_datetime)
#         print(f"   - Found old reminder: {old_reminder}")
#         if old_reminder:
#             crud_scheduler.delete_scheduled_task(event.db_session, old_reminder.id)
#             print(f"   - Old reminder #{old_reminder.id} marked for deletion.")

#         new_reminder_time = updated_booking.booking_datetime - timedelta(hours=24)
#         new_content = f"Hi {event.contact.name or 'there'}! Your appointment for {updated_booking.service_name} has been successfully rescheduled to {updated_booking.booking_datetime.strftime('%A at %I:%M %p')}."
#         crud_scheduler.create_scheduled_task(
#             db=event.db_session,
#             contact_id=event.contact.contact_id,
#             task_type="APPOINTMENT_REMINDER",
#             scheduled_time=new_reminder_time,
#             content=new_content
#         )
#         # event.db_session.commit()
#         print("   - Reschedule reminder transaction committed successfully.")
#     finally:
#         pass

# def generate_reschedule_reply(event: BookingRescheduleEvent):
#     """LISTENER 4: Generates the final confirmation reply."""
#     if event.final_reply: return
#     print("  [Listener]: Running generate_reschedule_reply...")
#     updated_booking = event.context.get("updated_booking")
#     if updated_booking:
#         event.final_reply = f"You're all set! I've successfully moved your {updated_booking.service_name} appointment to {updated_booking.booking_datetime.strftime('%A at %I:%M %p')}. We'll see you then!"
