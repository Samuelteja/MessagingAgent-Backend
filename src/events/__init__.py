# In src/events/__init__.py

from .event_bus import register_listener
from .event_types import (
    BaseEvent, InquiryEvent, GreetingEvent, NameCaptureEvent,
    BookingConfirmationRequestEvent, BookingCreationEvent, BookingAbandonedEvent, HandoffEvent,
    BookingUpdateEvent
)

# --- Import all our new listeners ---
from .booking_listeners import (
    validate_booking_conflict, create_booking_record, schedule_booking_reminder, generate_booking_reply, schedule_short_term_reminder
)
from .abandoned_listeners import schedule_abandoned_cart_followup
from .contact_listeners import update_contact_name, apply_suggested_tags
from .handoff_listeners import pause_ai_for_contact
# from .reschedule_listeners import find_and_validate_original_booking, update_booking_record, reschedule_reminder_task, generate_reschedule_reply
from .update_booking_listeners import find_original_booking, process_booking_updates, process_reminder_updates, generate_update_reply

def register_all_listeners():
    """A single function to set up all event pipelines."""

    # --- Pipeline for simple inquiries ---
    register_listener(InquiryEvent, apply_suggested_tags)
    # register_listener(InquiryEvent, generate_reply_from_suggestion)

    # --- Pipeline for greetings ---
    # register_listener(GreetingEvent, generate_reply_from_suggestion)

    # --- Pipeline for capturing a user's name ---
    register_listener(NameCaptureEvent, update_contact_name)
    # register_listener(NameCaptureEvent, generate_reply_from_suggestion)

    # --- Pipeline for asking the user to confirm a booking ---
    register_listener(BookingConfirmationRequestEvent, apply_suggested_tags)
    # register_listener(BookingConfirmationRequestEvent, generate_reply_from_suggestion)
    
    # --- Pipeline for creating a confirmed booking ---
    register_listener(BookingCreationEvent, validate_booking_conflict)
    register_listener(BookingCreationEvent, create_booking_record)
    register_listener(BookingCreationEvent, schedule_booking_reminder)
    register_listener(BookingCreationEvent, schedule_short_term_reminder)
    register_listener(BookingCreationEvent, apply_suggested_tags)
    register_listener(BookingCreationEvent, generate_booking_reply)
    # register_listener(BookingCreationEvent, generate_booking_reply)

    # --- Pipeline for abandoned bookings ---
    register_listener(BookingAbandonedEvent, schedule_abandoned_cart_followup)
    register_listener(BookingAbandonedEvent, apply_suggested_tags)
    # register_listener(BookingAbandonedEvent, generate_reply_from_suggestion)

    # --- Pipeline for human handoff ---
    register_listener(HandoffEvent, pause_ai_for_contact)
    register_listener(HandoffEvent, apply_suggested_tags)
    # register_listener(HandoffEvent, generate_reply_from_suggestion)

    # --- UNIFIED PIPELINE FOR ALL BOOKING MODIFICATIONS ---
    register_listener(BookingUpdateEvent, find_original_booking)
    register_listener(BookingUpdateEvent, process_booking_updates)
    register_listener(BookingUpdateEvent, process_reminder_updates)
    register_listener(BookingUpdateEvent, generate_update_reply)