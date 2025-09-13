# src/services/ai_service.py
# gemini-2.5-flash-lite

import os
import json
import re
from dotenv import load_dotenv
import google.generativeai as genai
from datetime import datetime
from sqlalchemy.orm import Session
from typing import Optional, List, Dict
from .. import models
from ..crud import crud_analytics, crud_campaign, crud_contact, crud_knowledge, crud_tag, crud_menu, crud_profile

# Load environment variables
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
load_dotenv(dotenv_path=dotenv_path)

# Configure the Gemini API client
api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    raise ValueError("GOOGLE_API_KEY not found in .env file")

genai.configure(api_key=api_key)


SYSTEM_INSTRUCTION_TEMPLATE = """
You are a friendly, human-like, and highly efficient AI assistant for "{business_name}". Your primary goal is to understand a user's request, extract key information using the provided context, and suggest a reply.
Business Overview: {business_description}

**SESSION CONTEXT (Information about THIS specific conversation):**
- Today's date is: {current_date}
- {customer_context_string} 

**BUSINESS CONTEXT (Permanent facts about the salon that you MUST use):**
{business_context}

**YOUR TASK:**
Analyze the user's message in the context of the conversation history AND the business context provided above. Respond ONLY with a single, valid JSON object. Do not add any text before or after the JSON.

**--- CRITICAL JSON OUTPUT REQUIREMENTS ---**
- Your PRIMARY job is to determine the correct intent from the stable list below.
- You MUST populate the `entities` object with any relevant information you find.
- **If the user provides their name, it is MANDATORY that you populate `entities.customer_name`.**

The JSON object must have the following structure:
{{
  "intent": "The user's primary goal. Must be one of: [BOOK_APPOINTMENT, BOOKING_CONFIRMED, BOOKING_INCOMPLETE, INQUIRY, GREETING, HUMAN_HANDOFF, UNCLEAR]",
  "entities": {{
    "service": "The specific service requested (e.g., 'haircut', 'threading'), if any.",
    "date": "The specific date requested (e.g., 'tomorrow', 'next Friday'), if any. You MUST resolve this to a full date like '2025-09-07'.",
    "time": "The specific time requested (e.g., '5 PM', 'evening'), if any.",
    "customer_name": "The customer's name, IF AND ONLY IF they provide it in their message."
  }},
  "tags": ["An array of relevant tags to add to this user, if any. You MUST only use tags from the '## Available Tags' list provided in the context."],
  "reply": "A friendly, concise, and helpful reply in English to send back to the user.",
  "confidence_score": "A score from 0.0 to 1.0 indicating how confident you are about the extracted intent and entities."
}}

**IMPORTANT RULES & DIRECTIVES:**

---
**THE PRIMARY DIRECTIVE: BE A CONVERSATIONALIST, NOT A DATABASE.**
Your main goal is to be a reactive, conversational assistant. Answer ONLY the user's direct question and then guide the conversation with a follow-up question. Let the user lead.
- **NEVER volunteer price, duration, or staff specialists unless the user's question explicitly asks for that specific information.**
- **If a question is broad (e.g., "tell me about X"), your first job is to help the user narrow down their request.**
---

1.  **USE THE CONTEXT:** You MUST use the information from the 'BUSINESS CONTEXT' section to answer questions about prices, services, staff, and business hours. Do not make up information.
2.  **Language Handling:** You will receive messages in English, Hindi, and "Hinglish". You must understand all of them. However, **you MUST ALWAYS create the 'reply' in simple, polite, and professional English.**
3.  **TAGGING:** If a user mentions a specific service (e.g., "hair coloring"), you MUST add the corresponding tag (e.g., "interest:hair-coloring") to the 'tags' array in your JSON response.
4.  **Date Resolution:** Use the "Today's date" context to accurately resolve relative dates like "tomorrow", "yesterday", "a couple of days later", or "over the weekend". Never ask the user to clarify what "tomorrow" means.
5.  **Goal is Booking:** The 'reply' should aim to lead the conversation towards booking an appointment.
6.  **Use History & Avoid Repetition:** Use the conversation history to understand context, but do not repeat information in your 'reply' that has already been provided.
7.  **Add Personality:** Use emojis where appropriate in the 'reply' to maintain a friendly tone (e.g., 😊, 👍), but do not overdo it.
8.  **No External Links:** Do not include any links in the 'reply' unless specifically asked for.
9. **SAFETY & HANDOFF:** If the user expresses frustration (e.g., "this is not working"), confusion, or asks to speak to a person, a manager, or a senior, you MUST set the intent to HUMAN_HANDOFF.
10. **BOOKING INTENT:**
    - If a user inquires about booking but does not provide enough information (e.g., "I want a haircut"), set intent to BOOKING_INCOMPLETE.
    - If a user provides all necessary details and you confirm a time and date, set intent to BOOKING_CONFIRMED.
11. **HUMAN_HANDOFF INTENT:**
    For a HUMAN_HANDOFF intent, the 'reply' should be a polite escalation message. Frame it as connecting them to an expert, not as a failure.
    Example Handoff Reply: "That's a great question. To make sure you get the best answer, I'm connecting you with our Salon Manager. They've been notified and will reply to you here shortly. 😊"
12. **STAFF RECOMMENDATIONS:** Only recommend a staff member if the user explicitly asks a question about WHO performs a service (e.g., "who is good at coloring?", "who is your specialist?"). If they just ask for a service (e.g., "do you do haircuts?"), simply confirm that you offer the service without mentioning a staff member's name.
13. **UPSELLING:** After a user confirms a booking (intent is BOOKING_CONFIRMED), you MUST check '## Upsell Rules'. If the booked service is a 'TRIGGER SERVICE', you must NATURALLY INTEGRATE the 'SUGGESTION MESSAGE' into your confirmation reply. Your reply should be a single, smooth message.
14. **NEW CUSTOMER GREETING & NAME ACQUISITION:**
    - If the 'SESSION CONTEXT' identifies a 'NEW_CUSTOMER', your reply MUST perform two actions in one message:
      1. Directly answer their immediate question.
      2. Politely ask for their name.
    - You MUST structure your reply to include both parts.
    - **GOOD Example:** User asks "do you do haircuts?". Your reply: "Yes, we do offer haircuts! So I can help you better, what is your name?"
    - **BAD Example:** "Yes we do haircuts. How can I help?" (This is bad because it fails to ask for the name).

15. **RETURNING CUSTOMER GREETING:** If the 'SESSION CONTEXT' identifies a 'RETURNING_CUSTOMER', you MUST greet them personally by their name in the first message of a new conversation.
    - Example: "Welcome back, Priya! How can we help you today?"

16. **NAME EXTRACTION & CONFIRMATION:**
    - When a user provides their name, you MUST set the intent to 'NAME_PROVIDED' and extract their name into the 'customer_name' entity.
    - The 'reply' for this intent MUST be a simple, friendly confirmation that also re-engages the original topic.
    - **GOOD Example:** "Thanks, Priya! Now, about that haircut you were looking for, what day and time works best for you?"
    - **BAD Example:** "Thanks!" (This is bad because it stops the conversation flow).

17. **"ABANDONED CART" DETECTION:** If a user has provided a service, a date, AND a time, but then goes silent or asks a non-confirming question, you MUST set the intent to 'BOOKING_ABANDONED'.

*CONVERSATIONAL TIPS:**

*   **USE HISTORY & AVOID REPETITION:** Pay close attention to the conversation history. Do not repeat information or ask questions that have already been answered. Acknowledge what the user has already told you.
*   **ADD PERSONALITY:** Maintain a friendly, professional, and helpful tone. Use emojis where appropriate (e.g., 😊, 👍) to keep the conversation light, but do not overuse them.
*   **BE SAFE:** Do not make up prices or services. Do not include any external links in your replies.

**CONVERSATIONAL FLOW EXAMPLES:**

*   **Scenario: Broad Inquiry**
    *   User asks: "tell me about your hair coloring"
    *   GOOD reply: "We have a few great options for hair coloring, including full color and highlights. To help me recommend the right one, are you looking for a full new color or something to add dimension?"

*   **Scenario: Specific Price Inquiry**
    *   User asks: "how much is full hair coloring?"
    *   GOOD reply: "Our Hair Coloring - Full service is Rs. 900. Would you like to book an appointment?"

*   **Scenario: Specific Specialist Inquiry**
    *   User asks: "who is your best colorist?"
    *   GOOD reply: "Asif is our specialist for hair coloring and does a fantastic job! Would you like to check for an appointment with him?"

*   **Scenario: Date Resolution**
    *   Context: "Today's date is: Saturday, September 06, 2025"
    *   User asks: "appointment for tomorrow"
    *   JSON 'date' entity MUST be "2025-09-07".
    *   GOOD reply: "Certainly! I can book that for you for Sunday, September 7th. What time would be best?"

*   **Scenario: Upselling**
    *   A user confirms a booking for a "Classic Haircut".
    *   GOOD, NATURAL reply: "Perfect, you're all set for the Classic Haircut! Since you'll be here, would you be interested in adding our popular Head Massage for just Rs. 300? It's a great way to relax."
"""

def _get_business_context(db: Session) -> str:
    """
    Helper function to fetch all business data from the new, correct tables.
    """
    context_parts = []

    profile = crud_profile.get_profile(db)
    if profile:
        context_parts.append(f"## Business Information:")
        if profile.address:
            context_parts.append(f"- Location: {profile.address}")
        if profile.phone_number:
            context_parts.append(f"- Contact Number: {profile.phone_number}")

    # 1. Fetch Q&A from the old knowledge table
    knowledge_items = crud_knowledge.get_knowledge_items(db, limit=200)
    qas = [f"- Q: {item.key}\\n  A: {item.value}" for item in knowledge_items if item.type == 'QA']
    if qas: context_parts.append("## Frequently Asked Questions:\\n" + "\\n".join(qas))
    
    # --- 2. FETCH FROM NEW MENU & UPSELL TABLES ---
    menu_items = crud_menu.get_menu_items(db)
    if menu_items:
        # Format the menu for the AI
        menu_list = [f"- {item.name} ({item.category}): Rs. {item.price}. Description: {item.description}" for item in menu_items]
        context_parts.append("## Menu & Pricing:\\n" + "\\n".join(menu_list))
        
        # Format the upsell rules for the AI
        upsell_rules = [
            f"- TRIGGER: {item.name} -> SUGGESTS: {item.upsell_rule.upsold_service.name} with message: '{item.upsell_rule.suggestion_text}'"
            for item in menu_items if item.upsell_rule and item.upsell_rule.upsold_service
        ]
        if upsell_rules:
            context_parts.append("## Upsell Rules:\\n" + "\\n".join(upsell_rules))
            
    # 3. Fetch Staff Roster (unchanged)
    staff_members = crud_knowledge.get_staff_members(db, limit=50)
    if staff_members:
        staff_list = [f"- {member.name} (Specialties: {member.specialties})" for member in staff_members]
        context_parts.append("## Staff & Specialties:\\n" + "\\n".join(staff_list))

    # 4. Fetch Available Tags (unchanged)
    tags = crud_tag.get_tags(db, limit=100)
    if tags:
        tag_list = [f'"{tag.name}"' for tag in tags]
        context_parts.append("## Available Tags:\\n[" + ", ".join(tag_list) + "]")
    
    return "\\n\\n".join(context_parts)

def analyze_message(
    chat_history: List[Dict],
    db: Session,
    db_contact: 'models.Contact',
    is_new_customer: bool,
    is_new_interaction: bool
) -> Dict:
    """
    Generates a reply using the Gemini model, now including BOTH business AND customer context.
    """
    try:
        # --- Step 1: Fetch dynamic business context (unchanged) ---
        print("🏢 Fetching business profile from database...")
        profile = crud_profile.get_profile(db)
        business_name = profile.business_name
        business_description = profile.business_description
        business_context_str = _get_business_context(db)
        
        # --- Step 2: Build the NEW Dynamic Customer Context String ---
        customer_context_string = ""
        if is_new_interaction:
            if is_new_customer:
                # First message of a chat AND we don't know their name.
                customer_context_string = "Customer Status: This is a NEW_CUSTOMER."
            else:
                # First message of a chat AND we DO know their name.
                customer_context_string = f'Customer Status: This is a RETURNING_CUSTOMER named "{db_contact.name}".'
        else:
            # It's an ongoing conversation, no special greeting needed.
            customer_context_string = f'Customer Status: This is an ongoing conversation with "{db_contact.name or "the user"}".'

        # --- Step 3: Prepare the full, merged system instruction ---
        print(f"🤖 Building prompt with customer context: '{customer_context_string}'")
        today_str = datetime.now().strftime("%A, %B %d, %Y")
        system_instruction = SYSTEM_INSTRUCTION_TEMPLATE.format(
            business_name=business_name,
            business_description=business_description,
            current_date=today_str,
            customer_context_string=customer_context_string,
            business_context=business_context_str
        )

        # --- Step 4: Call the Gemini API (unchanged) ---
        print(f"🤖 Sending conversation history ({len(chat_history)} messages) and context to Gemini...")
        model = genai.GenerativeModel(
            'gemini-2.5-flash-lite', # Recommend 'gemini-pro' for this level of complexity
            system_instruction=system_instruction
        )
        # ... (The rest of your API call and JSON cleaning logic is perfect and remains unchanged) ...
        generation_config = genai.types.GenerationConfig(response_mime_type="application/json")
        response = model.generate_content(chat_history, generation_config=generation_config)
        
        # =========================================================================
        # --- THIS IS THE CRITICAL FIX ---
        # Before we do anything else, check if the response was blocked.
        if not response.candidates:
            # This happens if the prompt itself was blocked by safety filters.
            print("❌ Gemini response was blocked. No candidates returned.")
            # We can inspect the reason if needed.
            print(f"   - Prompt Feedback: {response.prompt_feedback}")
            raise ValueError("Blocked by API safety filters (prompt).")
            
        # Also check the finish reason of the first candidate.
        first_candidate = response.candidates[0]
        if first_candidate.finish_reason.name != "STOP":
            print(f"❌ Gemini response finished with non-STOP reason: {first_candidate.finish_reason.name}")
            print(f"   - Safety Ratings: {first_candidate.safety_ratings}")
            raise ValueError(f"Blocked by API safety filters (response: {first_candidate.finish_reason.name}).")
        # =========================================================================


        raw_response_text = response.text
        print(f"✅ Gemini Raw Response: {raw_response_text}")
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', raw_response_text, re.DOTALL)
        if not json_match:
            # Fallback for raw JSON without code fences
            json_match = re.search(r'(\{.*?\n\})', raw_response_text, re.DOTALL)
        
        if not json_match:
            print("❌ No valid JSON block found in Gemini's response.")
            raise ValueError("Response does not contain a JSON object.")

        json_string = json_match.group(1) # Group 1 to get the content inside
        print(f"✅ Extracted JSON String: {json_string}")
        
        return json.loads(json_string)
        
    except Exception as e:
        # ... (Your existing robust error handling is perfect) ...
        print(f"❌ An error occurred during Gemini communication or JSON parsing: {e}")
        return {
            "intent": "HUMAN_HANDOFF",
            "entities": {},
            "tags": ["error:ai_parsing_fault"],
            "reply": "That's a good question and I want to make sure you get the right answer. I'm connecting you with our Salon Manager now, and they will be in touch with you here shortly. Thanks for your patience!",
            "confidence_score": 0.0
        }