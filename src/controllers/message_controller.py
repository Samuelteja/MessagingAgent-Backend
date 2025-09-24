# src/controllers/message_controller.py
import dateutil.parser
from datetime import timedelta
import asyncio
from sqlalchemy.orm import Session
from .. import schemas, crud, models
from ..services import ai_service, whatsapp_service, tag_pre_scanner
import time
import random
from datetime import datetime, time as time_obj, timezone
from typing import Tuple
from ..services.websocket_manager import manager
from ..crud import crud_analytics, crud_campaign, crud_contact, crud_knowledge, crud_tag, crud_booking, crud_scheduler
from ..schemas import analytics_schemas, campaign_schemas, contact_schemas, knowledge_schemas, tag_schemas, webhook_schemas

# --- CONFIGURATION ---
MIN_DELAY_SECONDS = 1.8
MAX_DELAY_SECONDS = 10.0
CHARS_PER_SECOND_FACTOR = 35

OUTCOME_HIERARCHY = {
    "pending": 0, "unclear": 1, "greeting": 2, "name_provided": 2,
    "inquiry": 3, "booking_incomplete": 4, "request_confirmation": 5,
    "booking_abandoned": 5, "human_handoff": 6, "booking_confirmed": 7,
}
CONVERSATION_RESET_THRESHOLD = timedelta(hours=48)

# ==============================================================================
# --- STAGE 1: BUSINESS & QUIET HOURS CHECK (UPGRADED LOGIC) ---
# ==============================================================================

def _act_on_ai_analysis(db: Session, contact: models.Contact, final_outcome: str, analysis: dict):
    """
    Handles the CONSEQUENCES of the AI's analysis based on the final,
    determined outcome from the state machine.

    This function is responsible for:
    - Applying tags to the contact.
    - Creating bookings in the database.
    - Scheduling follow-up tasks or reminders.
    """
    print(f"🤖 Acting on final determined outcome: '{final_outcome}'")
    entities = analysis.get("entities", {})

    # --- 1. APPLY TAGS (Works for any outcome) ---
    tag_names = analysis.get("tags", [])
    if tag_names:
        print(f"   - AI suggested tags: {tag_names}. Applying to contact {contact.contact_id}...")
        # This function correctly appends and avoids duplicates
        crud_tag.update_tags_for_contact(db, contact_id=contact.contact_id, tag_names=tag_names)

    # --- 2. HANDLE BOOKING & REMINDER CREATION ---
    # This block only runs if the final state is a booking confirmation.
    if final_outcome in ["booking_confirmed", "book_appointment"]:
        print(f"   - Processing booking based on outcome '{final_outcome}'...")
        service = entities.get("service")
        date_str = entities.get("date")
        time_str = entities.get("time")

        if service and date_str and time_str:
            try:
                booking_datetime_str = f"{date_str} {time_str}"
                booking_datetime = dateutil.parser.parse(booking_datetime_str)

                # Recency check to prevent creating duplicate bookings in rapid succession
                most_recent_booking = crud_booking.get_most_recent_booking(db, contact.id)
                is_duplicate = False
                if most_recent_booking:
                    created_at = most_recent_booking.created_at
                    if created_at.tzinfo is None:  # naive datetime
                        created_at = created_at.replace(tzinfo=timezone.utc)
                    time_since = datetime.now(timezone.utc) - created_at
                    if most_recent_booking.service_name.lower() == service.lower() and time_since < timedelta(minutes=5):
                        is_duplicate = True
                
                if is_duplicate:
                    print("   - ✅ Duplicate booking detected (same service < 5 mins). Skipping creation.")
                else:
                    crud_booking.create_booking(db, contact.id, service, booking_datetime)
                    
                    # Check for and schedule reminders
                    existing_reminder = crud_scheduler.get_existing_reminder(db, contact.contact_id, booking_datetime)
                    if not existing_reminder:
                        print("   - Scheduling a new appointment reminder.")
                        reminder_time = booking_datetime - timedelta(hours=24)
                        reminder_content = f"Hi {contact.name or 'there'}! Just a friendly reminder about your appointment for a {service} tomorrow at {booking_datetime.strftime('%I:%M %p')}. We look forward to seeing you!"
                        crud_scheduler.create_scheduled_task(db, contact.contact_id, "APPOINTMENT_REMINDER", reminder_time, reminder_content)
                    else:
                        print("   - ✅ Reminder already exists for this time slot. Skipping.")

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
# --- STAGE 4: DATABASE UPDATE LOGIC (UNCHANGED) ---
# ==============================================================================
# def update_conversation_with_ai_analysis(db: Session, conversation: models.Conversation, analysis: dict):
    # --- THIS SECTION IS MODIFIED with the "Stuck Conversation" bug fix ---
#     intent = analysis.get("intent")
    
    # 1. Update the outcome - with the bug fix
#     if intent in ["BOOKING_CONFIRMED", "HUMAN_HANDOFF"]:
        # --- REFACTOR ---: The "Stuck Conversation" Bug Fix
        # Only update the outcome if the current state is not already 'booking_confirmed'.
#         if conversation.outcome != 'booking_confirmed':
#             conversation.outcome = intent.lower()
#         else:
#             print("INFO: Ignored outcome update because conversation is already confirmed.")
        
        # 2. Automatically create and assign an outcome tag (logic is the same)
#         outcome_tag_name = f"outcome:{intent.lower()}"
#         tag = crud_tag.get_tag_by_name(db, name=outcome_tag_name)
#       if not tag:
#              tag = crud_tag.create_tag(db, schemas.TagCreate(name=outcome_tag_name))
#
#         if tag not in conversation.tags:
#             conversation.tags.append(tag)
#             print(f"✅ Automatically assigned tag: '{outcome_tag_name}'")

#     tag_names = analysis.get("tags", [])
#     if tag_names:
#         contact = conversation.contact
#         print(f"   - AI suggested tags: {tag_names}. Applying to contact {contact.contact_id}...")
#         existing_tag_names = {tag.name for tag in contact.tags}
        
#         new_tags_to_add = []
#         for tag_name in tag_names:
#             if tag_name not in existing_tag_names:
 #                tag = crud_tag.get_tag_by_name(db, name=tag_name)
#                 if tag:
 #                    new_tags_to_add.append(tag)
        
#         if new_tags_to_add:
#             contact.tags.extend(new_tags_to_add)
#             print(f"✅ AI suggested new tags for contact {contact.contact_id}: {[t.name for t in new_tags_to_add]}")
    
#     if intent == "HUMAN_HANDOFF":
#         print(f"🤖 Intent is HUMAN_HANDOFF. Automatically pausing AI for contact {conversation.contact.contact_id}")
        # We reuse the existing CRUD function to set the pause.
        # The default pause is 12 hours, giving the owner plenty of time to respond.
 #        crud_contact.set_ai_pause(db, contact_id=conversation.contact.contact_id)
        
 #    db.commit()

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

    print(f"\n--- New [{channel}] Message Pipeline Started for '{message.pushname or sender_number}' ---")
    
    contact = crud_contact.get_or_create_contact(db, contact_id=sender_number, pushname=message.pushname)
    if contact.ai_is_paused_until and contact.ai_is_paused_until > datetime.now(timezone.utc):
        print(f"-> AI is manually paused for {contact.contact_id}. Ignoring message.")
        # We still log the incoming message for the owner to see in the inbox
        crud_contact.log_conversation(db, channel, contact.id, message_body, None, "received_ignored_ai_paused", "pending")
        await manager.broadcast({"type": "new_message", "contact_id": contact.contact_id})
        return
    
    # Notify the live dashboard that a new message has arrived
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
    last_convo = crud_contact.get_last_conversation(db, contact_id=sender_number)
    current_outcome = "pending"
    if last_convo:
        ts = last_convo.timestamp
        if ts.tzinfo is None:  # naive datetime
            ts = ts.replace(tzinfo=timezone.utc)

        time_since = datetime.now(timezone.utc) - ts
        if time_since < CONVERSATION_RESET_THRESHOLD:
            current_outcome = last_convo.outcome
    db_history = crud_contact.get_chat_history(db, contact_id=sender_number, limit=10)
    is_new_customer_for_ai = not contact.is_name_confirmed
    is_new_interaction = len(db_history) <= 1


    # Fetch recent booking history for context
    recent_bookings = crud_booking.get_recent_and_upcoming_bookings(db, contact.id)
    booking_history_context = "  - This customer has no recent or upcoming appointments."
    if recent_bookings:
        formatted_bookings = [
            f"  - {b.service_name} on {b.booking_datetime.strftime('%A, %B %d')} at {b.booking_datetime.strftime('%I:%M %p')}"
            for b in recent_bookings
        ]
        booking_history_context = "\n".join(formatted_bookings)
    print(f"=> STAGE 2 [{channel}]: Preparing context. New customer for AI? {is_new_customer_for_ai}. New interaction? {is_new_interaction}.")
    # =========================================================================
    
    gemini_history = []
    for msg in reversed(db_history):
        gemini_history.append({'role': 'user', 'parts': [msg.incoming_text]})
        if msg.outgoing_text:
            gemini_history.append({'role': 'model', 'parts': [msg.outgoing_text]})
    gemini_history.append({'role': 'user', 'parts': [message_body]})

    # --- STAGE 3: CALL THE SUPERCHARGED AI BRAIN (Pass the new flag) ---
    print(f"=> STAGE 3 [{channel}]: Calling Supercharged AI Service...")
    if channel == "WhatsApp":
        whatsapp_service.set_typing(sender_number, True)
    
    relevant_tags = tag_pre_scanner.find_relevant_tags(message_body, db)
    analysis = ai_service.analyze_message(
        chat_history=gemini_history, 
        db=db, 
        db_contact=contact,
        is_new_customer=is_new_customer_for_ai,
        is_new_interaction=is_new_interaction,
        relevant_tags=relevant_tags,
        booking_history_context=booking_history_context
    )
    
    ai_reply = analysis.get("reply", "I'm having a little trouble with that request. I've notified our Salon Manager, and they will get back to you here shortly. Thanks for your patience!")
    
    
    # --- STAGE 4: LOG & UPDATE DATABASE ---
    print(f"=> STAGE 4 [{channel}]: Applying state machine logic...")
    
    # 1. Compare current state with AI's new intent
    new_intent_from_ai = analysis.get("intent", "unclear").lower()
    current_value = OUTCOME_HIERARCHY.get(current_outcome, 0)
    new_value = OUTCOME_HIERARCHY.get(new_intent_from_ai, 0)

    # 2. Determine the final outcome for this new conversation entry
    final_outcome = current_outcome
    if new_value > current_value:
        final_outcome = new_intent_from_ai
        print(f"   - State UPGRADE: From '{current_outcome}' -> '{final_outcome}'.")
    else:
        print(f"   - State HELD: Current '{current_outcome}' is >= new intent '{new_intent_from_ai}'.")

    # 3. Log the conversation WITH the final, correct outcome
    new_conversation = crud_contact.log_conversation(
        db=db, channel=channel, contact_db_id=contact.id,
        incoming_text=message_body, outgoing_text=ai_reply,
        status="replied", outcome=final_outcome
    )
    
    # 4. Act on the consequences of the final outcome by calling our helper
    _act_on_ai_analysis(db, contact, final_outcome, analysis)

    extracted_name = analysis.get("entities", {}).get("customer_name")
    if not contact.is_name_confirmed and extracted_name:
        crud_contact.update_contact_name(db, contact_id=sender_number, new_name=extracted_name)
    
    db.commit() # The single, final commit for the entire transaction.
    print(f"=> STAGE 5 [{channel}]: All DB changes committed. Sending reply...")

    # --- STAGE 5: SEND REPLY ---
    print(f"=> STAGE 5 [{channel}]: Sending reply...")
    calculated_delay = len(ai_reply) / CHARS_PER_SECOND_FACTOR
    final_delay = max(MIN_DELAY_SECONDS, min(calculated_delay, MAX_DELAY_SECONDS))
    final_delay += random.uniform(-0.5, 0.5)

    print(f"   - AI Reply Length: {len(ai_reply)} chars. Calculated delay: {final_delay:.2f} seconds.")
    await asyncio.sleep(final_delay)
    
    # This section will be replaced by a unified notification_service on Day 4.
    # For today's deliverable, this is correct.
    if channel == "WhatsApp":
        whatsapp_service.send_reply(phone_number=sender_number, message=ai_reply)
        whatsapp_service.set_typing(sender_number, False)
        
    print(f"--- Pipeline Finished for [{channel}] ---\n")