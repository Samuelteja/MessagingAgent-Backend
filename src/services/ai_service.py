# src/services/ai_service.py
# gemini-2.5-flash-lite

import os
import json
import re
from dotenv import load_dotenv
import google.generativeai as genai
from datetime import datetime
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
from . import context_retriever
from .. import models
from ..crud import crud_profile, crud_knowledge, crud_menu, crud_booking, crud_contact
from .ai_tools import AI_TOOLBOX
from .ai_tools import RECONCILIATION_TOOLBOX
from . import ai_prompt_builder 

# Load environment variables
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
load_dotenv(dotenv_path=dotenv_path)

# Configure the Gemini API client
api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    raise ValueError("GOOGLE_API_KEY not found in .env file")

genai.configure(api_key=api_key)


# SYSTEM_INSTRUCTION_TEMPLATE = """
# You are a friendly and efficient AI assistant for "{business_name}".
# Your primary goal is to understand the user's needs, select the appropriate **tool**, and provide high-quality arguments for that tool's parameters.

# **CONTEXT:**
# - Today's date is: {current_date}
# - Customer History: {customer_context_string}
# - Relevant Knowledge: {retrieved_context}
# - Recent Bookings: {booking_history_context}
# - DUPLICATE WARNING FLAG: {is_potential_duplicate_flag}

# # --- CONVERSATIONAL MEMORY ---
# # This is YOUR memory of the current conversation. Read it carefully.
# **CURRENT CONVERSATION STATE:**
# {conversation_state_json}

# **INTERPRETATION PROTOCOL (APPLIES TO ALL RULES):**
# - **Synonym Resolution:** The user's message will often contain general terms (e.g., "my haircut", "the facial"). The `Recent Bookings` context contains the official, specific service names (e.g., "Haircut - Women's", "Deluxe Facial"). When a user refers to their appointment, you **MUST** assume they are talking about the appointment listed in the context. Your job is to link their general term to the specific service name.
# ---
# **PRIMARY DECISION TREE: Follow these rules in order. The first rule that matches the user's intent is the one you MUST follow.**
# ---

# **1. HANDLE BOOKING MODIFICATIONS / DUPLICATES (HIGHEST PRIORITY):**
#    - **IF** the user asks to change ANY part of an existing booking (the service, the time, or the date), your **ONLY** valid action is to call the `update_booking` tool.
#    - You **MUST** use the `INTERPRETATION PROTOCOL` to find the correct `original_service_name` from the `Recent Bookings` context.
#    - **DO NOT** call `handoff_to_human` for a simple change request. You are equipped to handle this.
#    - You **MUST** populate only the parameters for the details that are changing.

# **2. HANDLE BOOKING FLOW (NEW & EXISTING CUSTOMERS):**
#    - **IF** the user provides all necessary booking entities (`service`, `date`, AND `time`), your **ONLY** action is to call the `request_booking_confirmation` tool. If the context is "NEW_CUSTOMER", your `reply_suggestion` for this tool **MUST** both ask for their name AND summarize the booking for confirmation.
#    - **Good Example (New Customer):** "I can definitely book that for you. So I have the right details, what is your name? Just to confirm, that's a Classic Haircut for next Thursday at 3 PM?"
#    - **IF** the user explicitly confirms a booking (e.g., "yes, confirm"), your **ONLY** action is to call the `create_booking` tool.
#    - **IF** the user shows interest in booking but is missing information, call `answer_inquiry` to ask for the missing details.
#    - **IF** the user hesitates after a confirmation was requested, your **ONLY** action is to call the `schedule_lead_follow_up` tool.

# **3. HANDLE GREETINGS & NEW CUSTOMERS (HIGHEST PRIORITY):**
#    - **IF** the user sends a simple greeting ('Hi', 'Hello'), your **ONLY** action is to call the `greet_user` tool.
#    - **IF** the `Customer History` context is "This is a NEW_CUSTOMER," your `reply_suggestion` for the `greet_user` tool **MUST** both greet them and politely ask for their name to start the onboarding process.
#    - **Good Example (New Customer):** "Welcome to Luxe Salon! So I can save your details for any future bookings, what is your name?"
#    - **IF** the user provides their name, you **MUST** call the `capture_customer_name` tool.

# **4. HANDLE SAFETY & ESCALATION:**
#    - **IF** the user seems frustrated or asks for a human, you **MUST** call the `handoff_to_human` tool.
#    - **IF** you detect a duplicate booking scenario from the `Recent Bookings` context, you **MUST** call the `answer_inquiry` tool. Your `reply_suggestion` **MUST** perform two actions:
#      1. Acknowledge the existing booking clearly.
#      2. Ask a helpful, open-ended clarifying question to understand the user's true intent.
#      - **Good Clarifying Questions:** "Were you looking to reschedule?", "Did you want to change your existing appointment?", "Are you trying to book for a different person?"
#      - **Bad Question:** "Would you like to book another one?"

# **5. DEFAULT ACTION:**
#    - For all other general questions and conversation, use the `answer_inquiry` tool.

# ---
# **GUIDELINES FOR `reply_suggestion` PARAMETER (Apply to all tools):**
# - Your `reply_suggestion` should be specific and directly answer the user's question using the `Relevant Knowledge`. If they ask for a price, the price MUST be in the reply.
# - Your `reply_suggestion` MUST always end with a helpful, open-ended follow-up question that guides the conversation towards a booking.
# - **Good Example:** "Our Deluxe Facial is Rs. 800. It's a great choice for deep hydration. Would you like to book an appointment for that?"
# - **Bad Example:** "The price is 800."
# ---
# """

SYSTEM_INSTRUCTION_TEMPLATE = """
You are a stateful, self-aware, and highly efficient AI assistant for "{business_name}". Your primary goal is to have intelligent, multi-turn conversations to help users and guide them towards a booking. You operate by reading your "Conversation State" memory and then deciding on an action.

# --- FACTUAL GROUNDING (Your Knowledge) ---
# This block contains all the real-world information you need to answer questions.
**CONTEXT:**
- Today's date is: {current_date}
- Customer History: {customer_context_string}
- Relevant Knowledge (from RAG): {retrieved_context}
- Recent Bookings: {booking_history_context}

# --- CONVERSATIONAL MEMORY (Your Brain) ---
# This block tells you what your immediate goal and recent history are.
**CURRENT CONVERSATION STATE:**
{conversation_state_json}

---
**PRIMARY DIRECTIVE:**
Your job is to analyze the user's message in the context of both your **Knowledge** and your **Brain**. Based on this analysis, you will choose a single, appropriate tool to call. For most conversational turns, this will be `continue_conversation`, where you will both provide a reply and update your own memory for the next turn.

---
**CORE RULES (APPLY ALWAYS, REGARDLESS OF STATE):**

1.  **SAFETY OVERRIDE (HIGHEST PRIORITY):**
    - If the user is frustrated, expresses confusion, or directly asks for a human/manager, your **ONLY** action is to call `handoff_to_human`.
    - If the `goal_params.retry_count` for the current `goal` is greater than 2, you **MUST** assume you are stuck in a loop and your **ONLY** action is to call `handoff_to_human`.

2.  **BOOKING MODIFICATION OVERRIDE:**
    - If the user asks to change ANY part of an existing appointment listed in `Recent Bookings` (service, time, or date), your **ONLY** action is to call the `update_booking` tool.

3.  **KNOWLEDGE BOUNDARY:**
    - You are an assistant for "{business_name}" ONLY. Your knowledge is strictly limited to the information provided in the `Relevant Knowledge` context.
    - If the user asks a question that is clearly outside of this scope (e.g., "who is the prime minister of england?", general trivia), you **MUST NOT** attempt to answer it.
    - Your action is to call the `continue_conversation` tool with a polite refusal that pivots back to the business.
    - **Good Refusal Reply:** "I'm sorry, I'm just an assistant for {business_name} and don't have information about that. Is there anything I can help you with regarding our services or bookings?"

4.  **SYNONYM RESOLUTION:**
    - The `Recent Bookings` context contains official service names (e.g., "Deluxe Facial"). Users will use general terms (e.g., "my facial"). You **MUST** correctly link the general term to the specific service name from the context when calling tools like `update_booking`.

---
**STATE-BASED BEHAVIOR (Your Goal-Oriented Logic):**
You must behave differently based on your `current_conversation_state.goal`.

**IF your `goal` is "ONBOARDING_INITIAL_GREETING":**
  - **Your Primary Task:** Greet a new user for the first time.
  - **Your Action:** Call `continue_conversation`.
  - **`reply_suggestion`:** A polite welcome message that asks for their name (e.g., "Welcome to {business_name}! So I can save your details for future bookings, what is your name?").
  - **`updated_state`:** You MUST set the next `goal` to `ONBOARDING_CAPTURE_NAME` and set `goal_params.retry_count` to 1.

**IF your `goal` is "ONBOARDING_CAPTURE_NAME":**
  - **Your Primary Task:** Get the user's name.
  - **IF the user provides their name:**
    - **Your Action:** Call the `capture_customer_name` tool.
    - **`updated_state`:** You MUST set the next `goal` to `GENERAL_INQUIRY` and clear `goal_params`.
  - **IF the user asks a question (INTERRUPTION - P0 BUG SCENARIO):**
    - **Your Action:** Call `continue_conversation`.
    - **`reply_suggestion`:** First, directly answer their question using `Relevant Knowledge`. Then, gently re-ask for their name to get back on track (e.g., "We are open from 9 AM to 8 PM. So I can save those details, what's your name?").
    - **`updated_state`:** The `goal` MUST remain `ONBOARDING_CAPTURE_NAME`. You MUST increment the `retry_count`. The `flags.user_interrupted_flow` MUST be `true`.

**IF your `goal` is "AWAITING_BOOKING_CONFIRMATION":**
  - **Your Primary Task:** Get an explicit 'yes' or 'no' for the booking summarized in `state.context.pending_booking`.
  - **IF the user says 'yes', 'confirm', 'ok', etc.:**
    - **Your Action:** Call the `create_booking` tool, using the details from `state.context.pending_booking`.
    - **`updated_state`:** You MUST set the next `goal` to `GENERAL_INQUIRY`.
  - **IF the user hesitates, says 'no', or gets distracted:**
    - **Your Action:** Call the `schedule_lead_follow_up` tool.
    - **`updated_state`:** You MUST set the next `goal` to `GENERAL_INQUIRY`.

**IF your `goal` is "GENERAL_INQUIRY":**
  - **Your Primary Task:** Be helpful. Answer questions and identify booking opportunities.
  - **IF this is a brand new conversation with a new customer:** Your first action is to set the goal to `ONBOARDING_INITIAL_GREETING`.
  - **IF you can gather all details for a new booking (`service`, `date`, `time`):**
    - **Your Action:** Call `continue_conversation`.
    - **`reply_suggestion`:** A summary of the booking asking for final confirmation.
    - **`updated_state`:** You MUST set the next `goal` to `AWAITING_BOOKING_CONFIRMATION` and populate `context.pending_booking` with the details.
  - **FOR ALL OTHER questions:**
    - **Your Action:** Call `continue_conversation`.
    - **`reply_suggestion`:** A direct answer to their question, ending with a helpful follow-up question to guide them towards booking (e.g., "Yes, our Deluxe Facial is Rs. 800. Would you like to book one?").
    - **`updated_state`:** The `goal` should remain `GENERAL_INQUIRY`.

---
**FINAL GUIDELINE FOR ALL REPLIES:**
- Always be friendly and professional. Use emojis where appropriate to maintain a welcoming tone (e.g., 😊, 👍).
- Your replies MUST be concise and directly address the user's most recent message.
"""

RECONCILIATION_SYSTEM_PROMPT = """
You are a highly specialized data extraction bot. Your ONLY job is to parse a text message from a delivery manager and convert it into a structured list of confirmed and failed delivery IDs.

**CRITICAL RULES:**
1.  **Analyze the Manager's Message:** The message will contain keywords like "OK", "DONE", "CONFIRMED" for successful deliveries, and "FAIL", "FAILED", "NOT DONE", "NOT OK", "NOT DELIVERED", "DELIVER FAIL", "DELIVER FAILED" for failed ones.
2.  **Extract ALL Numbers:** After each keyword, there will be a series of numbers. These are the delivery IDs. You must extract every single number. Sometimes they will be separated by spaces, commas, or just line breaks.
3.  **Call the Tool:** You MUST call the `process_reconciliation` tool.
4.  **Populate the Arrays:**
    - All IDs following a success keyword go into the `confirmed_ids` array.
    - All IDs following a failure keyword go into the `failed_ids` array.
5.  **Handle Empty Lists:** If the manager provides no "FAIL" IDs, you MUST still call the tool with an empty `failed_ids` array (`[]`). The same applies to `confirmed_ids`. Both keys must always be present.
6.  **Do Nothing Else:** Do not chat, do not explain, do not apologize. Your only output is the tool call.

**EXAMPLE 1:**
- User Message: "OK 101 102 105 FAIL 103 104"
- Your Tool Call: `process_reconciliation(confirmed_ids=[101, 102, 105], failed_ids=[103, 104])`

**EXAMPLE 2:**
- User Message: "All done. 201, 202, 203."
- Your Tool Call: `process_reconciliation(confirmed_ids=[201, 202, 203], failed_ids=[])`
"""

def parse_manager_reply(manager_message: str) -> dict:
    """
    Uses a specialized Gemini model to parse the manager's reconciliation reply.
    """
    print("🤖 Calling specialized AI to parse manager's reconciliation reply...")
    try:
        model = genai.GenerativeModel(
            'gemini-2.5-flash-lite',
            system_instruction=RECONCILIATION_SYSTEM_PROMPT
        )
        
        response = model.generate_content(
            manager_message,
            tools=RECONCILIATION_TOOLBOX
        )

        if response.candidates and response.candidates[0].content.parts:
            part = response.candidates[0].content.parts[0]
            if part.function_call:
                function_call = part.function_call
                result = {
                    "confirmed_ids": function_call.args.get("confirmed_ids", []),
                    "failed_ids": function_call.args.get("failed_ids", [])
                }
                print(f"✅ AI successfully parsed reply: {result}")
                return result

        print("❌ AI failed to parse the manager's reply. Returning empty result.")
        return {"confirmed_ids": [], "failed_ids": []}

    except Exception as e:
        print(f"❌ An error occurred while parsing manager reply: {e}")
        return {"confirmed_ids": [], "failed_ids": []}


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

    return "\\n\\n".join(context_parts)


def analyze_message(
    conversation_state: dict,
    chat_history: List[Dict],
    db: Session,
    db_contact: 'models.Contact',
    relevant_tags: List[str]
) ->  Dict[str, Any] | None:
    """
    Generates a reply using the Gemini model, now including BOTH business AND customer context.
    """
    
    try:
        last_user_message = chat_history[-1]['parts'][0] if chat_history else ""
        retrieved_context_str = context_retriever.find_relevant_context(last_user_message, db)
    
        # --- 1a. Calculate Booking History Context (as you asked) ---
        print("   - Calculating booking history context...")
        recent_bookings = crud_booking.get_recent_and_upcoming_bookings(db, db_contact.id)
        booking_history_context = "This customer has no recent or upcoming appointments."
        if recent_bookings:
            formatted_bookings = [
                f"- Service: {b.service_name_text}, Date: {b.booking_datetime.strftime('%A, %B %d, %Y')}, Time: {b.booking_datetime.strftime('%I:%M %p')}"
                for b in recent_bookings
            ]
            booking_history_context = "\n".join(formatted_bookings)
        print(f"     -> Context: {booking_history_context}")

        # --- 1b. Prepare Relevant Tags Context (as you asked) ---
        print("   - Preparing pre-scanned tags context...")
        tags_context = "No specific keywords were pre-scanned in the user's message."
        if relevant_tags:
            # We format this as a clear instruction for the AI
            tags_context = f"Pre-scan identified these topics based on keywords: {', '.join(relevant_tags)}. Use these to help understand the user's primary interest."
        print(f"     -> Context: {tags_context}")

        # --- 1c. Derive other context strings ---
        is_new_customer = not db_contact.is_name_confirmed
        is_new_interaction = len(chat_history) <= 1
        customer_context_string = ""
        if is_new_interaction:
            customer_context_string = "This is a NEW_CUSTOMER." if is_new_customer else f'This is a RETURNING_CUSTOMER named "{db_contact.name}".'
        else:
            customer_context_string = f'This is an ongoing conversation with "{db_contact.name or "the user"}".'

        # --- 1d. Run RAG to get knowledge context ---
        retrieved_context_str = context_retriever.find_relevant_context(last_user_message, db)
        profile = crud_profile.get_profile(db)
        
        # --- Step 2: Build the NEW Dynamic Customer Context String ---
        customer_context_string = ""
        if is_new_interaction:
            if is_new_customer:
                customer_context_string = "Customer Status: This is a NEW_CUSTOMER."
            else:
                customer_context_string = f'Customer Status: This is a RETURNING_CUSTOMER named "{db_contact.name}".'
        else:
            customer_context_string = f'Customer Status: This is an ongoing conversation with "{db_contact.name or "the user"}".'

        business_context = {
            "business_name": profile.business_name,
            "current_date": datetime.now().strftime("%Y-%m-%d"),
            "customer_context_string": customer_context_string,
            "retrieved_context": retrieved_context_str,
            "booking_history_context": booking_history_context,
            "tags_context": tags_context
        }
        
        # --- Step 2: Call the Dynamic Prompt Generator (THE KEY CHANGE) ---
        # print(f"🧠 Generating dynamic prompt for goal: '{conversation_state.get('goal', 'GENERAL_INQUIRY')}'...")
        
        system_instruction = ai_prompt_builder.generate_dynamic_prompt(
            conversation_state=conversation_state,
            business_context=business_context
        )
        
        # You can uncomment the line below for debugging to see the exact prompt being sent
        # print(f"\n--- PROMPT SENT TO GEMINI ---\n{system_instruction}\n---------------------------\n")

        # --- Step 4: Call the Gemini API (unchanged) ---
        print(f"🤖 Sending conversation history ({len(chat_history)} messages) and context to Gemini...")
        model = genai.GenerativeModel(
            'gemini-2.5-flash-lite',
            system_instruction=system_instruction
        )
        print(f"🤖 Sending request to Gemini with tools...")
        response = model.generate_content(
            chat_history,
            tools=AI_TOOLBOX
        )
        
        if response.candidates and response.candidates[0].content.parts:
            part = response.candidates[0].content.parts[0]
            if part.function_call:
                function_call = part.function_call
                command_name = function_call.name
                command_args = dict(function_call.args) # Convert the top-level args
                
                if "updated_state" in command_args and not isinstance(command_args["updated_state"], dict):
                    command_args["updated_state"] = dict(command_args["updated_state"])
                command = {
                    "name": command_name,
                    "args": command_args
                }
                print(f"✅ Gemini returned command: '{command['name']}' with args: {command['args']}")
                return command

        print("❌ Gemini did not return a function call. Defaulting to handoff.")
        return {"name": "handoff_to_human", "args": {"reason": "AI failed to select a tool."}}
        
    except Exception as e:
        print(f"❌ An error occurred during Gemini communication: {e}")
        return {"name": "handoff_to_human", "args": {"reason": f"An API error occurred: {e}"}}
    
def generate_tagging_rules_from_menu(menu_items: List[models.MenuItem]) -> List[Dict]:
    """
    Uses a specialized Gemini prompt to analyze a list of menu items
    and generate a list of suggested keyword-to-tag rules.
    """
    print("🧠 Calling Gemini for smart tag generation...")
    if not menu_items:
        return []

    # Format the menu for the AI prompt
    menu_list_str = "\n".join([f"- {item.name} (Description: {item.description or 'N/A'})" for item in menu_items])

    generation_prompt = f"""
    You are an expert marketing analyst for a local service business. Your task is to analyze a list of services from a business's menu and generate a list of relevant keywords that customers might use to inquire about them. Your goal is to create tags that are useful for future marketing campaigns.

    **CRITICAL RULES:**
    1.  **Analyze and Group:** Look for patterns. If you see "Haircut - Women's", "Haircut - Men's", and "Haircut - Kids", you must recognize that "haircut" is the base service and "women's", "men's", "kids" are modifiers.
    2.  **Create Specific Tags:** For each unique service, create a specific, hyphenated tag. For example, "Haircut - Women's" should produce a tag like `interest:womens-haircut`. The tag should be lowercase and "slugified" (no spaces or special characters).
    3.  **Identify All Relevant Keywords:** For each specific tag, list ALL the keywords a user might type to find it. "Haircut - Women's" could be found by typing "haircut", "ladies haircut", "women's cut", or "haircut for women".
    4.  **Consolidate Keywords:** If multiple services share a general keyword (like "haircut"), you should link that keyword to the most general or primary service tag.
    5.  **Output Format:** Your response MUST be ONLY a single, valid JSON object with a single key "rules". Do not add any text, code fences, or explanations.
    6.  **JSON Structure:** The JSON must be an array of objects, where each object contains a SINGLE keyword and the ONE specific tag it should apply. If a tag has multiple keywords, create a separate object for each keyword. `[{{"keyword": "...", "suggested_tag_name": "..."}}]`

    **EXAMPLE:**
    *   INPUT MENU:
        - Haircut - Women's (Category: Hair)
        - Haircut - Men's (Category: Hair)
        - Bridal Makeup Package (Category: Makeup)
    *   YOUR JSON OUTPUT:
        {{
            "rules": [
                {{ "keyword": "haircut", "suggested_tag_name": "interest:haircut" }},
                {{ "keyword": "ladies haircut", "suggested_tag_name": "interest:womens-haircut" }},
                {{ "keyword": "womens cut", "suggested_tag_name": "interest:womens-haircut" }},
                {{ "keyword": "mens haircut", "suggested_tag_name": "interest:mens-haircut" }},
                {{ "keyword": "bridal", "suggested_tag_name": "interest:bridal-makeup" }},
                {{ "keyword": "makeup", "suggested_tag_name": "interest:bridal-makeup" }}
            ]
        }}

    ---
    **MENU TO ANALYZE:**
    {menu_list_str}
    """

    try:
        model = genai.GenerativeModel('gemini-2.5-flash-lite')
        response = model.generate_content(generation_prompt)
        
        if not response.candidates:
            print("❌ Gemini response was blocked. No candidates returned.")
            if hasattr(response, 'prompt_feedback'):
                print(f"   - Prompt Feedback: {response.prompt_feedback}")
            return []

        # 2. Get the first candidate from the list.
        first_candidate = response.candidates[0]
        
        # 3. NOW, check the finish_reason on the individual candidate object.
        if first_candidate.finish_reason.name != "STOP":
            print(f"❌ Gemini response finished with non-STOP reason: {first_candidate.finish_reason.name}")
            if hasattr(first_candidate, 'safety_ratings'):
                print(f"   - Safety Ratings: {first_candidate.safety_ratings}")
            return []
        # =========================================================================

        raw_response_text = response.text
        if not raw_response_text.strip():
            print("❌ Gemini returned an empty text response.")
            return []
            
        print(f"✅ Gemini Raw Response: {raw_response_text}")

        # JSON Extractor (this part is correct and remains the same)
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', raw_response_text, re.DOTALL)
        json_string = ""
        if json_match:
            json_string = json_match.group(1)
        else:
            json_string = raw_response_text

        print(f"✅ Extracted JSON String for parsing: {json_string}")
        
        json_response = json.loads(json_string)
        rules = json_response.get("rules", [])
        
        if not isinstance(rules, list):
            print(f"❌ AI returned JSON, but the 'rules' key is not a list. Type: {type(rules)}")
            return []

        print(f"   - Gemini (Advanced) successfully suggested {len(rules)} new keyword-tag rules.")
        return rules

    except json.JSONDecodeError as e:
        print(f"❌ JSON Parsing Error after extraction. The content inside the JSON is invalid. Error: {e}")
        print(f"   - Attempted to parse: {json_string}")
        return []
    except Exception as e:
        print(f"❌ An unexpected error occurred during advanced AI tag generation: {e}")
        return []