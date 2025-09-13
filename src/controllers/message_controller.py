# src/controllers/message_controller.py
import asyncio
from sqlalchemy.orm import Session
from .. import schemas, crud, models
from ..services import ai_service, whatsapp_service
import time
import random
from datetime import datetime, time as time_obj, timezone
from typing import Tuple
from ..services.websocket_manager import manager
from ..crud import crud_analytics, crud_campaign, crud_contact, crud_knowledge, crud_tag
from ..schemas import analytics_schemas, campaign_schemas, contact_schemas, knowledge_schemas, tag_schemas, webhook_schemas

# --- CONFIGURATION ---
MIN_DELAY_SECONDS = 1.8
MAX_DELAY_SECONDS = 10.0
CHARS_PER_SECOND_FACTOR = 35

# ==============================================================================
# --- STAGE 1: BUSINESS & QUIET HOURS CHECK (UPGRADED LOGIC) ---
# ==============================================================================

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
def update_conversation_with_ai_analysis(db: Session, conversation: models.Conversation, analysis: dict):
    # --- THIS SECTION IS MODIFIED with the "Stuck Conversation" bug fix ---
    intent = analysis.get("intent")
    
    # 1. Update the outcome - with the bug fix
    if intent in ["BOOKING_CONFIRMED", "HUMAN_HANDOFF"]:
        # --- REFACTOR ---: The "Stuck Conversation" Bug Fix
        # Only update the outcome if the current state is not already 'booking_confirmed'.
        if conversation.outcome != 'booking_confirmed':
            conversation.outcome = intent.lower()
        else:
            print("INFO: Ignored outcome update because conversation is already confirmed.")
        
        # 2. Automatically create and assign an outcome tag (logic is the same)
        outcome_tag_name = f"outcome:{intent.lower()}"
        tag = crud_tag.get_tag_by_name(db, name=outcome_tag_name)
        if not tag:
            tag = crud_tag.create_tag(db, schemas.TagCreate(name=outcome_tag_name))
        
        if tag not in conversation.tags:
            conversation.tags.append(tag)
            print(f"✅ Automatically assigned tag: '{outcome_tag_name}'")

    tag_names = analysis.get("tags", [])
    if tag_names:
        contact = conversation.contact
        
        existing_tag_names = {tag.name for tag in contact.tags}
        
        new_tags_to_add = []
        for tag_name in tag_names:
            if tag_name not in existing_tag_names:
                tag = crud_tag.get_tag_by_name(db, name=tag_name)
                if tag:
                    new_tags_to_add.append(tag)
        
        if new_tags_to_add:
            contact.tags.extend(new_tags_to_add)
            print(f"✅ AI suggested new tags for contact {contact.contact_id}: {[t.name for t in new_tags_to_add]}")
    
    if intent == "HUMAN_HANDOFF":
        print(f"🤖 Intent is HUMAN_HANDOFF. Automatically pausing AI for contact {conversation.contact.contact_id}")
        # We reuse the existing CRUD function to set the pause.
        # The default pause is 12 hours, giving the owner plenty of time to respond.
        crud_contact.set_ai_pause(db, contact_id=conversation.contact.contact_id)
        
    db.commit()

# ==============================================================================
# --- THE NEW, FULLY REFACTORED MAIN CONTROLLER ---
# ==============================================================================
async def process_incoming_message(message: webhook_schemas.NormalizedMessage, db: Session):
    """
    This is the core logic pipeline. It is now completely independent of the
    message source (WhatsApp, Instagram, etc.).
    """
    # --- STAGE 0: INITIALIZE & BROADCAST ---
    sender_name = message.pushname
    sender_number = message.contact_id
    message_body = message.body
    channel = message.channel

    print(f"\n--- New [{channel}] Message Pipeline Started for '{sender_name or sender_number}' ---")
    
    # Get or create the contact record in our database.
    contact = crud_contact.get_or_create_contact(db, contact_id=sender_number, pushname=sender_name)
    pause_timestamp = contact.ai_is_paused_until

    if pause_timestamp:
        if pause_timestamp.tzinfo is None:
            pause_timestamp = pause_timestamp.replace(tzinfo=timezone.utc)
        
        # Now, the comparison is safe
        if pause_timestamp > datetime.now(timezone.utc):
            print(f"-> AI is manually paused for {contact.contact_id}. Ignoring incoming message.")
            crud_contact.log_conversation(
                db=db,
                channel=message.channel,
                contact_db_id=contact.id,
                incoming_text=message.body,
                outgoing_text=None,
                status="received_ignored_ai_paused"
            )
            await manager.broadcast({"type": "new_message", "contact": schemas.Contact.from_orm(contact).model_dump()})
            return
    
    # Notify the live dashboard immediately.
    await manager.broadcast({"type": "new_message", "contact": contact_schemas.Contact.from_orm(contact).model_dump()})

    # --- STAGE 1: BUSINESS HOURS CHECK ---
    status, off_hours_message = get_business_status(db)

    if status == "CLOSED_QUIET":
        print(f"=> STAGE 1 [{channel}]: Business in 'Quiet Hours'. Ignoring.")
        crud_contact.log_conversation(db, channel, contact.id, message_body, None, "received_ignored_quiet_hours")
        print(f"--- Pipeline Finished (Quiet Hours) for [{channel}] ---\n")
        return

    if status == "CLOSED_AWAKE":
        print(f"=> STAGE 1 [{channel}]: Business closed, but not in quiet hours.")
        last_convo = crud_contact.get_last_conversation(db, contact_id=sender_number)
        if last_convo and last_convo.status == "replied_off_hours":
            print("   - Already sent off-hours message. Ignoring.")
            crud_contact.log_conversation(db, channel, contact.id, message_body, None, "received_ignored_off_hours")
            print(f"--- Pipeline Finished (Ignored) for [{channel}] ---\n")
            return
        else:
            print("   - Sending off-hours message.")
            crud_contact.log_conversation(db, channel, contact.id, message_body, off_hours_message, "replied_off_hours")
            # For now, we assume only WhatsApp can send replies. This will be refactored on Day 4.
            if channel == "WhatsApp":
                whatsapp_service.send_reply(sender_number, off_hours_message)
            print(f"--- Pipeline Finished for [{channel}] ---\n")
            return
    
    print(f"=> STAGE 1 [{channel}]: Business is OPEN. Proceeding...")

    # --- STAGE 2: PREPARE CONVERSATION HISTORY ---
    db_history = crud_contact.get_chat_history(db, contact_id=sender_number, limit=10)
    is_new_customer_for_ai = not contact.is_name_confirmed
    is_new_interaction = len(db_history) <= 1

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
    
    analysis = ai_service.analyze_message(
        chat_history=gemini_history, 
        db=db, 
        db_contact=contact,
        is_new_customer=is_new_customer_for_ai,
        is_new_interaction=is_new_interaction
    )
    
    ai_reply = analysis.get("reply", "I'm having a little trouble with that request. I've notified our Salon Manager, and they will get back to you here shortly. Thanks for your patience!")

    # --- STAGE 3.5: HANDLE NAME_PROVIDED Intent ---
    if analysis.get("intent") == "NAME_PROVIDED":
        provided_name = analysis.get("entities", {}).get("customer_name")
        if provided_name and not contact.is_name_confirmed:
            print(f"✅ AI extracted customer name: '{provided_name}'. Updating and confirming contact.")
            crud_contact.update_contact_name(db, contact_id=sender_number, new_name=provided_name)
    
    # --- STAGE 4: LOG & UPDATE DATABASE ---
    print(f"=> STAGE 4 [{channel}]: Logging conversation and updating with AI analysis...")
    new_conversation = crud_contact.log_conversation(
        db=db,
        channel=channel,
        contact_db_id=contact.id,
        incoming_text=message_body,
        outgoing_text=ai_reply,
        status="replied"
    )
    update_conversation_with_ai_analysis(db, new_conversation, analysis)

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