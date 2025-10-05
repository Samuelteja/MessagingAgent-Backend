# src/controllers/message_controller.py
import dateutil.parser
from datetime import timedelta
import asyncio
from sqlalchemy.orm import Session
from .utils import deep_convert_to_dict
from sqlalchemy.orm.attributes import flag_modified
from .. import schemas, crud, models
from ..services import ai_service, whatsapp_service, tag_pre_scanner
import time
import random
from datetime import datetime, time as time_obj, timezone, timedelta
from ..events.event_bus import dispatch
from ..events.event_types import (
    BaseEvent, InquiryEvent, GreetingEvent, NameCaptureEvent,
    BookingConfirmationRequestEvent, BookingCreationEvent, BookingAbandonedEvent, HandoffEvent,
    BookingUpdateEvent
)
from typing import Tuple
from ..services.websocket_manager import manager
from ..crud import crud_analytics, crud_campaign, crud_contact, crud_knowledge, crud_tag, crud_booking, crud_scheduler
from ..schemas import analytics_schemas, campaign_schemas, contact_schemas, knowledge_schemas, tag_schemas, webhook_schemas
from . import reconciliation_controller

# --- CONFIGURATION ---
MIN_DELAY_SECONDS = 1.8
MAX_DELAY_SECONDS = 10.0
CHARS_PER_SECOND_FACTOR = 35
CONVERSATION_RESET_THRESHOLD = timedelta(hours=48)

OUTCOME_HIERARCHY = {
    "pending": 0, "unclear": 1, "answer_inquiry": 2,
    "capture_customer_name": 2, # Capture name is also a simple step
    "schedule_lead_follow_up": 3, # <-- GIVE THIS A PROPER VALUE
    "request_booking_confirmation": 5,
    "handoff_to_human": 6,
    "create_booking": 7,
    "booking_confirmed": 7,
}
CONVERSATION_RESET_THRESHOLD = timedelta(hours=48)

# ==============================================================================
# --- STAGE 1: BUSINESS & QUIET HOURS CHECK (UPGRADED LOGIC) ---
# ==============================================================================

def _act_on_ai_analysis(db: Session, contact: models.Contact, final_outcome: str, analysis: dict):
    """
    Handles the CONSEQUENCES of the AI's analysis based on the final,
    determined outcome from the state machine.
    """
    print(f"🤖 Acting on final determined outcome: '{final_outcome}'")
    entities = analysis.get("entities", {})

    # --- 1. APPLY TAGS (Works for any outcome) ---
    tag_names = analysis.get("tags", [])
    if tag_names:
        crud_tag.update_tags_for_contact(db, contact_id=contact.contact_id, tag_names=tag_names)

    # --- 2. HANDLE BOOKING & REMINDER CREATION ---
    if final_outcome in ["booking_confirmed", "book_appointment"]:
        print(f"   - Processing booking based on outcome '{final_outcome}'...")
        service = entities.get("service")
        date_str = entities.get("date")
        time_str = entities.get("time")

        if service and date_str and time_str:
            try:
                booking_datetime_str = f"{date_str} {time_str}"
                booking_datetime = dateutil.parser.parse(booking_datetime_str)
                crud_booking.create_booking(db, contact.id, service, booking_datetime)
                existing_reminder = crud_scheduler.get_existing_reminder(db, contact.contact_id, booking_datetime)
                if not existing_reminder:
                    reminder_time = booking_datetime - timedelta(hours=24)
                    reminder_content = f"Hi {contact.name or 'there'}! Reminder for your {service} appointment tomorrow at {booking_datetime.strftime('%I:%M %p')}."
                    crud_scheduler.create_scheduled_task(db, contact.contact_id, "APPOINTMENT_REMINDER", reminder_time, reminder_content)

            except dateutil.parser.ParserError as e:
                print(f"   - ❌ Error parsing date/time from AI entities: {e}")
        else:
            print("   - ⚠️ Warning: Booking outcome received, but missing service, date, or time entities.")

    # --- 3. HANDLE FOLLOW-UP SCHEDULING ---
    # This block only runs if the final state is an incomplete or abandoned booking.
    if final_outcome in ["booking_incomplete", "booking_abandoned"]:
        print(f"   - Outcome is '{final_outcome}'. Scheduling a lead follow-up.")
        
        # Check if a follow-up for this contact already exists to avoid spamming
        existing_followup = db.query(models.ScheduledTask).filter(
            models.ScheduledTask.contact_id == contact.contact_id,
            models.ScheduledTask.task_type == "LEAD_FOLLOWUP",
            models.ScheduledTask.status == "pending"
        ).first()

        if not existing_followup:
            follow_up_time = datetime.now(timezone.utc) + timedelta(hours=24)
            service = entities.get("service", "your appointment")
            follow_up_content = f"Hi {contact.name or 'there'}, just following up. You were about to book a {service} with us. We may still have slots available. Would you like to continue?"
            crud_scheduler.create_scheduled_task(db, contact.contact_id, "LEAD_FOLLOWUP", follow_up_time, follow_up_content)
        else:
            print(f"   - ✅ A pending follow-up already exists (Task ID: {existing_followup.id}). Skipping new follow-up creation.")

    print("🤖 Finished acting on AI analysis.")

def _is_time_in_range(start: time_obj, end: time_obj, current: time_obj) -> bool:
    """
    Helper function to correctly check if a time is within a range,
    handling overnight ranges (e.g., 22:00 to 06:00).
    """
    if start <= end:
        # Normal, same-day range (e.g., 09:00 to 17:00)
        return start <= current <= end
    else:
        # Overnight range (e.g., 22:00 to 06:00)
        # The time is valid if it's after the start OR before the end.
        return current >= start or current < end

def get_business_status(db: Session) -> Tuple[str, str]:
    """
    Checks the business's current status using the robust time checker.
    Returns a tuple: (status: str, off_hours_message: str)
    status can be: "OPEN", "CLOSED_QUIET", "CLOSED_AWAKE"
    """
    business_hours_list = crud_knowledge.get_business_hours(db)
    if not business_hours_list:
        return ("OPEN", "") # Default to OPEN if no hours are configured

    hours_map = {h.day_of_week: h for h in business_hours_list}
    now = datetime.now()
    current_day = now.weekday() # Monday is 0, Sunday is 6
    current_time = now.time()

    todays_hours = hours_map.get(current_day)

    # If no hours are set for today at all (e.g., Sunday is missing from DB)
    if not todays_hours:
        return ("CLOSED_AWAKE", "Thanks for your message! We appear to be closed today, but our team will review your message when we're back.")

    # Rule 1: Check for Quiet Hours first (highest priority)
    if todays_hours.quiet_hours_start and todays_hours.quiet_hours_end:
        if _is_time_in_range(todays_hours.quiet_hours_start, todays_hours.quiet_hours_end, current_time):
            return ("CLOSED_QUIET", "")

    # Rule 2: Check for regular Business Hours
    if todays_hours.open_time and todays_hours.close_time:
         if _is_time_in_range(todays_hours.open_time, todays_hours.close_time, current_time):
            return ("OPEN", "")

    # Rule 3: If neither of the above, we are "closed but awake"
    off_hours_msg = "Thanks for your message! We are currently closed."
    if todays_hours.open_time and todays_hours.close_time:
        # Provide a more helpful message if we know the hours
        off_hours_msg = f"Thanks for your message! Our hours today are from {todays_hours.open_time.strftime('%I:%M %p')} to {todays_hours.close_time.strftime('%I:%M %p')}. We'll get back to you as soon as we reopen!"
    
    return ("CLOSED_AWAKE", off_hours_msg)

# ==============================================================================
# --- THE NEW, FULLY REFACTORED MAIN CONTROLLER ---
# ==============================================================================
async def process_incoming_message(message: webhook_schemas.NormalizedMessage, db: Session):
    """
    This is the core logic pipeline. It is now completely independent of the
    message source (WhatsApp, Instagram, etc.).
    """
    # --- STAGE 0: INITIALIZE & BROADCAST ---
    sender_number = message.contact_id
    message_body = message.body
    channel = message.channel

    contact = crud_contact.get_or_create_contact(db, contact_id=sender_number, pushname=message.pushname)
    
    if contact.role == 'manager':
        print(f"-> Message from Manager ({contact.contact_id}) detected. Routing to Reconciliation Controller.")
        reconciliation_controller.process_manager_reconciliation(message, db)
        return
    
    if contact.ai_is_paused_until:
        pause_timestamp = contact.ai_is_paused_until
        
        # Make the timestamp from the DB "aware" of the UTC timezone
        if pause_timestamp.tzinfo is None:
            pause_timestamp = pause_timestamp.replace(tzinfo=timezone.utc)
        
        # Now, the comparison is safe and correct
        if pause_timestamp > datetime.now(timezone.utc):
            print(f"-> AI is manually paused for {contact.contact_id}. Ignoring message.")
            crud_contact.log_conversation(db, message.channel, contact.id, message.body, None, "received_ignored_ai_paused", "pending")
            await manager.broadcast({"type": "new_message", "contact_id": contact.contact_id})
            return
    
    await manager.broadcast({"type": "new_message", "contact_id": contact.contact_id})

    status, off_hours_message = get_business_status(db)

    if status == "CLOSED_QUIET":
        print(f"=> STAGE 1 [{channel}]: Business in 'Quiet Hours'. Ignoring.")
        crud_contact.log_conversation(db, channel, contact.id, message_body, None, "received_ignored_quiet_hours", "pending")
        return

    if status == "CLOSED_AWAKE":
        print(f"=> STAGE 1 [{channel}]: Business closed, but not in quiet hours.")
        last_convo = crud_contact.get_last_conversation(db, contact_id=sender_number)

        # Check if the last message was ALSO an off-hours reply to prevent spamming
        if last_convo and last_convo.status == "replied_off_hours":
            print("   - Already sent off-hours message recently. Ignoring.")
            # We still log the incoming message, but we don't reply.
            # The outcome remains the same as the last message to preserve state.
            crud_contact.log_conversation(
                db=db,
                channel=channel,
                contact_db_id=contact.id,
                incoming_text=message_body,
                outgoing_text=None,
                status="received_ignored_off_hours",
                outcome=last_convo.outcome # Inherit the last outcome
            )
            db.commit() # Commit this log entry
            return
        else:
            print("   - Sending off-hours message.")
            # When we send an off-hours reply, the conversation state is reset or held at "pending".
            crud_contact.log_conversation(
                db=db,
                channel=channel,
                contact_db_id=contact.id,
                incoming_text=message_body,
                outgoing_text=off_hours_message,
                status="replied_off_hours",
                outcome="pending" # Reset the outcome to pending for the next interaction
            )
            db.commit() # Commit this log entry before sending the message

            if channel == "WhatsApp":
                whatsapp_service.send_reply(sender_number, off_hours_message)
            
            print(f"--- Pipeline Finished (Off Hours Reply Sent) for [{channel}] ---\n")
            return
    
    print(f"=> STAGE 1 [{channel}]: Business is OPEN. Proceeding...")
    # --- STAGE 2: PREPARE CONVERSATION HISTORY ---
    print(f"=> STAGE 2 [{message.channel}]: Preparing context with conversational memory...")

    current_state = contact.conversation_state
    if not current_state:
        print("   - Empty state detected. Initializing state for a new conversation.")
        current_state = {
            "goal": "GENERAL_INQUIRY",
            "goal_params": {},
            "context": {}
        }
    state_for_ai = current_state.copy()

    last_convo = crud_contact.get_last_conversation(db, contact_id=sender_number)
    current_outcome = "pending"
    if last_convo:
        ts = last_convo.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)

        if (datetime.now(timezone.utc) - ts) > CONVERSATION_RESET_THRESHOLD:
            print("   - Stale conversation detected. Ignoring previous AI 'goal' for this turn.")
            if 'goal' in state_for_ai: state_for_ai['goal'] = None
            if 'goal_params' in state_for_ai: state_for_ai['goal_params'] = {}

    db_history = crud_contact.get_chat_history(db, contact_id=sender_number, limit=10)
    
    # Fetch recent booking history for context
    recent_bookings = crud_booking.get_recent_and_upcoming_bookings(db, contact.id)
    booking_history_context = "  - This customer has no recent or upcoming appointments."
    is_potential_duplicate = False
    if recent_bookings:
        formatted_bookings = [
            f"  - {b.service_name_text} on {b.booking_datetime.strftime('%A, %B %d')} at {b.booking_datetime.strftime('%I:%M %p')}"
            for b in recent_bookings
        ]
        booking_history_context = "This customer has the following recent or upcoming appointments:\n" + "\n".join(formatted_bookings)
        for booking in recent_bookings:
            if booking.service_name_text.lower() in message_body.lower():
                is_potential_duplicate = True
                print("   - POTENTIAL DUPLICATE DETECTED by backend pre-check.")
                break
    # print(f"=> STAGE 2 [{channel}]: Preparing context. New customer for AI? {is_new_customer_for_ai}. New interaction? {is_new_interaction}.")
    # =========================================================================
    
    is_new_customer_for_ai = not contact.is_name_confirmed
    is_new_interaction = len(db_history) == 0

    gemini_history = []
    for msg in reversed(db_history):
        gemini_history.append({'role': 'user', 'parts': [msg.incoming_text]})
        if msg.outgoing_text:
            gemini_history.append({'role': 'model', 'parts': [msg.outgoing_text]})
    gemini_history.append({'role': 'user', 'parts': [message_body]})

    # --- STAGE 3 (REVISED): CALL AI WITH MEMORY ---
    print(f"=> STAGE 3 [{channel}]: Calling Supercharged AI Service...")
    if channel == "WhatsApp":
        whatsapp_service.set_typing(sender_number, True)
    
    relevant_tags = tag_pre_scanner.find_relevant_tags(message_body, db)
    command = ai_service.analyze_message(
        conversation_state=state_for_ai,
        chat_history=gemini_history,
        db=db,
        db_contact=contact,
        relevant_tags=relevant_tags
    )
    
    if not command:
        command = {"name": "handoff_to_human", "args": {"reason": "AI failed to select a tool."}}

    function_name = command.get("name")
    function_args = {}
    if command and "args" in command:
        function_args = deep_convert_to_dict(command["args"])
    print(f"=> STAGE 4: AI returned tool '{function_name}'. Dispatching event...")
    
    analysis_payload = {"action_params": function_args}
    event = None
    if function_name == "create_booking":
        event = BookingCreationEvent(contact=contact, db_session=db, analysis=analysis_payload)
        dispatch(event)
    elif function_name == "update_booking":
        event = BookingUpdateEvent(contact=contact, db_session=db, analysis=analysis_payload)
        dispatch(event)
    elif function_name == "request_booking_confirmation":
        event = BookingConfirmationRequestEvent(contact=contact, db_session=db, analysis=analysis_payload)
        dispatch(event)
    elif function_name == "schedule_lead_follow_up":
        event = BookingAbandonedEvent(contact=contact, db_session=db, analysis=analysis_payload)
        dispatch(event)
    elif function_name == "handoff_to_human":
        event = HandoffEvent(contact=contact, db_session=db, analysis=analysis_payload)
        dispatch(event)
    elif function_name == "capture_customer_name":
        event = NameCaptureEvent(contact=contact, db_session=db, analysis=analysis_payload)
        dispatch(event)
    else:
        event = InquiryEvent(contact=contact, db_session=db, analysis=analysis_payload)
        dispatch(event)


    final_reply = event.final_reply or "I'm sorry, I seem to be having a technical issue. A team member will be with you shortly."

    if event.stop_processing:
        # If the pipeline was stopped (e.g., by a booking conflict), the final_reply was set by the listener.
        final_reply = event.final_reply
    else:
        # If the pipeline succeeded, we generate the reply based on the action
        if function_name == "create_booking":
            final_reply = "Great, your appointment is confirmed! We look forward to seeing you."
        elif function_name == "handoff_to_human":
            final_reply = "That's a good question. I'm connecting you with our Salon Manager now, they will reply here shortly. 😊"
        else: # For all other cases (inquiry, greeting, name capture etc.)
            final_reply = function_args.get('reply_suggestion', final_reply)

    new_outcome = function_name.lower()

    is_duplicate_inquiry = (
        current_outcome == 'booking_confirmed' and 
        new_outcome == 'answer_inquiry' and 
        is_potential_duplicate # The flag we set earlier
    )

    is_fresh_conversation = False
    if last_convo:
        ts = last_convo.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if (datetime.now(timezone.utc) - ts) < CONVERSATION_RESET_THRESHOLD:
            is_fresh_conversation = True

    is_modification_request = new_outcome in ["update_booking", "reschedule_booking"]

    if is_fresh_conversation and current_outcome == 'booking_confirmed' and not is_modification_request:
        final_outcome = current_outcome
        print(f"   - State LOCKED: Fresh, confirmed conversation and new intent is not a modification. State remains '{final_outcome}'.")
    else:
        final_outcome = new_outcome
        print(f"   - State Update: New conversation, stale conversation, or a modification request. State is now '{final_outcome}'.")
    
    if final_outcome == 'create_booking':
        final_outcome = 'booking_confirmed'
    elif final_outcome == 'request_booking_confirmation':
        final_outcome = 'request_confirmation'

    # --- STAGE 5 (RENAMED): PERSIST & RETIRE CONVERSATIONAL STATE ---
    raw_updated_state  = function_args.get("updated_state")
    if raw_updated_state:
        clean_updated_state = deep_convert_to_dict(raw_updated_state)
        print(f"   - AI returned new state. Persisting: {clean_updated_state}")
        contact.conversation_state = clean_updated_state
    else:
        print(f"   - AI did not return a new state. Preserving existing state.")
        contact.conversation_state = state_for_ai

    # "State Retirement" for terminal outcomes
    if final_outcome in ["booking_confirmed", "human_handoff"]:
        print(f"   - Terminal outcome '{final_outcome}' reached. Retiring active state.")
        if contact.conversation_state:
            # We create a new dict to avoid modifying the old one in place
            retired_state = dict(contact.conversation_state)
            retired_state["goal"] = None
            retired_state["goal_params"] = {}
            contact.conversation_state = retired_state
    
    # This is CRUCIAL. It tells SQLAlchemy that the JSON field has been
    # changed and needs to be included in the UPDATE statement.
    flag_modified(contact, "conversation_state")
    # ====================================================

    print(f"=> STAGE 6: Logging final outcome '{final_outcome}' and sending reply.")

    # Log the full exchange with the FINAL reply generated by our system.
    crud_contact.log_conversation(
        db=db,
        channel=message.channel,
        contact_db_id=contact.id,
        incoming_text=message.body,
        outgoing_text=final_reply,
        status="replied",
        outcome=final_outcome
    )
    
    db.commit()

    print("=> STAGE 6: Broadcasting full conversation update via WebSocket...")
    try:
        # We need the most recent conversation record we just saved
        # The 'contact' object already has its conversations relationship loaded
        final_convo_obj = contact.conversations[-1]

        # Use the Pydantic schema to serialize the SQLAlchemy object into a dictionary
        # This guarantees the structure matches the REST API
        serialized_convo = contact_schemas.Conversation.from_orm(final_convo_obj).dict()

        await manager.broadcast({
            "type": "conversation_update",
            "conversation": serialized_convo
        })
        print("   - ✅ Successfully broadcasted 'conversation_update'.")
    except Exception as e:
        print(f"   - ❌ ERROR during WebSocket broadcast: {e}")
    
    # --- STAGE 5: SEND REPLY ---
    print(f"=> STAGE 5 [{channel}]: Sending reply...")
    calculated_delay = len(final_reply) / CHARS_PER_SECOND_FACTOR
    final_delay = max(MIN_DELAY_SECONDS, min(calculated_delay, MAX_DELAY_SECONDS))
    final_delay += random.uniform(-0.5, 0.5)

    print(f"   - AI Reply Length: {len(final_reply)} chars. Calculated delay: {final_delay:.2f} seconds.")
    await asyncio.sleep(final_delay)
    
    if channel == "WhatsApp":
        whatsapp_service.send_reply(phone_number=sender_number, message=final_reply)
        whatsapp_service.set_typing(sender_number, False)
        
    print(f"--- Pipeline Finished for [{channel}] ---\n")