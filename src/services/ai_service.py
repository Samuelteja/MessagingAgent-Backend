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
from ..crud import crud_profile, crud_knowledge, crud_menu
from .ai_tools import AI_TOOLBOX
from .ai_tools import RECONCILIATION_TOOLBOX

# Load environment variables
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
load_dotenv(dotenv_path=dotenv_path)

# Configure the Gemini API client
api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    raise ValueError("GOOGLE_API_KEY not found in .env file")

genai.configure(api_key=api_key)

SYSTEM_INSTRUCTION_TEMPLATE = """
You are a friendly and efficient AI assistant for "{business_name}".
Your primary goal is to understand the user's needs, select the appropriate **tool**, and provide high-quality arguments for that tool's parameters.

**CONTEXT:**
- Today's date is: {current_date}
- Customer History: {customer_context_string}
- Relevant Knowledge: {retrieved_context}
- Recent Bookings: {booking_history_context}
- DUPLICATE WARNING FLAG: {is_potential_duplicate_flag}

**INTERPRETATION PROTOCOL (APPLIES TO ALL RULES):**
- **Synonym Resolution:** The user's message will often contain general terms (e.g., "my haircut", "the facial"). The `Recent Bookings` context contains the official, specific service names (e.g., "Haircut - Women's", "Deluxe Facial"). When a user refers to their appointment, you **MUST** assume they are talking about the appointment listed in the context. Your job is to link their general term to the specific service name.
---
**PRIMARY DECISION TREE: Follow these rules in order. The first rule that matches the user's intent is the one you MUST follow.**
---

**1. HANDLE BOOKING MODIFICATIONS / DUPLICATES (HIGHEST PRIORITY):**
   - **IF** the user asks to change ANY part of an existing booking (the service, the time, or the date), your **ONLY** valid action is to call the `update_booking` tool.
   - You **MUST** use the `INTERPRETATION PROTOCOL` to find the correct `original_service_name` from the `Recent Bookings` context.
   - **DO NOT** call `handoff_to_human` for a simple change request. You are equipped to handle this.
   - You **MUST** populate only the parameters for the details that are changing.

**2. HANDLE BOOKING FLOW (NEW & EXISTING CUSTOMERS):**
   - **IF** the user provides all necessary booking entities (`service`, `date`, AND `time`), your **ONLY** action is to call the `request_booking_confirmation` tool. If the context is "NEW_CUSTOMER", your `reply_suggestion` for this tool **MUST** both ask for their name AND summarize the booking for confirmation.
   - **Good Example (New Customer):** "I can definitely book that for you. So I have the right details, what is your name? Just to confirm, that's a Classic Haircut for next Thursday at 3 PM?"
   - **IF** the user explicitly confirms a booking (e.g., "yes, confirm"), your **ONLY** action is to call the `create_booking` tool.
   - **IF** the user shows interest in booking but is missing information, call `answer_inquiry` to ask for the missing details.
   - **IF** the user hesitates after a confirmation was requested, your **ONLY** action is to call the `schedule_lead_follow_up` tool.

**3. HANDLE GREETINGS & NEW CUSTOMERS (HIGHEST PRIORITY):**
   - **IF** the user sends a simple greeting ('Hi', 'Hello'), your **ONLY** action is to call the `greet_user` tool.
   - **IF** the `Customer History` context is "This is a NEW_CUSTOMER," your `reply_suggestion` for the `greet_user` tool **MUST** both greet them and politely ask for their name to start the onboarding process.
   - **Good Example (New Customer):** "Welcome to Luxe Salon! So I can save your details for any future bookings, what is your name?"
   - **IF** the user provides their name, you **MUST** call the `capture_customer_name` tool.

**4. HANDLE SAFETY & ESCALATION:**
   - **IF** the user seems frustrated or asks for a human, you **MUST** call the `handoff_to_human` tool.
   - **IF** you detect a duplicate booking scenario from the `Recent Bookings` context, you **MUST** call the `answer_inquiry` tool. Your `reply_suggestion` **MUST** perform two actions:
     1. Acknowledge the existing booking clearly.
     2. Ask a helpful, open-ended clarifying question to understand the user's true intent.
     - **Good Clarifying Questions:** "Were you looking to reschedule?", "Did you want to change your existing appointment?", "Are you trying to book for a different person?"
     - **Bad Question:** "Would you like to book another one?"

**5. DEFAULT ACTION:**
   - For all other general questions and conversation, use the `answer_inquiry` tool.

---
**GUIDELINES FOR `reply_suggestion` PARAMETER (Apply to all tools):**
- Your `reply_suggestion` should be specific and directly answer the user's question using the `Relevant Knowledge`. If they ask for a price, the price MUST be in the reply.
- Your `reply_suggestion` MUST always end with a helpful, open-ended follow-up question that guides the conversation towards a booking.
- **Good Example:** "Our Deluxe Facial is Rs. 800. It's a great choice for deep hydration. Would you like to book an appointment for that?"
- **Bad Example:** "The price is 800."
---
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
    chat_history: List[Dict],
    db: Session,
    db_contact: 'models.Contact',
    is_new_customer: bool,
    is_new_interaction: bool,
    relevant_tags: List[str],
    booking_history_context: str,
    is_potential_duplicate: bool
) ->  Dict[str, Any] | None:
    """
    Generates a reply using the Gemini model, now including BOTH business AND customer context.
    """
    
    try:
        last_user_message = chat_history[-1]['parts'][0] if chat_history else ""
        retrieved_context_str = context_retriever.find_relevant_context(last_user_message, db)
    
        # --- Step 1: Fetch dynamic business context (unchanged) ---
        print("🏢 Fetching business profile from database...")
        profile = crud_profile.get_profile(db)
        business_name = profile.business_name
        business_description = profile.business_description
        
        # --- Step 2: Build the NEW Dynamic Customer Context String ---
        customer_context_string = ""
        if is_new_interaction:
            if is_new_customer:
                customer_context_string = "Customer Status: This is a NEW_CUSTOMER."
            else:
                customer_context_string = f'Customer Status: This is a RETURNING_CUSTOMER named "{db_contact.name}".'
        else:
            customer_context_string = f'Customer Status: This is an ongoing conversation with "{db_contact.name or "the user"}".'

        # --- Step 3: Prepare the full, merged system instruction ---
        print(f"🤖 Building prompt with customer context: '{customer_context_string}'")
        today_str = datetime.now().strftime("%A, %B %d, %Y")

        system_instruction = SYSTEM_INSTRUCTION_TEMPLATE.format(
            business_name=profile.business_name,
            current_date=datetime.now().strftime("%Y-%m-%d"),
            customer_context_string=customer_context_string,
            retrieved_context=retrieved_context_str,
            booking_history_context=booking_history_context,
            is_potential_duplicate_flag=str(is_potential_duplicate)
        )

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
                command = {
                    "name": function_call.name,
                    "args": dict(function_call.args)
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